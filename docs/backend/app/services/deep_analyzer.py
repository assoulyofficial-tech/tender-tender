"""
Deep Analysis Service - AI Pipeline 2.

Triggered on-demand when user opens a tender.
Extracts: Universal Fields, Lot items, Execution dates.
Implements: Annex reconciliation, Field provenance tracking.
"""

import json
import httpx
from dataclasses import dataclass, field, asdict
from typing import Optional, Any
from uuid import UUID
from datetime import datetime

from app.config import settings


# Universal Fields Schema
@dataclass
class LotItem:
    """Individual lot in a multi-lot tender."""
    lot_number: int
    title: str
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    estimated_value: Optional[float] = None
    execution_location: Optional[str] = None
    
    
@dataclass
class ExecutionDates:
    """Execution/delivery timeline."""
    start_date: Optional[str] = None  # ISO format
    end_date: Optional[str] = None  # ISO format
    duration_days: Optional[int] = None
    duration_months: Optional[int] = None
    milestones: list[dict] = field(default_factory=list)  # [{name, date, description}]
    delivery_schedule: Optional[str] = None


@dataclass
class UniversalFields:
    """
    Universal fields extracted via deep analysis.
    Extends Avis metadata with detailed procurement information.
    """
    # Contract Details
    contract_type: Optional[str] = None  # Works, Supplies, Services, Mixed
    procedure_type: Optional[str] = None  # Open, Restricted, Negotiated, etc.
    award_criteria: Optional[str] = None  # Lowest price, MEAT, etc.
    
    # Financial Details
    payment_terms: Optional[str] = None
    advance_payment: Optional[float] = None  # Percentage
    retention_percentage: Optional[float] = None
    price_revision_clause: bool = False
    currency: str = "DZD"
    
    # Guarantees
    bid_guarantee: Optional[float] = None
    performance_guarantee: Optional[float] = None
    advance_guarantee: Optional[float] = None
    
    # Technical Specifications
    technical_specifications: list[str] = field(default_factory=list)
    quality_standards: list[str] = field(default_factory=list)  # ISO, NF, etc.
    environmental_requirements: list[str] = field(default_factory=list)
    
    # Eligibility Deep Dive
    minimum_experience_years: Optional[int] = None
    required_certifications: list[str] = field(default_factory=list)
    required_equipment: list[str] = field(default_factory=list)
    minimum_turnover: Optional[float] = None
    minimum_similar_projects: Optional[int] = None
    
    # Subcontracting
    subcontracting_allowed: bool = True
    max_subcontracting_percentage: Optional[float] = None
    
    # Lot Information
    lots: list[LotItem] = field(default_factory=list)
    single_lot_only: bool = False  # Can bid on individual lots
    all_lots_required: bool = False  # Must bid on all lots
    
    # Execution Timeline
    execution_dates: Optional[ExecutionDates] = None
    
    # Contact Information
    contracting_authority: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    
    # Additional
    language_requirements: list[str] = field(default_factory=list)
    site_visit_required: bool = False
    site_visit_date: Optional[str] = None
    clarification_deadline: Optional[str] = None
    
    # Metadata
    confidence_score: float = 0.0
    extraction_notes: list[str] = field(default_factory=list)


# Deep Analysis Prompt
DEEP_ANALYSIS_PROMPT = """You are an expert procurement analyst specialized in public tender analysis.

Analyze the provided tender document(s) and extract DETAILED information following this structure.

EXTRACTION RULES:
1. NO GUESSING - Only extract information explicitly stated in the documents
2. Use ISO 8601 date format (YYYY-MM-DD) for all dates
3. Use numeric values without currency symbols for amounts
4. If information is not found, leave the field null/empty
5. Confidence score (0.0-1.0) reflects how clearly information was stated
6. Note any ambiguities in extraction_notes

EXTRACT THE FOLLOWING:

## CONTRACT DETAILS
- contract_type: "Works" | "Supplies" | "Services" | "Mixed"
- procedure_type: Open, Restricted, Negotiated, Competitive Dialogue, etc.
- award_criteria: "Lowest Price" | "MEAT" (Most Economically Advantageous Tender) | description

## FINANCIAL DETAILS
- payment_terms: Payment schedule description
- advance_payment: Percentage of advance payment allowed
- retention_percentage: Retention money percentage
- price_revision_clause: true/false
- currency: Currency code (default DZD)

## GUARANTEES (as percentages or absolute amounts)
- bid_guarantee: Bid/tender guarantee amount
- performance_guarantee: Performance bond percentage
- advance_guarantee: Guarantee for advance payment

## TECHNICAL REQUIREMENTS
- technical_specifications: List of specific technical requirements
- quality_standards: Required certifications (ISO 9001, NF, etc.)
- environmental_requirements: Environmental/sustainability requirements

## ELIGIBILITY REQUIREMENTS
- minimum_experience_years: Years in relevant field
- required_certifications: Professional/technical certifications
- required_equipment: Required equipment/machinery list
- minimum_turnover: Minimum annual turnover requirement
- minimum_similar_projects: Number of similar completed projects

## SUBCONTRACTING
- subcontracting_allowed: true/false
- max_subcontracting_percentage: Maximum allowed percentage

## LOTS (if applicable)
For each lot extract:
- lot_number: Sequential number
- title: Lot title/name
- description: Detailed description
- quantity: Amount/quantity
- unit: Unit of measure
- estimated_value: Estimated value
- execution_location: Where work/delivery happens

## EXECUTION DATES
- start_date: Contract/execution start date
- end_date: Expected completion date
- duration_days: Duration in days (if specified)
- duration_months: Duration in months (if specified)
- milestones: Key milestones [{name, date, description}]
- delivery_schedule: Delivery schedule description

## CONTACT INFORMATION
- contracting_authority: Full name of contracting entity
- contact_name: Contact person name
- contact_email: Email address
- contact_phone: Phone number

## OTHER REQUIREMENTS
- language_requirements: Required languages for submission
- site_visit_required: true/false
- site_visit_date: Date of mandatory site visit
- clarification_deadline: Deadline for questions

Respond ONLY with valid JSON matching this structure. No markdown, no explanations."""


class DeepAnalyzer:
    """
    Deep Analysis using DeepSeek API.
    Triggered on-demand when user views a tender.
    """
    
    def __init__(self):
        self.api_key = settings.deepseek_api_key
        self.base_url = settings.deepseek_base_url
        self.model = settings.deepseek_model
        self.timeout = 120.0  # Deep analysis takes longer
    
    def is_configured(self) -> bool:
        """Check if API key is configured."""
        return bool(self.api_key)
    
    async def analyze_documents(
        self,
        documents: list[dict],
        existing_metadata: Optional[dict] = None
    ) -> UniversalFields:
        """
        Perform deep analysis on tender documents.
        
        Args:
            documents: List of {filename, content, is_annex, document_type}
            existing_metadata: Previously extracted Avis metadata (for context)
            
        Returns:
            UniversalFields with extracted data
        """
        if not self.is_configured():
            raise ValueError("DeepSeek API key not configured")
        
        # Prepare document content with annex markers
        doc_texts = []
        for doc in documents:
            marker = "[ANNEXE]" if doc.get("is_annex") else "[DOCUMENT PRINCIPAL]"
            doc_type = doc.get("document_type", "unknown")
            doc_texts.append(
                f"\n{'='*60}\n"
                f"{marker} {doc['filename']} (type: {doc_type})\n"
                f"{'='*60}\n"
                f"{doc['content'][:50000]}"  # Limit per document
            )
        
        combined_text = "\n\n".join(doc_texts)
        
        # Add existing metadata context if available
        context = ""
        if existing_metadata:
            context = f"\n\nPreviously extracted metadata (for reference):\n{json.dumps(existing_metadata, indent=2, default=str)}\n"
        
        # Call DeepSeek API
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": DEEP_ANALYSIS_PROMPT
                        },
                        {
                            "role": "user",
                            "content": f"Analyze these tender documents:{context}\n\n{combined_text}"
                        }
                    ],
                    "temperature": 0.1,  # Low temperature for consistent extraction
                    "max_tokens": 8000
                }
            )
            
            if response.status_code != 200:
                error_text = response.text
                raise Exception(f"DeepSeek API error {response.status_code}: {error_text}")
            
            result = response.json()
            
        # Parse response
        content = result["choices"][0]["message"]["content"]
        
        # Clean JSON from potential markdown
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        
        try:
            data = json.loads(content.strip())
        except json.JSONDecodeError as e:
            return UniversalFields(
                extraction_notes=[f"JSON parse error: {str(e)}", f"Raw content: {content[:500]}"]
            )
        
        # Build UniversalFields from response
        return self._parse_response(data)
    
    def _parse_response(self, data: dict) -> UniversalFields:
        """Parse API response into UniversalFields."""
        
        # Parse lots
        lots = []
        for lot_data in data.get("lots", []):
            lots.append(LotItem(
                lot_number=lot_data.get("lot_number", 0),
                title=lot_data.get("title", ""),
                description=lot_data.get("description"),
                quantity=lot_data.get("quantity"),
                unit=lot_data.get("unit"),
                estimated_value=lot_data.get("estimated_value"),
                execution_location=lot_data.get("execution_location")
            ))
        
        # Parse execution dates
        exec_dates = None
        if "execution_dates" in data and data["execution_dates"]:
            ed = data["execution_dates"]
            exec_dates = ExecutionDates(
                start_date=ed.get("start_date"),
                end_date=ed.get("end_date"),
                duration_days=ed.get("duration_days"),
                duration_months=ed.get("duration_months"),
                milestones=ed.get("milestones", []),
                delivery_schedule=ed.get("delivery_schedule")
            )
        
        return UniversalFields(
            # Contract Details
            contract_type=data.get("contract_type"),
            procedure_type=data.get("procedure_type"),
            award_criteria=data.get("award_criteria"),
            
            # Financial
            payment_terms=data.get("payment_terms"),
            advance_payment=data.get("advance_payment"),
            retention_percentage=data.get("retention_percentage"),
            price_revision_clause=data.get("price_revision_clause", False),
            currency=data.get("currency", "DZD"),
            
            # Guarantees
            bid_guarantee=data.get("bid_guarantee"),
            performance_guarantee=data.get("performance_guarantee"),
            advance_guarantee=data.get("advance_guarantee"),
            
            # Technical
            technical_specifications=data.get("technical_specifications", []),
            quality_standards=data.get("quality_standards", []),
            environmental_requirements=data.get("environmental_requirements", []),
            
            # Eligibility
            minimum_experience_years=data.get("minimum_experience_years"),
            required_certifications=data.get("required_certifications", []),
            required_equipment=data.get("required_equipment", []),
            minimum_turnover=data.get("minimum_turnover"),
            minimum_similar_projects=data.get("minimum_similar_projects"),
            
            # Subcontracting
            subcontracting_allowed=data.get("subcontracting_allowed", True),
            max_subcontracting_percentage=data.get("max_subcontracting_percentage"),
            
            # Lots
            lots=lots,
            single_lot_only=data.get("single_lot_only", False),
            all_lots_required=data.get("all_lots_required", False),
            
            # Execution
            execution_dates=exec_dates,
            
            # Contact
            contracting_authority=data.get("contracting_authority"),
            contact_name=data.get("contact_name"),
            contact_email=data.get("contact_email"),
            contact_phone=data.get("contact_phone"),
            
            # Other
            language_requirements=data.get("language_requirements", []),
            site_visit_required=data.get("site_visit_required", False),
            site_visit_date=data.get("site_visit_date"),
            clarification_deadline=data.get("clarification_deadline"),
            
            # Metadata
            confidence_score=data.get("confidence_score", 0.8),
            extraction_notes=data.get("extraction_notes", [])
        )
    
    def to_dict(self, fields: UniversalFields) -> dict:
        """Convert UniversalFields to dictionary for storage."""
        result = asdict(fields)
        
        # Convert nested dataclasses
        if fields.execution_dates:
            result["execution_dates"] = asdict(fields.execution_dates)
        
        result["lots"] = [asdict(lot) for lot in fields.lots]
        
        return result

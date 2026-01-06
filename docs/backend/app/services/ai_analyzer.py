"""
AI Analysis Pipeline using DeepSeek API.
Extracts Avis metadata from tender documents.
No guessing - only extracts what's explicitly stated.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


# Avis Metadata Schema
@dataclass
class AvisMetadata:
    """Extracted Avis metadata from tender documents."""
    # Basic info
    reference: Optional[str] = None
    title: Optional[str] = None
    organization: Optional[str] = None
    
    # Dates
    publication_date: Optional[str] = None
    deadline: Optional[str] = None  # Submission deadline
    opening_date: Optional[str] = None  # Bid opening date
    
    # Financial
    budget_estimate: Optional[float] = None
    caution_amount: Optional[float] = None
    
    # Classification
    category: Optional[str] = None
    
    # Keywords (multilingual)
    keywords_fr: list[str] = field(default_factory=list)
    keywords_ar: list[str] = field(default_factory=list)
    keywords_en: list[str] = field(default_factory=list)
    
    # Requirements
    eligibility_criteria: list[str] = field(default_factory=list)
    submission_requirements: list[str] = field(default_factory=list)
    technical_requirements: list[str] = field(default_factory=list)
    
    # Documents
    required_documents: list[str] = field(default_factory=list)
    
    # Location
    submission_address: Optional[str] = None
    opening_location: Optional[str] = None
    
    # Additional
    lots: list[dict] = field(default_factory=list)  # If multiple lots
    notes: Optional[str] = None


@dataclass
class AnalysisResult:
    """Result of AI analysis."""
    metadata: AvisMetadata
    success: bool = True
    error: Optional[str] = None
    confidence: float = 0.0
    source_type: str = "ai"  # For provenance tracking


EXTRACTION_PROMPT = """You are a tender document analyst. Extract metadata from the following tender document text.

CRITICAL RULES:
1. ONLY extract information that is EXPLICITLY stated in the text
2. DO NOT guess, infer, or make assumptions
3. If information is not clearly stated, leave the field as null or empty array
4. Dates must be in ISO format (YYYY-MM-DD) or null if unclear
5. Amounts must be numbers only (no currency symbols)
6. Extract keywords in French, Arabic, and English when available

DOCUMENT TEXT:
{document_text}

Extract and return a JSON object with this exact structure:
{{
    "reference": "tender reference number or null",
    "title": "tender title or null",
    "organization": "issuing organization or null",
    "publication_date": "YYYY-MM-DD or null",
    "deadline": "YYYY-MM-DD or null (submission deadline)",
    "opening_date": "YYYY-MM-DD or null (bid opening date)",
    "budget_estimate": number or null,
    "caution_amount": number or null,
    "category": "category type or null",
    "keywords_fr": ["french", "keywords"],
    "keywords_ar": ["arabic", "keywords"],
    "keywords_en": ["english", "keywords"],
    "eligibility_criteria": ["criterion 1", "criterion 2"],
    "submission_requirements": ["requirement 1", "requirement 2"],
    "technical_requirements": ["technical spec 1", "technical spec 2"],
    "required_documents": ["document 1", "document 2"],
    "submission_address": "address or null",
    "opening_location": "location or null",
    "lots": [
        {{"lot_number": 1, "description": "lot description", "budget": number or null}}
    ],
    "notes": "any additional important notes or null"
}}

Return ONLY the JSON object, no explanations."""


class DeepSeekAnalyzer:
    """AI analyzer using DeepSeek API."""
    
    def __init__(self):
        self.api_key = settings.deepseek_api_key
        self.base_url = settings.deepseek_base_url
        self.model = settings.deepseek_model
    
    def is_configured(self) -> bool:
        """Check if DeepSeek API is configured."""
        return bool(self.api_key)
    
    async def analyze_document(
        self,
        document_text: str,
        website_deadline: Optional[datetime] = None,
        is_annex: bool = False
    ) -> AnalysisResult:
        """
        Analyze document and extract Avis metadata.
        
        Args:
            document_text: Extracted text from document
            website_deadline: Deadline from website (takes precedence)
            is_annex: If True, this is an annex document (override priority)
            
        Returns:
            AnalysisResult with extracted metadata
        """
        if not self.is_configured():
            return AnalysisResult(
                metadata=AvisMetadata(),
                success=False,
                error="DeepSeek API key not configured. Set DEEPSEEK_API_KEY in .env"
            )
        
        if not document_text or len(document_text.strip()) < 100:
            return AnalysisResult(
                metadata=AvisMetadata(),
                success=False,
                error="Document text too short or empty"
            )
        
        try:
            # Truncate very long documents
            max_chars = 50000
            if len(document_text) > max_chars:
                document_text = document_text[:max_chars] + "\n...[truncated]..."
            
            prompt = EXTRACTION_PROMPT.format(document_text=document_text)
            
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": "You are a precise document analyzer. Extract only explicitly stated information."},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.1,  # Low temperature for consistent extraction
                        "max_tokens": 4000
                    }
                )
                
                response.raise_for_status()
                result = response.json()
            
            # Parse response
            content = result["choices"][0]["message"]["content"]
            
            # Extract JSON from response (handle markdown code blocks)
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            data = json.loads(content.strip())
            
            # Build metadata
            metadata = AvisMetadata(
                reference=data.get("reference"),
                title=data.get("title"),
                organization=data.get("organization"),
                publication_date=data.get("publication_date"),
                deadline=data.get("deadline"),
                opening_date=data.get("opening_date"),
                budget_estimate=data.get("budget_estimate"),
                caution_amount=data.get("caution_amount"),
                category=data.get("category"),
                keywords_fr=data.get("keywords_fr", []),
                keywords_ar=data.get("keywords_ar", []),
                keywords_en=data.get("keywords_en", []),
                eligibility_criteria=data.get("eligibility_criteria", []),
                submission_requirements=data.get("submission_requirements", []),
                technical_requirements=data.get("technical_requirements", []),
                required_documents=data.get("required_documents", []),
                submission_address=data.get("submission_address"),
                opening_location=data.get("opening_location"),
                lots=data.get("lots", []),
                notes=data.get("notes")
            )
            
            # Apply override rules
            
            # Rule 1: Website deadline takes precedence over document deadline
            if website_deadline:
                metadata.deadline = website_deadline.strftime("%Y-%m-%d")
            
            # Rule 2: Annex documents can override main document values
            # (This is handled at the caller level by processing order)
            
            return AnalysisResult(
                metadata=metadata,
                success=True,
                confidence=0.85,  # Base confidence for AI extraction
                source_type="annex" if is_annex else "ai"
            )
            
        except httpx.HTTPStatusError as e:
            logger.error(f"DeepSeek API error: {e.response.status_code}")
            return AnalysisResult(
                metadata=AvisMetadata(),
                success=False,
                error=f"DeepSeek API error: {e.response.status_code}"
            )
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response: {e}")
            return AnalysisResult(
                metadata=AvisMetadata(),
                success=False,
                error=f"Failed to parse AI response: {e}"
            )
        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            return AnalysisResult(
                metadata=AvisMetadata(),
                success=False,
                error=str(e)
            )


# Global analyzer instance
ai_analyzer = DeepSeekAnalyzer()

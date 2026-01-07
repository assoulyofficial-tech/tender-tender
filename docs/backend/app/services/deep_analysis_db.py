"""
Deep Analysis Database Service.

Handles on-demand deep analysis when user views a tender.
Implements annex reconciliation and field provenance tracking.
"""

import json
from typing import Optional, Any
from uuid import UUID
from datetime import datetime
from dataclasses import asdict

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.tender import (
    Tender, TenderDocument, TenderField, ProcessingState,
    FieldSource, OCRStatus, DocumentType
)
from app.services.deep_analyzer import DeepAnalyzer, UniversalFields


class DeepAnalysisDBService:
    """
    Service for on-demand deep analysis.
    
    Triggered when user opens a tender (not background).
    Implements:
    - Annex reconciliation: Annex values can override main document
    - Field provenance tracking: Source document tracked for each field
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.analyzer = DeepAnalyzer()
    
    def is_configured(self) -> bool:
        """Check if DeepSeek API is configured."""
        return self.analyzer.is_configured()
    
    def needs_deep_analysis(self, tender_id: UUID) -> bool:
        """
        Check if tender needs deep analysis.
        
        Returns True if:
        - Has extracted text
        - No deep_analysis field exists yet
        """
        tender = self.db.query(Tender).filter(Tender.id == tender_id).first()
        if not tender:
            return False
        
        # Check for existing deep analysis
        existing = self.db.query(TenderField).filter(
            and_(
                TenderField.tender_id == tender_id,
                TenderField.field_name == "deep_analysis"
            )
        ).first()
        
        if existing:
            return False
        
        # Check if has extracted documents
        docs_with_text = self.db.query(TenderDocument).filter(
            and_(
                TenderDocument.tender_id == tender_id,
                TenderDocument.extracted_text.isnot(None),
                TenderDocument.ocr_status == OCRStatus.COMPLETED
            )
        ).count()
        
        return docs_with_text > 0
    
    def get_deep_analysis(self, tender_id: UUID) -> Optional[dict]:
        """
        Get existing deep analysis results.
        
        Returns None if not yet analyzed.
        """
        field = self.db.query(TenderField).filter(
            and_(
                TenderField.tender_id == tender_id,
                TenderField.field_name == "deep_analysis"
            )
        ).first()
        
        if field:
            try:
                return json.loads(field.field_value)
            except json.JSONDecodeError:
                return None
        
        return None
    
    async def perform_deep_analysis(self, tender_id: UUID) -> dict:
        """
        Perform on-demand deep analysis for a tender.
        
        This is triggered when user opens the tender detail page.
        NOT a background job - runs synchronously on request.
        
        Args:
            tender_id: Tender UUID
            
        Returns:
            Analysis results with provenance info
        """
        tender = self.db.query(Tender).filter(Tender.id == tender_id).first()
        if not tender:
            return {"error": "Tender not found"}
        
        # Get all documents with extracted text
        documents = self.db.query(TenderDocument).filter(
            and_(
                TenderDocument.tender_id == tender_id,
                TenderDocument.extracted_text.isnot(None),
                TenderDocument.ocr_status == OCRStatus.COMPLETED
            )
        ).all()
        
        if not documents:
            return {"error": "No extracted text available for analysis"}
        
        # Check if API is configured
        if not self.is_configured():
            return {"error": "DeepSeek API key not configured"}
        
        # Get existing Avis metadata for context
        existing_metadata = self._get_existing_metadata(tender_id)
        
        # Prepare documents with annex identification
        doc_list = []
        for doc in documents:
            is_annex = self._is_annex_document(doc)
            doc_list.append({
                "id": str(doc.id),
                "filename": doc.filename,
                "content": doc.extracted_text,
                "is_annex": is_annex,
                "document_type": doc.file_type.value if doc.file_type else "unknown"
            })
        
        # Sort: main documents first, annexes last (for override logic)
        doc_list.sort(key=lambda x: x["is_annex"])
        
        # Perform deep analysis
        try:
            result = await self.analyzer.analyze_documents(
                documents=doc_list,
                existing_metadata=existing_metadata
            )
        except Exception as e:
            return {"error": f"Analysis failed: {str(e)}"}
        
        # Store results with provenance
        fields_stored = self._store_deep_analysis(tender_id, result, doc_list)
        
        # Update processing state
        self._update_processing_state(tender_id)
        
        return {
            "status": "completed",
            "tender_id": str(tender_id),
            "reference": tender.reference,
            "fields_extracted": fields_stored,
            "lots_found": len(result.lots),
            "has_execution_dates": result.execution_dates is not None,
            "confidence_score": result.confidence_score,
            "analysis": self.analyzer.to_dict(result)
        }
    
    def _is_annex_document(self, doc: TenderDocument) -> bool:
        """
        Determine if document is an annex/attachment.
        
        Annexes can override main document values.
        """
        filename_lower = doc.filename.lower()
        
        annex_indicators = [
            "annex", "annexe", "attachment", "piece_jointe",
            "cahier_des_charges", "cdc", "cctp", "ccap",
            "bordereau", "dpgf", "bpu", "dqe",
            "reglement", "rc_", "cps", "cpc"
        ]
        
        for indicator in annex_indicators:
            if indicator in filename_lower:
                return True
        
        return False
    
    def _get_existing_metadata(self, tender_id: UUID) -> Optional[dict]:
        """Get previously extracted Avis metadata."""
        fields = self.db.query(TenderField).filter(
            TenderField.tender_id == tender_id
        ).all()
        
        if not fields:
            return None
        
        metadata = {}
        for field in fields:
            if field.field_name != "deep_analysis":
                metadata[field.field_name] = {
                    "value": field.field_value,
                    "source": field.source.value if field.source else "unknown",
                    "confidence": field.confidence
                }
        
        return metadata if metadata else None
    
    def _store_deep_analysis(
        self,
        tender_id: UUID,
        result: UniversalFields,
        documents: list[dict]
    ) -> int:
        """
        Store deep analysis results with provenance tracking.
        
        Implements annex reconciliation:
        - Main document values are base
        - Annex values can override specific fields
        """
        fields_stored = 0
        analysis_dict = self.analyzer.to_dict(result)
        
        # Find primary source document (first non-annex with content)
        primary_doc_id = None
        for doc in documents:
            if not doc["is_annex"]:
                primary_doc_id = doc["id"]
                break
        if not primary_doc_id and documents:
            primary_doc_id = documents[0]["id"]
        
        # Store complete analysis as JSON field
        self._store_field(
            tender_id=tender_id,
            field_name="deep_analysis",
            field_value=json.dumps(analysis_dict, default=str),
            field_type="json",
            source=FieldSource.AI,
            confidence=result.confidence_score,
            document_id=primary_doc_id,
            source_location="deep_analysis"
        )
        fields_stored += 1
        
        # Store individual important fields for easy querying
        field_mappings = [
            ("contract_type", result.contract_type, "text"),
            ("procedure_type", result.procedure_type, "text"),
            ("award_criteria", result.award_criteria, "text"),
            ("payment_terms", result.payment_terms, "text"),
            ("bid_guarantee", str(result.bid_guarantee) if result.bid_guarantee else None, "number"),
            ("performance_guarantee", str(result.performance_guarantee) if result.performance_guarantee else None, "number"),
            ("minimum_experience_years", str(result.minimum_experience_years) if result.minimum_experience_years else None, "number"),
            ("minimum_turnover", str(result.minimum_turnover) if result.minimum_turnover else None, "number"),
            ("subcontracting_allowed", str(result.subcontracting_allowed).lower(), "boolean"),
            ("site_visit_required", str(result.site_visit_required).lower(), "boolean"),
            ("site_visit_date", result.site_visit_date, "date"),
            ("clarification_deadline", result.clarification_deadline, "date"),
        ]
        
        for field_name, field_value, field_type in field_mappings:
            if field_value:
                self._store_field(
                    tender_id=tender_id,
                    field_name=f"deep_{field_name}",
                    field_value=field_value,
                    field_type=field_type,
                    source=FieldSource.AI,
                    confidence=result.confidence_score,
                    document_id=primary_doc_id,
                    source_location="deep_analysis"
                )
                fields_stored += 1
        
        # Store lots if present
        if result.lots:
            self._store_field(
                tender_id=tender_id,
                field_name="lots",
                field_value=json.dumps([asdict(lot) for lot in result.lots], default=str),
                field_type="json",
                source=FieldSource.AI,
                confidence=result.confidence_score,
                document_id=primary_doc_id,
                source_location="deep_analysis"
            )
            fields_stored += 1
        
        # Store execution dates if present
        if result.execution_dates:
            self._store_field(
                tender_id=tender_id,
                field_name="execution_dates",
                field_value=json.dumps(asdict(result.execution_dates), default=str),
                field_type="json",
                source=FieldSource.AI,
                confidence=result.confidence_score,
                document_id=primary_doc_id,
                source_location="deep_analysis"
            )
            fields_stored += 1
        
        # Store technical requirements as list
        if result.technical_specifications:
            self._store_field(
                tender_id=tender_id,
                field_name="technical_specifications",
                field_value=json.dumps(result.technical_specifications),
                field_type="list",
                source=FieldSource.AI,
                confidence=result.confidence_score,
                document_id=primary_doc_id,
                source_location="deep_analysis"
            )
            fields_stored += 1
        
        # Store quality standards
        if result.quality_standards:
            self._store_field(
                tender_id=tender_id,
                field_name="quality_standards",
                field_value=json.dumps(result.quality_standards),
                field_type="list",
                source=FieldSource.AI,
                confidence=result.confidence_score,
                document_id=primary_doc_id,
                source_location="deep_analysis"
            )
            fields_stored += 1
        
        # Store required certifications
        if result.required_certifications:
            self._store_field(
                tender_id=tender_id,
                field_name="required_certifications",
                field_value=json.dumps(result.required_certifications),
                field_type="list",
                source=FieldSource.AI,
                confidence=result.confidence_score,
                document_id=primary_doc_id,
                source_location="deep_analysis"
            )
            fields_stored += 1
        
        self.db.commit()
        return fields_stored
    
    def _store_field(
        self,
        tender_id: UUID,
        field_name: str,
        field_value: str,
        field_type: str,
        source: FieldSource,
        confidence: float,
        document_id: Optional[str],
        source_location: str
    ):
        """Store or update a field with provenance."""
        # Check for existing field
        existing = self.db.query(TenderField).filter(
            and_(
                TenderField.tender_id == tender_id,
                TenderField.field_name == field_name
            )
        ).first()
        
        if existing:
            # Update existing
            existing.field_value = field_value
            existing.field_type = field_type
            existing.source = source
            existing.confidence = confidence
            existing.source_location = source_location
            existing.updated_at = datetime.utcnow()
            if document_id:
                existing.document_id = UUID(document_id)
        else:
            # Create new
            field = TenderField(
                tender_id=tender_id,
                document_id=UUID(document_id) if document_id else None,
                field_name=field_name,
                field_value=field_value,
                field_type=field_type,
                source=source,
                confidence=confidence,
                source_location=source_location
            )
            self.db.add(field)
    
    def _update_processing_state(self, tender_id: UUID):
        """Update processing state to reflect deep analysis completion."""
        state = self.db.query(ProcessingState).filter(
            ProcessingState.tender_id == tender_id
        ).first()
        
        if state:
            state.ai_analyzed = True
            state.ai_analyzed_at = datetime.utcnow()
            state.updated_at = datetime.utcnow()
        
        self.db.commit()

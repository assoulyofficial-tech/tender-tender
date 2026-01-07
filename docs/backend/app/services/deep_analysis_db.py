"""
AI Process 2 Database Service - Universal Deep Analysis.

On-demand analysis when user opens a tender.
Extracts full operational, financial, and technical structure.
"""

import json
from typing import Optional
from uuid import UUID
from datetime import datetime
from dataclasses import asdict

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.tender import (
    Tender, TenderDocument, TenderField, ProcessingState,
    FieldSource, OCRStatus
)
from app.services.deep_analyzer import DeepAnalyzer, UniversalFields
from app.services.ai_analyzer import DocumentType, DOCUMENT_DETECTION_KEYWORDS


class DeepAnalysisDBService:
    """
    AI Process 2 - Universal Deep Analysis with DB integration.
    
    User Shift operation (on click only).
    This is expensive and must only run on user intent.
    
    Implements:
    - Document priority ordering
    - Full lot/item extraction
    - Caution computation rules
    - Verbatim technical descriptions
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.analyzer = DeepAnalyzer()
    
    def is_configured(self) -> bool:
        """Check if AI is configured."""
        return self.analyzer.is_configured()
    
    def needs_deep_analysis(self, tender_id: UUID) -> bool:
        """Check if tender needs deep analysis."""
        tender = self.db.query(Tender).filter(Tender.id == tender_id).first()
        if not tender:
            return False
        
        existing = self.db.query(TenderField).filter(
            and_(
                TenderField.tender_id == tender_id,
                TenderField.field_name == "universal_analysis"
            )
        ).first()
        
        if existing:
            return False
        
        docs_with_text = self.db.query(TenderDocument).filter(
            and_(
                TenderDocument.tender_id == tender_id,
                TenderDocument.extracted_text.isnot(None),
                TenderDocument.ocr_status == OCRStatus.COMPLETED
            )
        ).count()
        
        return docs_with_text > 0
    
    def get_deep_analysis(self, tender_id: UUID) -> Optional[dict]:
        """Get existing deep analysis results."""
        field = self.db.query(TenderField).filter(
            and_(
                TenderField.tender_id == tender_id,
                TenderField.field_name == "universal_analysis"
            )
        ).first()
        
        if field:
            try:
                return json.loads(field.field_value)
            except json.JSONDecodeError:
                return None
        
        return None
    
    def _classify_document(self, first_page: str) -> str:
        """Classify document by content keywords."""
        text_lower = first_page.lower()
        
        for doc_type, keywords in DOCUMENT_DETECTION_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return doc_type.value
        
        return "unknown"
    
    async def perform_deep_analysis(self, tender_id: UUID) -> dict:
        """
        Perform Universal Deep Analysis.
        
        This is triggered when user opens tender detail.
        NOT a background job.
        """
        tender = self.db.query(Tender).filter(Tender.id == tender_id).first()
        if not tender:
            return {"error": "Tender not found"}
        
        documents = self.db.query(TenderDocument).filter(
            and_(
                TenderDocument.tender_id == tender_id,
                TenderDocument.extracted_text.isnot(None),
                TenderDocument.ocr_status == OCRStatus.COMPLETED
            )
        ).all()
        
        if not documents:
            return {"error": "No extracted text available"}
        
        if not self.is_configured():
            return {"error": "DeepSeek API key not configured"}
        
        # Prepare documents with classification
        doc_list = []
        for doc in documents:
            first_page = (doc.extracted_text or "")[:3000]
            doc_type = self._classify_document(first_page)
            
            doc_list.append({
                "id": str(doc.id),
                "filename": doc.filename,
                "content": doc.extracted_text,
                "doc_type": doc_type
            })
        
        # Get existing Avis metadata for reference
        existing_avis = self._get_avis_metadata(tender_id)
        
        # Perform analysis
        try:
            result = await self.analyzer.analyze_documents(
                documents=doc_list,
                existing_avis=existing_avis
            )
        except Exception as e:
            return {"error": f"Analysis failed: {str(e)}"}
        
        # Store results
        fields_stored = self._store_analysis(tender_id, result, doc_list)
        
        # Count lots and items
        total_lots = len(result.lots)
        total_items = sum(len(lot.items) for lot in result.lots)
        
        return {
            "status": "completed",
            "tender_id": str(tender_id),
            "reference": tender.reference,
            "fields_extracted": fields_stored,
            "lots_found": total_lots,
            "items_found": total_items,
            "has_execution_dates": any(lot.execution_date for lot in result.lots),
            "confidence_score": 0.9,
            "analysis": self.analyzer.to_dict(result)
        }
    
    def _get_avis_metadata(self, tender_id: UUID) -> Optional[dict]:
        """Get Avis metadata for reference."""
        field = self.db.query(TenderField).filter(
            and_(
                TenderField.tender_id == tender_id,
                TenderField.field_name == "avis_metadata"
            )
        ).first()
        
        if field:
            try:
                return json.loads(field.field_value)
            except json.JSONDecodeError:
                return None
        
        return None
    
    def _store_analysis(
        self,
        tender_id: UUID,
        result: UniversalFields,
        documents: list[dict]
    ) -> int:
        """Store Universal Deep Analysis results."""
        fields_stored = 0
        
        # Find primary document (CPS preferred)
        primary_doc_id = None
        for doc in documents:
            if doc.get("doc_type") == "cps":
                primary_doc_id = doc["id"]
                break
        if not primary_doc_id:
            for doc in documents:
                if doc.get("doc_type") == "rc":
                    primary_doc_id = doc["id"]
                    break
        if not primary_doc_id and documents:
            primary_doc_id = documents[0]["id"]
        
        # Store complete analysis
        analysis_dict = self.analyzer.to_dict(result)
        self._store_field(
            tender_id=tender_id,
            field_name="universal_analysis",
            field_value=json.dumps(analysis_dict, default=str),
            field_type="json",
            source=FieldSource.AI,
            confidence=0.9,
            document_id=primary_doc_id,
            source_location="universal_deep_analysis"
        )
        fields_stored += 1
        
        # Store key fields individually for querying
        simple_fields = [
            ("deep_reference_tender", result.reference_tender),
            ("deep_tender_type", result.tender_type),
            ("deep_issuing_institution", result.issuing_institution),
            ("deep_institution_address", result.institution_address),
            ("deep_folder_opening_location", result.folder_opening_location),
            ("deep_subject", result.subject),
        ]
        
        for field_name, value in simple_fields:
            if value:
                self._store_field(
                    tender_id=tender_id,
                    field_name=field_name,
                    field_value=str(value),
                    field_type="text",
                    source=FieldSource.AI,
                    confidence=0.9,
                    document_id=primary_doc_id,
                    source_location="universal_deep_analysis"
                )
                fields_stored += 1
        
        # Store estimated value
        if result.total_estimated_value:
            self._store_field(
                tender_id=tender_id,
                field_name="deep_total_estimated_value",
                field_value=str(result.total_estimated_value),
                field_type="number",
                source=FieldSource.AI,
                confidence=0.9,
                document_id=primary_doc_id,
                source_location="universal_deep_analysis"
            )
            fields_stored += 1
        
        # Store submission deadline
        if result.submission_deadline.date:
            self._store_field(
                tender_id=tender_id,
                field_name="deep_submission_deadline_date",
                field_value=result.submission_deadline.date,
                field_type="date",
                source=FieldSource.AI,
                confidence=0.9,
                document_id=primary_doc_id,
                source_location="universal_deep_analysis"
            )
            fields_stored += 1
        
        if result.submission_deadline.time:
            self._store_field(
                tender_id=tender_id,
                field_name="deep_submission_deadline_time",
                field_value=result.submission_deadline.time,
                field_type="text",
                source=FieldSource.AI,
                confidence=0.9,
                document_id=primary_doc_id,
                source_location="universal_deep_analysis"
            )
            fields_stored += 1
        
        # Store lots with full structure (including items)
        if result.lots:
            self._store_field(
                tender_id=tender_id,
                field_name="universal_lots",
                field_value=json.dumps([asdict(lot) for lot in result.lots], default=str),
                field_type="json",
                source=FieldSource.AI,
                confidence=0.9,
                document_id=primary_doc_id,
                source_location="universal_deep_analysis"
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
        """Store or update a field."""
        existing = self.db.query(TenderField).filter(
            and_(
                TenderField.tender_id == tender_id,
                TenderField.field_name == field_name
            )
        ).first()
        
        if existing:
            existing.field_value = field_value
            existing.field_type = field_type
            existing.source = source
            existing.confidence = confidence
            existing.source_location = source_location
            existing.updated_at = datetime.utcnow()
            if document_id:
                existing.document_id = UUID(document_id)
        else:
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
        """Update processing state for deep analysis."""
        state = self.db.query(ProcessingState).filter(
            ProcessingState.tender_id == tender_id
        ).first()
        
        if state:
            state.updated_at = datetime.utcnow()
        
        self.db.commit()

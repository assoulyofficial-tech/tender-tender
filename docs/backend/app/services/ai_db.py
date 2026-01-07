"""
AI Process 1 Database Service.

Integrates Avis Metadata Extraction with database.
Handles document classification, annex override, and website deadline override.
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
from app.services.ai_analyzer import (
    AvisExtractor, AvisMetadata, DocumentType
)


class AIDBService:
    """
    AI Process 1 - Avis Metadata Extraction with DB integration.
    
    Night Shift operation for minimal cost.
    Implements:
    - Document classification by keywords
    - Annex override logic
    - Website deadline override
    - Full provenance tracking
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.extractor = AvisExtractor()
    
    def is_configured(self) -> bool:
        """Check if AI is configured."""
        return self.extractor.is_configured()
    
    async def analyze_tender(
        self,
        tender_id: UUID,
        website_deadline: Optional[dict] = None
    ) -> dict:
        """
        Extract Avis metadata for a tender.
        
        Args:
            tender_id: Tender UUID
            website_deadline: Optional {date, time} from website
            
        Returns:
            Analysis summary with provenance
        """
        tender = self.db.query(Tender).filter(Tender.id == tender_id).first()
        if not tender:
            return {"error": "Tender not found"}
        
        # Get documents with extracted text
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
        
        # Prepare documents for extraction
        doc_list = []
        for doc in documents:
            # Classify by content keywords
            first_page = (doc.extracted_text or "")[:3000]
            doc_type = self.extractor.classify_document(first_page)
            
            doc_list.append({
                "id": str(doc.id),
                "filename": doc.filename,
                "content": doc.extracted_text,
                "doc_type": doc_type,
                "position": len(doc_list)  # For sorting
            })
        
        # Build website deadline if available from tender
        if not website_deadline and tender.deadline:
            website_deadline = {
                "date": tender.deadline.strftime("%d/%m/%Y"),
                "time": tender.deadline.strftime("%H:%M")
            }
        
        # Extract metadata
        try:
            metadata = await self.extractor.extract_metadata(
                documents=doc_list,
                website_deadline=website_deadline
            )
        except Exception as e:
            return {"error": f"Extraction failed: {str(e)}"}
        
        # Store results
        fields_stored = self._store_metadata(tender_id, metadata, doc_list)
        
        # Update processing state
        self._update_processing_state(tender_id)
        
        return {
            "status": "completed",
            "reference": tender.reference,
            "documents_analyzed": len(doc_list),
            "fields_extracted": fields_stored,
            "errors": []
        }
    
    def _store_metadata(
        self,
        tender_id: UUID,
        metadata: AvisMetadata,
        documents: list[dict]
    ) -> int:
        """Store Avis metadata with provenance tracking."""
        fields_stored = 0
        
        # Get primary document ID
        primary_doc_id = None
        for doc in documents:
            if doc.get("doc_type") == DocumentType.AVIS:
                primary_doc_id = doc["id"]
                break
        if not primary_doc_id and documents:
            primary_doc_id = documents[0]["id"]
        
        # Store complete metadata as JSON
        metadata_dict = self.extractor.to_dict(metadata)
        self._store_field(
            tender_id=tender_id,
            field_name="avis_metadata",
            field_value=json.dumps(metadata_dict, default=str),
            field_type="json",
            source=FieldSource.AI,
            confidence=0.9,
            document_id=primary_doc_id,
            source_location="avis_extraction"
        )
        fields_stored += 1
        
        # Store individual provenance fields
        provenance_fields = [
            ("reference_tender", metadata.reference_tender),
            ("tender_type", metadata.tender_type),
            ("issuing_institution", metadata.issuing_institution),
            ("folder_opening_location", metadata.folder_opening_location),
            ("subject", metadata.subject),
            ("total_estimated_value", metadata.total_estimated_value),
        ]
        
        for field_name, prov_field in provenance_fields:
            if prov_field and prov_field.value:
                doc_id = self._find_doc_id(prov_field.source_document, documents) or primary_doc_id
                self._store_field(
                    tender_id=tender_id,
                    field_name=f"avis_{field_name}",
                    field_value=str(prov_field.value),
                    field_type="text",
                    source=FieldSource.AI,
                    confidence=0.9,
                    document_id=doc_id,
                    source_location=prov_field.source_document
                )
                fields_stored += 1
        
        # Store submission deadline
        if metadata.submission_deadline.date.value:
            doc_id = self._find_doc_id(
                metadata.submission_deadline.date.source_document, documents
            ) or primary_doc_id
            self._store_field(
                tender_id=tender_id,
                field_name="avis_submission_deadline_date",
                field_value=metadata.submission_deadline.date.value,
                field_type="date",
                source=FieldSource.AI,
                confidence=0.95 if metadata.submission_deadline.date.source_document == "Website" else 0.9,
                document_id=doc_id,
                source_location=metadata.submission_deadline.date.source_document
            )
            fields_stored += 1
        
        if metadata.submission_deadline.time.value:
            self._store_field(
                tender_id=tender_id,
                field_name="avis_submission_deadline_time",
                field_value=metadata.submission_deadline.time.value,
                field_type="text",
                source=FieldSource.AI,
                confidence=0.95 if metadata.submission_deadline.time.source_document == "Website" else 0.9,
                document_id=primary_doc_id,
                source_location=metadata.submission_deadline.time.source_document
            )
            fields_stored += 1
        
        # Store lots
        if metadata.lots:
            self._store_field(
                tender_id=tender_id,
                field_name="avis_lots",
                field_value=json.dumps([asdict(lot) for lot in metadata.lots], default=str),
                field_type="json",
                source=FieldSource.AI,
                confidence=0.9,
                document_id=primary_doc_id,
                source_location="avis_extraction"
            )
            fields_stored += 1
        
        # Store keywords (CRITICAL for search)
        if metadata.keywords:
            self._store_field(
                tender_id=tender_id,
                field_name="keywords_fr",
                field_value=json.dumps(metadata.keywords.keywords_fr),
                field_type="list",
                source=FieldSource.AI,
                confidence=0.85,
                document_id=primary_doc_id,
                source_location="avis_extraction"
            )
            self._store_field(
                tender_id=tender_id,
                field_name="keywords_eng",
                field_value=json.dumps(metadata.keywords.keywords_eng),
                field_type="list",
                source=FieldSource.AI,
                confidence=0.85,
                document_id=primary_doc_id,
                source_location="avis_extraction"
            )
            self._store_field(
                tender_id=tender_id,
                field_name="keywords_ar",
                field_value=json.dumps(metadata.keywords.keywords_ar),
                field_type="list",
                source=FieldSource.AI,
                confidence=0.85,
                document_id=primary_doc_id,
                source_location="avis_extraction"
            )
            fields_stored += 3
        
        self.db.commit()
        return fields_stored
    
    def _find_doc_id(self, source_document: Optional[str], documents: list[dict]) -> Optional[str]:
        """Find document ID by source name."""
        if not source_document or source_document == "Website":
            return None
        
        for doc in documents:
            if source_document.lower() in doc["filename"].lower():
                return doc["id"]
        
        return None
    
    def _store_field(
        self,
        tender_id: UUID,
        field_name: str,
        field_value: str,
        field_type: str,
        source: FieldSource,
        confidence: float,
        document_id: Optional[str],
        source_location: Optional[str]
    ):
        """Store or update a field with provenance."""
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
        """Update processing state."""
        state = self.db.query(ProcessingState).filter(
            ProcessingState.tender_id == tender_id
        ).first()
        
        if state:
            state.ai_analyzed = True
            state.ai_analyzed_at = datetime.utcnow()
            state.updated_at = datetime.utcnow()
        
        self.db.commit()
    
    async def analyze_pending_tenders(self, limit: int = 10) -> dict:
        """Analyze tenders with extracted text but no AI analysis."""
        # Find pending tenders
        pending = self.db.query(Tender).join(ProcessingState).filter(
            and_(
                ProcessingState.text_extracted == True,
                ProcessingState.ai_analyzed == False
            )
        ).limit(limit).all()
        
        results = {
            "total_pending": len(pending),
            "analyzed": 0,
            "errors": []
        }
        
        for tender in pending:
            try:
                result = await self.analyze_tender(tender.id)
                if "error" not in result:
                    results["analyzed"] += 1
                else:
                    results["errors"].append(f"{tender.reference}: {result['error']}")
            except Exception as e:
                results["errors"].append(f"{tender.reference}: {str(e)}")
        
        return results

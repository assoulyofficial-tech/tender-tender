"""
Database integration for AI analysis.
Stores extracted metadata in tender_fields with provenance tracking.
"""

import json
from datetime import datetime
from uuid import UUID
from typing import Optional
from sqlalchemy.orm import Session

from app.models import (
    Tender,
    TenderDocument,
    TenderField,
    ProcessingState,
    FieldSource,
    ProcessingStatus,
    DocumentType,
)
from app.services.ai_analyzer import DeepSeekAnalyzer, AvisMetadata, AnalysisResult


class AIDBService:
    """Service to run AI analysis and store results."""
    
    def __init__(self, db: Session):
        self.db = db
        self.analyzer = DeepSeekAnalyzer()
    
    def is_configured(self) -> bool:
        """Check if AI is properly configured."""
        return self.analyzer.is_configured()
    
    async def analyze_tender(self, tender_id: UUID) -> dict:
        """
        Analyze all documents for a tender and store extracted metadata.
        
        Implements:
        - Annex override logic: Annex documents override main document values
        - Website deadline override: Website deadline takes precedence
        
        Args:
            tender_id: Tender UUID
            
        Returns:
            Analysis summary
        """
        tender = self.db.query(Tender).filter(Tender.id == tender_id).first()
        if not tender:
            return {"error": f"Tender not found: {tender_id}"}
        
        if not self.is_configured():
            return {"error": "DeepSeek API key not configured. Set DEEPSEEK_API_KEY in .env"}
        
        # Update processing state
        state = tender.processing_state
        if state:
            state.status = ProcessingStatus.ANALYZING
            state.current_step = "ai_extraction"
            state.analysis_started_at = datetime.utcnow()
            self.db.commit()
        
        results = {
            "tender_id": str(tender_id),
            "reference": tender.reference,
            "documents_analyzed": 0,
            "fields_extracted": 0,
            "errors": [],
        }
        
        # Get website deadline (takes precedence)
        website_deadline = tender.deadline
        
        # Process documents in order: main documents first, then annexes
        # Annexes can override main document values
        main_docs = [d for d in tender.documents if d.file_type != DocumentType.ANNEXE]
        annex_docs = [d for d in tender.documents if d.file_type == DocumentType.ANNEXE]
        
        combined_metadata = AvisMetadata()
        
        # Process main documents
        for doc in main_docs:
            if not doc.extracted_text:
                continue
            
            doc_result = await self._analyze_document(
                doc,
                website_deadline=website_deadline,
                is_annex=False
            )
            
            if doc_result.success:
                self._merge_metadata(combined_metadata, doc_result.metadata)
                results["documents_analyzed"] += 1
            else:
                results["errors"].append(f"{doc.filename}: {doc_result.error}")
        
        # Process annexes (can override)
        for doc in annex_docs:
            if not doc.extracted_text:
                continue
            
            doc_result = await self._analyze_document(
                doc,
                website_deadline=website_deadline,
                is_annex=True
            )
            
            if doc_result.success:
                # Annex values override (merge with priority)
                self._merge_metadata(combined_metadata, doc_result.metadata, override=True)
                results["documents_analyzed"] += 1
            else:
                results["errors"].append(f"{doc.filename}: {doc_result.error}")
        
        # Store extracted fields
        fields_count = self._store_metadata(tender_id, combined_metadata)
        results["fields_extracted"] = fields_count
        
        # Update tender with extracted data
        self._update_tender(tender, combined_metadata, website_deadline)
        
        # Update processing state
        if state:
            state.analysis_completed_at = datetime.utcnow()
            state.status = ProcessingStatus.COMPLETED if not results["errors"] else ProcessingStatus.FAILED
            state.progress = 100.0
            self.db.commit()
        
        return results
    
    async def _analyze_document(
        self,
        doc: TenderDocument,
        website_deadline: Optional[datetime],
        is_annex: bool
    ) -> AnalysisResult:
        """Analyze a single document."""
        return await self.analyzer.analyze_document(
            document_text=doc.extracted_text,
            website_deadline=website_deadline,
            is_annex=is_annex
        )
    
    def _merge_metadata(
        self,
        target: AvisMetadata,
        source: AvisMetadata,
        override: bool = False
    ):
        """
        Merge source metadata into target.
        
        Args:
            target: Target metadata to update
            source: Source metadata to merge from
            override: If True, source values always override target
        """
        # Simple fields - override if set and (empty target or override flag)
        simple_fields = [
            'reference', 'title', 'organization', 'publication_date',
            'deadline', 'opening_date', 'budget_estimate', 'caution_amount',
            'category', 'submission_address', 'opening_location', 'notes'
        ]
        
        for field in simple_fields:
            source_val = getattr(source, field)
            target_val = getattr(target, field)
            
            if source_val is not None:
                if target_val is None or override:
                    setattr(target, field, source_val)
        
        # List fields - extend (avoid duplicates)
        list_fields = [
            'keywords_fr', 'keywords_ar', 'keywords_en',
            'eligibility_criteria', 'submission_requirements',
            'technical_requirements', 'required_documents'
        ]
        
        for field in list_fields:
            source_list = getattr(source, field, [])
            target_list = getattr(target, field, [])
            
            for item in source_list:
                if item not in target_list:
                    target_list.append(item)
        
        # Lots - extend
        for lot in source.lots:
            if lot not in target.lots:
                target.lots.append(lot)
    
    def _store_metadata(self, tender_id: UUID, metadata: AvisMetadata) -> int:
        """Store extracted metadata as TenderField records."""
        # Delete existing AI-extracted fields
        self.db.query(TenderField).filter(
            TenderField.tender_id == tender_id,
            TenderField.source == FieldSource.AI
        ).delete()
        
        count = 0
        
        # Helper to create field
        def add_field(name: str, value, field_type: str = "text", confidence: float = 0.85):
            nonlocal count
            if value is None:
                return
            if isinstance(value, list) and len(value) == 0:
                return
            
            str_value = json.dumps(value) if isinstance(value, (list, dict)) else str(value)
            
            field = TenderField(
                tender_id=tender_id,
                field_name=name,
                field_value=str_value,
                field_type=field_type,
                source=FieldSource.AI,
                confidence=confidence,
                is_verified=False
            )
            self.db.add(field)
            count += 1
        
        # Store all fields
        add_field("keywords_fr", metadata.keywords_fr, "list")
        add_field("keywords_ar", metadata.keywords_ar, "list")
        add_field("keywords_en", metadata.keywords_en, "list")
        add_field("eligibility_criteria", metadata.eligibility_criteria, "list")
        add_field("submission_requirements", metadata.submission_requirements, "list")
        add_field("technical_requirements", metadata.technical_requirements, "list")
        add_field("required_documents", metadata.required_documents, "list")
        add_field("submission_address", metadata.submission_address)
        add_field("opening_location", metadata.opening_location)
        add_field("lots", metadata.lots, "json")
        add_field("notes", metadata.notes)
        
        self.db.commit()
        return count
    
    def _update_tender(
        self,
        tender: Tender,
        metadata: AvisMetadata,
        website_deadline: Optional[datetime]
    ):
        """Update tender record with extracted data."""
        # Only update if we got new info and it wasn't already set
        if metadata.title and not tender.title:
            tender.title = metadata.title
        
        if metadata.organization and not tender.organization:
            tender.organization = metadata.organization
        
        if metadata.budget_estimate and not tender.budget_estimate:
            tender.budget_estimate = metadata.budget_estimate
        
        if metadata.caution_amount and not tender.caution_amount:
            tender.caution_amount = metadata.caution_amount
        
        # Deadline: Website takes precedence, then AI extraction
        if website_deadline:
            tender.deadline = website_deadline
        elif metadata.deadline and not tender.deadline:
            try:
                tender.deadline = datetime.strptime(metadata.deadline, "%Y-%m-%d")
            except ValueError:
                pass
        
        # Opening date from AI if not set
        if metadata.opening_date and not tender.opening_date:
            try:
                tender.opening_date = datetime.strptime(metadata.opening_date, "%Y-%m-%d")
            except ValueError:
                pass
        
        tender.updated_at = datetime.utcnow()
        self.db.commit()
    
    async def analyze_pending_tenders(self, limit: int = 10) -> dict:
        """
        Analyze tenders that have extracted text but no AI analysis.
        
        Args:
            limit: Maximum tenders to process
            
        Returns:
            Summary of results
        """
        # Find tenders with documents that have text but no AI fields
        tenders_with_text = (
            self.db.query(Tender)
            .join(TenderDocument)
            .filter(TenderDocument.extracted_text.isnot(None))
            .limit(limit)
            .all()
        )
        
        # Filter to those without AI analysis
        pending = []
        for tender in tenders_with_text:
            has_ai_fields = self.db.query(TenderField).filter(
                TenderField.tender_id == tender.id,
                TenderField.source == FieldSource.AI
            ).first()
            
            if not has_ai_fields:
                pending.append(tender)
        
        results = {
            "total_pending": len(pending),
            "analyzed": 0,
            "errors": [],
        }
        
        for tender in pending[:limit]:
            try:
                result = await self.analyze_tender(tender.id)
                if "error" not in result:
                    results["analyzed"] += 1
                else:
                    results["errors"].append(f"{tender.reference}: {result['error']}")
            except Exception as e:
                results["errors"].append(f"{tender.reference}: {str(e)}")
        
        return results

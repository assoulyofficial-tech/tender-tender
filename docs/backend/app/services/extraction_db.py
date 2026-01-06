"""
Database integration for text extraction.
Stores extracted text in PostgreSQL.
"""

from datetime import datetime
from uuid import UUID
from sqlalchemy.orm import Session

from app.models import (
    Tender,
    TenderDocument,
    ProcessingState,
    OCRStatus,
    ProcessingStatus,
)
from app.services.extractor import TextExtractor, ExtractionResult, ExtractionMethod
from app.services.scraper_db import document_store


class ExtractionDBService:
    """Service to extract text and update database."""
    
    def __init__(self, db: Session):
        self.db = db
        self.extractor = TextExtractor()
    
    def process_tender(self, tender_id: UUID) -> dict:
        """
        Process all documents for a tender.
        
        Args:
            tender_id: Tender UUID
            
        Returns:
            Summary of extraction results
        """
        tender = self.db.query(Tender).filter(Tender.id == tender_id).first()
        if not tender:
            return {"error": f"Tender not found: {tender_id}"}
        
        # Update processing state
        state = tender.processing_state
        if state:
            state.status = ProcessingStatus.OCR
            state.current_step = "text_extraction"
            state.ocr_started_at = datetime.utcnow()
            self.db.commit()
        
        results = {
            "tender_id": str(tender_id),
            "reference": tender.reference,
            "documents": [],
            "success_count": 0,
            "error_count": 0,
        }
        
        # Process each document
        for doc in tender.documents:
            doc_result = self._process_document(tender.reference, doc)
            results["documents"].append(doc_result)
            
            if doc_result["success"]:
                results["success_count"] += 1
            else:
                results["error_count"] += 1
        
        # Update processing state
        if state:
            state.ocr_completed_at = datetime.utcnow()
            if results["error_count"] == 0:
                state.status = ProcessingStatus.COMPLETED
                state.progress = 100.0
            else:
                state.status = ProcessingStatus.FAILED if results["success_count"] == 0 else ProcessingStatus.COMPLETED
                state.progress = 80.0
            self.db.commit()
        
        return results
    
    def _process_document(self, reference: str, doc: TenderDocument) -> dict:
        """Process a single document."""
        result = {
            "document_id": str(doc.id),
            "filename": doc.filename,
            "success": False,
            "method": None,
            "text_length": 0,
            "page_count": None,
            "error": None,
        }
        
        # Update OCR status
        doc.ocr_status = OCRStatus.PROCESSING
        self.db.commit()
        
        try:
            # Get document content from memory store
            content = document_store.get(reference, doc.filename)
            
            if not content:
                # Try to download from URL if not in memory
                if doc.download_url:
                    content = self._download_document(doc.download_url)
                
                if not content:
                    raise ValueError("Document content not available")
            
            # Extract text
            extraction = self.extractor.extract(content, doc.filename)
            
            if extraction.success:
                doc.extracted_text = extraction.text
                doc.ocr_status = OCRStatus.COMPLETED
                doc.page_count = extraction.page_count
                
                result["success"] = True
                result["method"] = extraction.method.value
                result["text_length"] = len(extraction.text)
                result["page_count"] = extraction.page_count
            else:
                doc.ocr_status = OCRStatus.FAILED
                doc.ocr_error = extraction.error
                result["error"] = extraction.error
            
            self.db.commit()
            
        except Exception as e:
            doc.ocr_status = OCRStatus.FAILED
            doc.ocr_error = str(e)
            result["error"] = str(e)
            self.db.commit()
        
        return result
    
    def _download_document(self, url: str) -> bytes:
        """Download document from URL."""
        import httpx
        
        response = httpx.get(url, timeout=60.0, follow_redirects=True)
        response.raise_for_status()
        return response.content
    
    def process_pending_documents(self, limit: int = 50) -> dict:
        """
        Process all documents with pending OCR status.
        
        Args:
            limit: Maximum documents to process
            
        Returns:
            Summary of results
        """
        pending_docs = self.db.query(TenderDocument).filter(
            TenderDocument.ocr_status == OCRStatus.PENDING
        ).limit(limit).all()
        
        results = {
            "total": len(pending_docs),
            "success": 0,
            "failed": 0,
            "documents": [],
        }
        
        for doc in pending_docs:
            tender = doc.tender
            doc_result = self._process_document(tender.reference, doc)
            results["documents"].append(doc_result)
            
            if doc_result["success"]:
                results["success"] += 1
            else:
                results["failed"] += 1
        
        return results

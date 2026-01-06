"""
Database integration for scraper results.
Stores scraped tenders and documents in PostgreSQL.
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4
from sqlalchemy.orm import Session

from app.models import (
    Tender,
    TenderDocument,
    ProcessingState,
    TenderStatus,
    DocumentType,
    OCRStatus,
    ProcessingStatus
)
from app.services.scraper import ScrapedTender, ScrapedDocument, ScrapeResult


class ScraperDBService:
    """Service to persist scraped data to database."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def save_scrape_result(self, result: ScrapeResult) -> dict:
        """
        Save all scraped tenders to database.
        
        Returns:
            Summary dict with counts
        """
        created = 0
        updated = 0
        skipped = 0
        errors = []
        
        for scraped_tender in result.tenders:
            try:
                existing = self.db.query(Tender).filter(
                    Tender.reference == scraped_tender.reference
                ).first()
                
                if existing:
                    # Update existing tender
                    self._update_tender(existing, scraped_tender)
                    updated += 1
                else:
                    # Create new tender
                    self._create_tender(scraped_tender)
                    created += 1
                    
            except Exception as e:
                errors.append(f"Error saving {scraped_tender.reference}: {str(e)}")
                skipped += 1
        
        self.db.commit()
        
        return {
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "errors": errors,
            "total_scraped": len(result.tenders),
            "scrape_errors": result.errors
        }
    
    def _create_tender(self, scraped: ScrapedTender) -> Tender:
        """Create new tender from scraped data."""
        tender = Tender(
            id=uuid4(),
            reference=scraped.reference,
            title=scraped.title,
            organization=scraped.organization,
            category=scraped.category,
            publication_date=scraped.publication_date,
            deadline=scraped.deadline,
            opening_date=scraped.opening_date,
            budget_estimate=scraped.budget_estimate,
            caution_amount=scraped.caution_amount,
            status=TenderStatus.OPEN,
            source_url=scraped.source_url,
            source_id=scraped.source_id,
        )
        self.db.add(tender)
        self.db.flush()  # Get tender.id
        
        # Create processing state
        processing_state = ProcessingState(
            id=uuid4(),
            tender_id=tender.id,
            status=ProcessingStatus.PENDING,
            current_step="scraped",
            progress=10.0,
            scraping_completed_at=datetime.utcnow()
        )
        self.db.add(processing_state)
        
        # Add documents (metadata only - content in memory)
        for doc in scraped.documents:
            self._create_document(tender.id, doc)
        
        return tender
    
    def _update_tender(self, tender: Tender, scraped: ScrapedTender):
        """Update existing tender with new scraped data."""
        # Only update fields that might have changed
        if scraped.deadline:
            tender.deadline = scraped.deadline
        if scraped.budget_estimate:
            tender.budget_estimate = scraped.budget_estimate
        if scraped.opening_date:
            tender.opening_date = scraped.opening_date
        
        tender.updated_at = datetime.utcnow()
        
        # Check for new documents
        existing_urls = {doc.download_url for doc in tender.documents}
        for doc in scraped.documents:
            if doc.download_url not in existing_urls:
                self._create_document(tender.id, doc)
    
    def _create_document(self, tender_id, doc: ScrapedDocument) -> TenderDocument:
        """Create document record (metadata only)."""
        doc_type = self._map_file_type(doc.file_type)
        
        document = TenderDocument(
            id=uuid4(),
            tender_id=tender_id,
            filename=doc.filename,
            file_type=doc_type,
            file_size=doc.file_size,
            file_path=None,  # No disk storage
            download_url=doc.download_url,
            ocr_status=OCRStatus.PENDING,
        )
        self.db.add(document)
        return document
    
    def _map_file_type(self, file_type: str) -> DocumentType:
        """Map string file type to enum."""
        mapping = {
            'rc': DocumentType.RC,
            'cps': DocumentType.CPS,
            'annexe': DocumentType.ANNEXE,
        }
        return mapping.get(file_type.lower(), DocumentType.OTHER)


# In-memory document store for current scrape session
class InMemoryDocumentStore:
    """
    Temporary in-memory storage for downloaded documents.
    Documents are stored here during scraping and can be
    passed to OCR without disk writes.
    """
    
    def __init__(self):
        self._store: dict[str, bytes] = {}  # reference -> content
    
    def store(self, reference: str, filename: str, content: bytes):
        """Store document content."""
        key = f"{reference}:{filename}"
        self._store[key] = content
    
    def get(self, reference: str, filename: str) -> Optional[bytes]:
        """Retrieve document content."""
        key = f"{reference}:{filename}"
        return self._store.get(key)
    
    def get_all_for_tender(self, reference: str) -> dict[str, bytes]:
        """Get all documents for a tender."""
        prefix = f"{reference}:"
        return {
            k.split(":", 1)[1]: v 
            for k, v in self._store.items() 
            if k.startswith(prefix)
        }
    
    def clear(self):
        """Clear all stored documents."""
        self._store.clear()
    
    def clear_tender(self, reference: str):
        """Clear documents for a specific tender."""
        prefix = f"{reference}:"
        keys_to_delete = [k for k in self._store if k.startswith(prefix)]
        for key in keys_to_delete:
            del self._store[key]
    
    @property
    def size(self) -> int:
        """Total size in bytes."""
        return sum(len(v) for v in self._store.values())
    
    @property
    def count(self) -> int:
        """Number of stored documents."""
        return len(self._store)


# Global document store instance
document_store = InMemoryDocumentStore()

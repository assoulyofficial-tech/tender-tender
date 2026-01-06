"""
Text Extraction API endpoints.
Triggers text extraction from documents.
"""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.services.extraction_db import ExtractionDBService


router = APIRouter(prefix="/extraction", tags=["extraction"])


class ExtractionTrigger(BaseModel):
    """Request to trigger extraction."""
    tender_id: Optional[UUID] = None  # Specific tender, or None for all pending


class ExtractionResponse(BaseModel):
    """Response from extraction trigger."""
    status: str
    message: str
    tender_id: Optional[str] = None


class ExtractionResult(BaseModel):
    """Detailed extraction result."""
    tender_id: str
    reference: str
    documents: list
    success_count: int
    error_count: int


@router.post("/trigger", response_model=ExtractionResponse)
def trigger_extraction(
    request: ExtractionTrigger,
    db: Session = Depends(get_db)
):
    """
    Trigger text extraction for documents.
    
    If tender_id is provided, extracts from that tender's documents.
    Otherwise, processes all pending documents.
    """
    service = ExtractionDBService(db)
    
    if request.tender_id:
        result = service.process_tender(request.tender_id)
        
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        
        return ExtractionResponse(
            status="completed",
            message=f"Extracted from {result['success_count']} documents",
            tender_id=str(request.tender_id)
        )
    else:
        result = service.process_pending_documents()
        
        return ExtractionResponse(
            status="completed",
            message=f"Processed {result['success']} of {result['total']} documents"
        )


@router.post("/tender/{tender_id}", response_model=ExtractionResult)
def extract_tender_documents(
    tender_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Extract text from all documents of a specific tender.
    
    Returns detailed extraction results.
    """
    service = ExtractionDBService(db)
    result = service.process_tender(tender_id)
    
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    
    return ExtractionResult(**result)


@router.post("/pending")
def process_pending_documents(
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """
    Process all documents with pending OCR status.
    
    Args:
        limit: Maximum number of documents to process
    """
    service = ExtractionDBService(db)
    result = service.process_pending_documents(limit=limit)
    
    return {
        "status": "completed",
        "total_processed": result["total"],
        "successful": result["success"],
        "failed": result["failed"],
    }

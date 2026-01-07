"""
AI Process 1 — AVIS METADATA EXTRACTION API.

Night Shift — minimal cost, immediate listing.
Extracts searchable listing metadata with zero inference and full traceability.
"""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from app.database import get_db
from app.services.ai_db import AIDBService


router = APIRouter(prefix="/analysis", tags=["analysis"])


class AnalysisStatus(BaseModel):
    """AI analysis configuration status."""
    configured: bool
    model: str
    message: str
    process: str = "AI Process 1 - Avis Metadata Extraction"


class WebsiteDeadline(BaseModel):
    """Website deadline override."""
    date: Optional[str] = None  # DD/MM/YYYY
    time: Optional[str] = None  # HH:MM


class AnalysisTrigger(BaseModel):
    """Request to trigger Avis analysis."""
    tender_id: Optional[UUID] = None
    website_deadline: Optional[WebsiteDeadline] = None


class AnalysisResponse(BaseModel):
    """Response from Avis analysis."""
    status: str
    message: str
    tender_id: Optional[str] = None
    documents_analyzed: int = 0
    fields_extracted: int = 0
    keywords_generated: bool = False


@router.get("/status", response_model=AnalysisStatus)
def get_analysis_status(db: Session = Depends(get_db)):
    """
    Check if AI Process 1 (Avis Extraction) is configured.
    """
    service = AIDBService(db)
    
    from app.config import settings
    
    if service.is_configured():
        return AnalysisStatus(
            configured=True,
            model=settings.deepseek_model,
            message="DeepSeek API is configured - Avis extraction ready"
        )
    else:
        return AnalysisStatus(
            configured=False,
            model=settings.deepseek_model,
            message="DeepSeek API key not configured. Set DEEPSEEK_API_KEY in .env"
        )


@router.post("/trigger", response_model=AnalysisResponse)
async def trigger_analysis(
    request: AnalysisTrigger,
    db: Session = Depends(get_db)
):
    """
    Trigger AI Process 1 — Avis Metadata Extraction.
    
    Night Shift operation for immediate listing.
    
    Features:
    - Document classification by keywords (not filename)
    - Annex override logic (latest annex authoritative)
    - Website deadline override (MANDATORY)
    - Multilingual keywords (FR, EN, AR)
    - Full provenance tracking
    """
    service = AIDBService(db)
    
    if not service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="DeepSeek API key not configured. Set DEEPSEEK_API_KEY in .env"
        )
    
    # Prepare website deadline if provided
    website_deadline = None
    if request.website_deadline:
        website_deadline = {
            "date": request.website_deadline.date,
            "time": request.website_deadline.time
        }
    
    if request.tender_id:
        result = await service.analyze_tender(
            request.tender_id,
            website_deadline=website_deadline
        )
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        return AnalysisResponse(
            status="completed",
            message=f"Avis extraction: {result['documents_analyzed']} documents analyzed",
            tender_id=str(request.tender_id),
            documents_analyzed=result["documents_analyzed"],
            fields_extracted=result["fields_extracted"],
            keywords_generated=result["fields_extracted"] > 0
        )
    else:
        result = await service.analyze_pending_tenders()
        
        return AnalysisResponse(
            status="completed",
            message=f"Batch Avis extraction: {result['analyzed']}/{result['total_pending']} tenders",
            documents_analyzed=result["analyzed"],
            fields_extracted=0,
            keywords_generated=result["analyzed"] > 0
        )


@router.post("/tender/{tender_id}")
async def analyze_tender(
    tender_id: UUID,
    website_deadline: Optional[WebsiteDeadline] = None,
    db: Session = Depends(get_db)
):
    """
    Run AI Process 1 on a specific tender.
    
    Extraction Rules (STRICT):
    - No guessing
    - No inference  
    - No normalization
    - No currency conversion
    - If missing → null
    - Preserve original wording
    
    Document Priority:
    1. Avis de consultation (preferred)
    2. RC (if Avis missing)
    3. Annexes (override logic applies)
    4. Website (deadline override only)
    """
    service = AIDBService(db)
    
    if not service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="DeepSeek API key not configured. Set DEEPSEEK_API_KEY in .env"
        )
    
    ws_deadline = None
    if website_deadline:
        ws_deadline = {"date": website_deadline.date, "time": website_deadline.time}
    
    result = await service.analyze_tender(tender_id, website_deadline=ws_deadline)
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return {
        "status": "completed",
        "process": "AI Process 1 - Avis Metadata Extraction",
        "tender_id": str(tender_id),
        "reference": result["reference"],
        "documents_analyzed": result["documents_analyzed"],
        "fields_extracted": result["fields_extracted"],
        "errors": result["errors"]
    }


@router.post("/pending")
async def analyze_pending(
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """
    Night Shift batch processing.
    
    Analyze all tenders with extracted text but no Avis metadata.
    """
    service = AIDBService(db)
    
    if not service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="DeepSeek API key not configured. Set DEEPSEEK_API_KEY in .env"
        )
    
    result = await service.analyze_pending_tenders(limit=limit)
    
    return {
        "status": "completed",
        "process": "AI Process 1 - Batch Avis Extraction",
        "total_pending": result["total_pending"],
        "analyzed": result["analyzed"],
        "errors": result["errors"]
    }

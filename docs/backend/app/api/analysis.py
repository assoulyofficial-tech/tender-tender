"""
AI Analysis API endpoints.
Triggers AI extraction of Avis metadata.
"""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.services.ai_db import AIDBService


router = APIRouter(prefix="/analysis", tags=["analysis"])


class AnalysisStatus(BaseModel):
    """AI analysis configuration status."""
    configured: bool
    model: str
    message: str


class AnalysisTrigger(BaseModel):
    """Request to trigger analysis."""
    tender_id: Optional[UUID] = None


class AnalysisResponse(BaseModel):
    """Response from analysis trigger."""
    status: str
    message: str
    tender_id: Optional[str] = None
    documents_analyzed: int = 0
    fields_extracted: int = 0


@router.get("/status", response_model=AnalysisStatus)
def get_analysis_status(db: Session = Depends(get_db)):
    """
    Check if AI analysis is properly configured.
    """
    service = AIDBService(db)
    
    from app.config import settings
    
    if service.is_configured():
        return AnalysisStatus(
            configured=True,
            model=settings.deepseek_model,
            message="DeepSeek API is configured and ready"
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
    Trigger AI analysis for a tender or pending tenders.
    
    If tender_id is provided, analyzes that specific tender.
    Otherwise, processes pending tenders without AI analysis.
    """
    service = AIDBService(db)
    
    if not service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="DeepSeek API key not configured. Set DEEPSEEK_API_KEY in .env"
        )
    
    if request.tender_id:
        result = await service.analyze_tender(request.tender_id)
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        return AnalysisResponse(
            status="completed",
            message=f"Analyzed {result['documents_analyzed']} documents",
            tender_id=str(request.tender_id),
            documents_analyzed=result["documents_analyzed"],
            fields_extracted=result["fields_extracted"]
        )
    else:
        result = await service.analyze_pending_tenders()
        
        return AnalysisResponse(
            status="completed",
            message=f"Analyzed {result['analyzed']} of {result['total_pending']} pending tenders",
            documents_analyzed=result["analyzed"],
            fields_extracted=0  # Not tracked in batch mode
        )


@router.post("/tender/{tender_id}")
async def analyze_tender(
    tender_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Run AI analysis on a specific tender.
    
    Extracts Avis metadata from all documents.
    Applies annex override and website deadline logic.
    """
    service = AIDBService(db)
    
    if not service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="DeepSeek API key not configured. Set DEEPSEEK_API_KEY in .env"
        )
    
    result = await service.analyze_tender(tender_id)
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return {
        "status": "completed",
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
    Analyze all tenders that have extracted text but no AI analysis.
    
    Args:
        limit: Maximum tenders to process (default: 10)
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
        "total_pending": result["total_pending"],
        "analyzed": result["analyzed"],
        "errors": result["errors"]
    }

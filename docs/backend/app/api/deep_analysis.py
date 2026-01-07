"""
Deep Analysis API endpoints.

On-demand AI analysis triggered when user opens a tender.
No background execution - runs synchronously on request.
"""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Any

from app.database import get_db
from app.services.deep_analysis_db import DeepAnalysisDBService


router = APIRouter(prefix="/deep-analysis", tags=["deep-analysis"])


class DeepAnalysisStatus(BaseModel):
    """Status of deep analysis for a tender."""
    tender_id: str
    needs_analysis: bool
    has_analysis: bool
    message: str


class DeepAnalysisResult(BaseModel):
    """Deep analysis result."""
    status: str
    tender_id: str
    reference: Optional[str] = None
    fields_extracted: int = 0
    lots_found: int = 0
    has_execution_dates: bool = False
    confidence_score: float = 0.0
    analysis: Optional[dict] = None
    error: Optional[str] = None


@router.get("/status/{tender_id}", response_model=DeepAnalysisStatus)
def get_deep_analysis_status(
    tender_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Check if a tender needs or has deep analysis.
    
    Called when user navigates to tender detail page.
    """
    service = DeepAnalysisDBService(db)
    
    needs = service.needs_deep_analysis(tender_id)
    existing = service.get_deep_analysis(tender_id)
    
    if existing:
        return DeepAnalysisStatus(
            tender_id=str(tender_id),
            needs_analysis=False,
            has_analysis=True,
            message="Deep analysis available"
        )
    elif needs:
        return DeepAnalysisStatus(
            tender_id=str(tender_id),
            needs_analysis=True,
            has_analysis=False,
            message="Tender ready for deep analysis"
        )
    else:
        return DeepAnalysisStatus(
            tender_id=str(tender_id),
            needs_analysis=False,
            has_analysis=False,
            message="No extracted text available for analysis"
        )


@router.get("/{tender_id}", response_model=DeepAnalysisResult)
def get_deep_analysis(
    tender_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Get existing deep analysis results for a tender.
    
    Returns cached results if available, does not trigger new analysis.
    """
    service = DeepAnalysisDBService(db)
    
    existing = service.get_deep_analysis(tender_id)
    
    if existing:
        return DeepAnalysisResult(
            status="completed",
            tender_id=str(tender_id),
            fields_extracted=len(existing.get("lots", [])) + 10,  # Approximate
            lots_found=len(existing.get("lots", [])),
            has_execution_dates=existing.get("execution_dates") is not None,
            confidence_score=existing.get("confidence_score", 0.0),
            analysis=existing
        )
    else:
        return DeepAnalysisResult(
            status="not_found",
            tender_id=str(tender_id),
            error="No deep analysis available. Trigger analysis first."
        )


@router.post("/{tender_id}", response_model=DeepAnalysisResult)
async def trigger_deep_analysis(
    tender_id: UUID,
    force: bool = False,
    db: Session = Depends(get_db)
):
    """
    Trigger on-demand deep analysis for a tender.
    
    Called when user opens tender detail page.
    NOT a background job - runs synchronously.
    
    Args:
        tender_id: Tender UUID
        force: If True, re-analyze even if already analyzed
    """
    service = DeepAnalysisDBService(db)
    
    # Check API configuration
    if not service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="DeepSeek API key not configured. Set DEEPSEEK_API_KEY in .env"
        )
    
    # Check if already analyzed (unless force)
    if not force:
        existing = service.get_deep_analysis(tender_id)
        if existing:
            return DeepAnalysisResult(
                status="cached",
                tender_id=str(tender_id),
                lots_found=len(existing.get("lots", [])),
                has_execution_dates=existing.get("execution_dates") is not None,
                confidence_score=existing.get("confidence_score", 0.0),
                analysis=existing
            )
    
    # Perform analysis
    result = await service.perform_deep_analysis(tender_id)
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return DeepAnalysisResult(
        status=result["status"],
        tender_id=result["tender_id"],
        reference=result.get("reference"),
        fields_extracted=result["fields_extracted"],
        lots_found=result["lots_found"],
        has_execution_dates=result["has_execution_dates"],
        confidence_score=result["confidence_score"],
        analysis=result["analysis"]
    )


@router.get("/{tender_id}/lots")
def get_tender_lots(
    tender_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Get lot items from deep analysis.
    
    Convenience endpoint for lot-specific data.
    """
    service = DeepAnalysisDBService(db)
    
    existing = service.get_deep_analysis(tender_id)
    
    if not existing:
        raise HTTPException(
            status_code=404,
            detail="No deep analysis available. Trigger analysis first."
        )
    
    lots = existing.get("lots", [])
    
    return {
        "tender_id": str(tender_id),
        "lots_count": len(lots),
        "lots": lots,
        "single_lot_only": existing.get("single_lot_only", False),
        "all_lots_required": existing.get("all_lots_required", False)
    }


@router.get("/{tender_id}/execution")
def get_execution_dates(
    tender_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Get execution dates from deep analysis.
    
    Convenience endpoint for timeline data.
    """
    service = DeepAnalysisDBService(db)
    
    existing = service.get_deep_analysis(tender_id)
    
    if not existing:
        raise HTTPException(
            status_code=404,
            detail="No deep analysis available. Trigger analysis first."
        )
    
    execution_dates = existing.get("execution_dates")
    
    return {
        "tender_id": str(tender_id),
        "has_dates": execution_dates is not None,
        "execution_dates": execution_dates
    }


@router.get("/{tender_id}/provenance")
def get_field_provenance(
    tender_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Get field provenance tracking information.
    
    Shows source document and confidence for each extracted field.
    """
    from app.models.tender import TenderField, TenderDocument
    
    fields = db.query(TenderField).filter(
        TenderField.tender_id == tender_id
    ).all()
    
    provenance = []
    for field in fields:
        doc_name = None
        if field.document_id:
            doc = db.query(TenderDocument).filter(
                TenderDocument.id == field.document_id
            ).first()
            if doc:
                doc_name = doc.filename
        
        provenance.append({
            "field_name": field.field_name,
            "field_type": field.field_type,
            "source": field.source.value if field.source else "unknown",
            "confidence": field.confidence,
            "source_document": doc_name,
            "source_location": field.source_location,
            "is_verified": field.is_verified,
            "created_at": field.created_at.isoformat() if field.created_at else None,
            "updated_at": field.updated_at.isoformat() if field.updated_at else None
        })
    
    return {
        "tender_id": str(tender_id),
        "total_fields": len(provenance),
        "fields": provenance
    }

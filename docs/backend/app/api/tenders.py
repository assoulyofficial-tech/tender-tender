from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_

from app.database import get_db
from app.models import Tender, TenderStatus
from app.schemas import (
    TenderResponse,
    TenderDetailResponse,
    TenderDocumentResponse,
    TenderAnalysis,
    ProcessingStateResponse,
    PaginatedResponse
)

router = APIRouter()


@router.get("", response_model=PaginatedResponse[TenderResponse])
def list_tenders(
    search: Optional[str] = Query(None, description="Search in title, reference, organization"),
    status: Optional[str] = Query(None, description="Filter by status"),
    category: Optional[str] = Query(None, description="Filter by category"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db)
):
    """List tenders with filtering and pagination."""
    query = db.query(Tender)
    
    # Search filter
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                Tender.title.ilike(search_term),
                Tender.reference.ilike(search_term),
                Tender.organization.ilike(search_term)
            )
        )
    
    # Status filter
    if status:
        try:
            status_enum = TenderStatus(status)
            query = query.filter(Tender.status == status_enum)
        except ValueError:
            pass  # Invalid status, ignore filter
    
    # Category filter
    if category:
        query = query.filter(Tender.category.ilike(f"%{category}%"))
    
    # Get total count
    total = query.count()
    
    # Pagination
    offset = (page - 1) * page_size
    tenders = query.order_by(Tender.created_at.desc()).offset(offset).limit(page_size).all()
    
    # Calculate total pages
    total_pages = (total + page_size - 1) // page_size
    
    return PaginatedResponse(
        items=[TenderResponse.from_orm_with_budget(t) for t in tenders],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/{tender_id}", response_model=TenderDetailResponse)
def get_tender(
    tender_id: UUID,
    db: Session = Depends(get_db)
):
    """Get detailed tender information."""
    tender = db.query(Tender).options(
        joinedload(Tender.documents),
        joinedload(Tender.fields),
        joinedload(Tender.processing_state)
    ).filter(Tender.id == tender_id).first()
    
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")
    
    # Build analysis from fields
    analysis = None
    if tender.fields:
        field_map = {}
        for field in tender.fields:
            if field.field_name not in field_map:
                field_map[field.field_name] = []
            field_map[field.field_name].append(field.field_value)
        
        analysis = TenderAnalysis(
            summary=field_map.get("summary", [None])[0],
            key_requirements=field_map.get("key_requirement", []),
            eligibility_criteria=field_map.get("eligibility_criteria", []),
            submission_requirements=field_map.get("submission_requirement", [])
        )
    
    # Get extracted text from documents
    extracted_text = None
    for doc in tender.documents:
        if doc.extracted_text:
            extracted_text = doc.extracted_text
            break
    
    return TenderDetailResponse(
        id=tender.id,
        reference=tender.reference,
        title=tender.title,
        organization=tender.organization,
        category=tender.category,
        deadline=tender.deadline,
        budget=tender.budget_estimate,
        status=tender.status,
        source_url=tender.source_url,
        created_at=tender.created_at,
        updated_at=tender.updated_at,
        description=None,
        extracted_text=extracted_text,
        documents=[TenderDocumentResponse.model_validate(d) for d in tender.documents],
        analysis=analysis,
        processing_state=ProcessingStateResponse.model_validate(tender.processing_state) if tender.processing_state else None
    )

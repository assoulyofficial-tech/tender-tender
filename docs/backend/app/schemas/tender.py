from datetime import datetime
from typing import Optional, Generic, TypeVar
from uuid import UUID
from pydantic import BaseModel, ConfigDict
from app.models.tender import TenderStatus, DocumentType, OCRStatus, ProcessingStatus, FieldSource

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response."""
    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int


# Tender Schemas
class TenderBase(BaseModel):
    reference: str
    title: str
    organization: str
    category: str = "Fournitures"
    source_url: str


class TenderCreate(TenderBase):
    publication_date: Optional[datetime] = None
    deadline: Optional[datetime] = None
    opening_date: Optional[datetime] = None
    budget_estimate: Optional[float] = None
    caution_amount: Optional[float] = None
    source_id: Optional[str] = None


class TenderUpdate(BaseModel):
    title: Optional[str] = None
    organization: Optional[str] = None
    category: Optional[str] = None
    status: Optional[TenderStatus] = None
    deadline: Optional[datetime] = None
    budget_estimate: Optional[float] = None


class TenderResponse(BaseModel):
    """Basic tender response for list views."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    reference: str
    title: str
    organization: str
    category: str
    deadline: Optional[datetime]
    budget: Optional[float] = None  # Alias for budget_estimate
    status: TenderStatus
    source_url: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_with_budget(cls, tender):
        return cls(
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
            updated_at=tender.updated_at
        )


class TenderListResponse(TenderResponse):
    """Tender response for list views (same as TenderResponse)."""
    pass


# Document Schemas
class TenderDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    filename: str
    file_type: DocumentType
    file_size: Optional[int]
    ocr_status: OCRStatus
    extracted_text: Optional[str]
    download_url: Optional[str]
    page_count: Optional[int]


# Field Schemas
class TenderFieldResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    field_name: str
    field_value: str
    field_type: str
    source: FieldSource
    confidence: Optional[float]
    source_location: Optional[str]
    is_verified: bool


# Processing State Schemas
class ProcessingStateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    status: ProcessingStatus
    current_step: Optional[str]
    progress: float
    error_message: Optional[str]
    retry_count: int


# Analysis Schema (computed from fields)
class TenderAnalysis(BaseModel):
    summary: Optional[str] = None
    key_requirements: list[str] = []
    eligibility_criteria: list[str] = []
    submission_requirements: list[str] = []
    evaluated_at: Optional[datetime] = None


# Detail Response
class TenderDetailResponse(TenderResponse):
    """Full tender response with documents, fields, and analysis."""
    description: Optional[str] = None
    extracted_text: Optional[str] = None
    documents: list[TenderDocumentResponse] = []
    analysis: Optional[TenderAnalysis] = None
    processing_state: Optional[ProcessingStateResponse] = None

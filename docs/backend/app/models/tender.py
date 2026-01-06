import enum
from datetime import datetime
from uuid import uuid4
from sqlalchemy import (
    Column, String, Text, DateTime, Enum, ForeignKey, 
    Integer, Float, Boolean, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class TenderStatus(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"
    AWARDED = "awarded"
    CANCELLED = "cancelled"


class DocumentType(str, enum.Enum):
    RC = "rc"  # Règlement de Consultation
    CPS = "cps"  # Cahier des Prescriptions Spéciales
    ANNEXE = "annexe"
    OTHER = "other"


class OCRStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ProcessingStatus(str, enum.Enum):
    PENDING = "pending"
    SCRAPING = "scraping"
    DOWNLOADING = "downloading"
    OCR = "ocr"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    FAILED = "failed"


class FieldSource(str, enum.Enum):
    SCRAPED = "scraped"  # From website HTML
    OCR = "ocr"  # From document OCR
    AI = "ai"  # AI-extracted/analyzed
    MANUAL = "manual"  # Manually entered


class Tender(Base):
    """Main tender table - stores tender metadata."""
    __tablename__ = "tenders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    reference = Column(String(100), unique=True, nullable=False, index=True)
    title = Column(String(500), nullable=False)
    organization = Column(String(300), nullable=False)
    category = Column(String(100), default="Fournitures")
    
    # Dates
    publication_date = Column(DateTime, nullable=True)
    deadline = Column(DateTime, nullable=True)
    opening_date = Column(DateTime, nullable=True)
    
    # Financial
    budget_estimate = Column(Float, nullable=True)
    caution_amount = Column(Float, nullable=True)
    
    # Status
    status = Column(Enum(TenderStatus), default=TenderStatus.OPEN, nullable=False)
    
    # Source
    source_url = Column(String(1000), nullable=False)
    source_id = Column(String(100), nullable=True)  # ID from source website
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    documents = relationship("TenderDocument", back_populates="tender", cascade="all, delete-orphan")
    fields = relationship("TenderField", back_populates="tender", cascade="all, delete-orphan")
    processing_state = relationship("ProcessingState", back_populates="tender", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_tenders_status_deadline", "status", "deadline"),
        Index("ix_tenders_organization", "organization"),
    )


class TenderDocument(Base):
    """Documents attached to tenders (PDFs, etc.)."""
    __tablename__ = "tender_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tender_id = Column(UUID(as_uuid=True), ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False)
    
    # File info
    filename = Column(String(500), nullable=False)
    file_type = Column(Enum(DocumentType), default=DocumentType.OTHER)
    file_size = Column(Integer, nullable=True)  # bytes
    file_path = Column(String(1000), nullable=True)  # local storage path
    download_url = Column(String(1000), nullable=True)  # original URL
    
    # OCR
    ocr_status = Column(Enum(OCRStatus), default=OCRStatus.PENDING)
    ocr_error = Column(Text, nullable=True)
    extracted_text = Column(Text, nullable=True)
    page_count = Column(Integer, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    tender = relationship("Tender", back_populates="documents")

    __table_args__ = (
        Index("ix_tender_documents_tender_id", "tender_id"),
        Index("ix_tender_documents_ocr_status", "ocr_status"),
    )


class TenderField(Base):
    """Extracted fields with provenance tracking."""
    __tablename__ = "tender_fields"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tender_id = Column(UUID(as_uuid=True), ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False)
    document_id = Column(UUID(as_uuid=True), ForeignKey("tender_documents.id", ondelete="SET NULL"), nullable=True)
    
    # Field data
    field_name = Column(String(100), nullable=False)  # e.g., "eligibility_criteria", "submission_deadline"
    field_value = Column(Text, nullable=False)
    field_type = Column(String(50), default="text")  # text, date, number, list, json
    
    # Provenance
    source = Column(Enum(FieldSource), nullable=False)
    confidence = Column(Float, nullable=True)  # 0.0 to 1.0 for AI-extracted
    source_location = Column(String(200), nullable=True)  # page number, section, etc.
    
    # Validation
    is_verified = Column(Boolean, default=False)
    verified_at = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    tender = relationship("Tender", back_populates="fields")

    __table_args__ = (
        Index("ix_tender_fields_tender_id_field_name", "tender_id", "field_name"),
        Index("ix_tender_fields_source", "source"),
    )


class ProcessingState(Base):
    """Tracks processing pipeline state for each tender."""
    __tablename__ = "processing_states"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tender_id = Column(UUID(as_uuid=True), ForeignKey("tenders.id", ondelete="CASCADE"), unique=True, nullable=False)
    
    # Current state
    status = Column(Enum(ProcessingStatus), default=ProcessingStatus.PENDING, nullable=False)
    current_step = Column(String(100), nullable=True)
    progress = Column(Float, default=0.0)  # 0.0 to 100.0
    
    # Error tracking
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    last_error_at = Column(DateTime, nullable=True)
    
    # Step timestamps
    scraping_started_at = Column(DateTime, nullable=True)
    scraping_completed_at = Column(DateTime, nullable=True)
    ocr_started_at = Column(DateTime, nullable=True)
    ocr_completed_at = Column(DateTime, nullable=True)
    analysis_started_at = Column(DateTime, nullable=True)
    analysis_completed_at = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    tender = relationship("Tender", back_populates="processing_state")

    __table_args__ = (
        Index("ix_processing_states_status", "status"),
    )

"""
Ask AI API endpoints.

Conversational Q&A for tenders.
Supports French and Moroccan Darija.
"""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from app.database import get_db
from app.services.ask_ai_db import AskAIDBService


router = APIRouter(prefix="/ask", tags=["ask-ai"])


class ConversationEntry(BaseModel):
    """Previous Q&A entry for context."""
    question: str
    answer: str


class AskRequest(BaseModel):
    """Request to ask a question about a tender."""
    question: str
    conversation_history: Optional[List[ConversationEntry]] = None


class Citation(BaseModel):
    """Source citation."""
    document_name: str
    section: Optional[str] = None
    page: Optional[int] = None
    quote: Optional[str] = None


class AskResponse(BaseModel):
    """Response from Ask AI."""
    answer: str
    language_detected: str
    citations: List[Citation]
    confidence: float
    follow_up_suggestions: List[str]
    tender_reference: str
    documents_used: int


class TenderSummary(BaseModel):
    """Summary of tender context available."""
    tender_id: str
    reference: str
    title: str
    has_documents: bool
    document_count: int
    document_names: List[str]
    has_analysis: bool
    can_ask: bool


class SuggestedQuestionsResponse(BaseModel):
    """Suggested questions response."""
    questions: List[str]
    language: str


@router.get("/status")
def get_ask_ai_status(db: Session = Depends(get_db)):
    """
    Check if Ask AI is properly configured.
    """
    service = AskAIDBService(db)
    
    from app.config import settings
    
    if service.is_configured():
        return {
            "configured": True,
            "model": settings.deepseek_model,
            "message": "Ask AI is ready",
            "supported_languages": ["fr", "ar-ma", "ar", "en"]
        }
    else:
        return {
            "configured": False,
            "model": settings.deepseek_model,
            "message": "DeepSeek API key not configured. Set DEEPSEEK_API_KEY in .env"
        }


@router.get("/tender/{tender_id}/summary", response_model=TenderSummary)
def get_tender_summary(
    tender_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Get summary of available tender context.
    
    Shows what documents and analysis are available for Q&A.
    """
    service = AskAIDBService(db)
    result = service.get_tender_summary(tender_id)
    
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    
    return result


@router.get("/tender/{tender_id}/suggestions")
def get_suggested_questions(
    tender_id: UUID,
    language: str = "fr",
    db: Session = Depends(get_db)
):
    """
    Get suggested questions for a tender.
    
    Args:
        tender_id: Tender UUID
        language: 'fr' (French) or 'ar-ma' (Darija)
    """
    service = AskAIDBService(db)
    
    # Validate language
    if language not in ["fr", "ar-ma"]:
        language = "fr"
    
    questions = service.get_suggested_questions(tender_id, language)
    
    return {
        "questions": questions,
        "language": language
    }


@router.post("/tender/{tender_id}", response_model=AskResponse)
async def ask_about_tender(
    tender_id: UUID,
    request: AskRequest,
    db: Session = Depends(get_db)
):
    """
    Ask a question about a tender.
    
    Supports:
    - French
    - Moroccan Darija (Arabic dialect)
    - Standard Arabic
    - English
    
    Returns answer with source citations.
    """
    service = AskAIDBService(db)
    
    if not service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="DeepSeek API key not configured. Set DEEPSEEK_API_KEY in .env"
        )
    
    # Convert conversation history to dict format
    history = None
    if request.conversation_history:
        history = [
            {"question": entry.question, "answer": entry.answer}
            for entry in request.conversation_history
        ]
    
    result = await service.ask_about_tender(
        tender_id=tender_id,
        question=request.question,
        conversation_history=history
    )
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result


@router.post("/tender/{tender_id}/quick")
async def quick_ask(
    tender_id: UUID,
    question: str,
    db: Session = Depends(get_db)
):
    """
    Quick ask endpoint - simple GET-like interface.
    
    For simple one-off questions without conversation history.
    """
    service = AskAIDBService(db)
    
    if not service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="DeepSeek API key not configured"
        )
    
    result = await service.ask_about_tender(
        tender_id=tender_id,
        question=question
    )
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result

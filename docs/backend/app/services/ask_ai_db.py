"""
Ask AI Database Service.

Integrates Ask AI with tender data from database.
Stores conversation history for context.
"""

import json
from typing import Optional, Any
from uuid import UUID
from datetime import datetime
from dataclasses import asdict

from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

from app.models.tender import (
    Tender, TenderDocument, TenderField, 
    OCRStatus, FieldSource
)
from app.services.ask_ai import AskAIService, AskAIResponse, SourceCitation


class AskAIDBService:
    """
    Ask AI service with database integration.
    
    Loads tender context from database.
    Optionally stores conversation history.
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.ask_service = AskAIService()
    
    def is_configured(self) -> bool:
        """Check if AI is configured."""
        return self.ask_service.is_configured()
    
    def _get_tender_info(self, tender: Tender) -> dict:
        """Extract tender info for context."""
        return {
            "reference": tender.reference,
            "title": tender.title,
            "organization": tender.organization,
            "category": tender.category,
            "deadline": tender.deadline.isoformat() if tender.deadline else None,
            "publication_date": tender.publication_date.isoformat() if tender.publication_date else None,
            "budget_estimate": tender.budget_estimate,
            "caution_amount": tender.caution_amount,
            "status": tender.status.value if tender.status else None,
            "source_url": tender.source_url
        }
    
    def _get_documents(self, tender_id: UUID) -> list[dict]:
        """Get all extracted documents for a tender."""
        documents = self.db.query(TenderDocument).filter(
            and_(
                TenderDocument.tender_id == tender_id,
                TenderDocument.extracted_text.isnot(None),
                TenderDocument.ocr_status == OCRStatus.COMPLETED
            )
        ).all()
        
        return [
            {
                "filename": doc.filename,
                "content": doc.extracted_text or "",
                "file_type": doc.file_type.value if doc.file_type else "unknown"
            }
            for doc in documents
        ]
    
    def _get_analysis(self, tender_id: UUID) -> Optional[dict]:
        """Get AI analysis results if available."""
        # Get deep analysis
        deep_field = self.db.query(TenderField).filter(
            and_(
                TenderField.tender_id == tender_id,
                TenderField.field_name == "deep_analysis"
            )
        ).first()
        
        if deep_field:
            try:
                return json.loads(deep_field.field_value)
            except json.JSONDecodeError:
                pass
        
        # Get individual AI fields
        fields = self.db.query(TenderField).filter(
            and_(
                TenderField.tender_id == tender_id,
                TenderField.source == FieldSource.AI
            )
        ).all()
        
        if not fields:
            return None
        
        analysis = {}
        for field in fields:
            try:
                if field.field_type == "json" or field.field_type == "list":
                    analysis[field.field_name] = json.loads(field.field_value)
                else:
                    analysis[field.field_name] = field.field_value
            except json.JSONDecodeError:
                analysis[field.field_name] = field.field_value
        
        return analysis if analysis else None
    
    async def ask_about_tender(
        self,
        tender_id: UUID,
        question: str,
        conversation_history: Optional[list[dict]] = None
    ) -> dict:
        """
        Ask a question about a specific tender.
        
        Args:
            tender_id: Tender UUID
            question: User's question
            conversation_history: Previous Q&A pairs
            
        Returns:
            Response dict with answer and citations
        """
        # Get tender
        tender = self.db.query(Tender).filter(Tender.id == tender_id).first()
        if not tender:
            return {"error": "Tender not found"}
        
        # Check if configured
        if not self.is_configured():
            return {"error": "DeepSeek API key not configured"}
        
        # Get context
        tender_info = self._get_tender_info(tender)
        documents = self._get_documents(tender_id)
        analysis = self._get_analysis(tender_id)
        
        if not documents:
            return {
                "error": "No extracted documents available for this tender",
                "suggestion": "Please run text extraction first"
            }
        
        # Ask the question
        try:
            response = await self.ask_service.ask(
                question=question,
                tender_info=tender_info,
                documents=documents,
                analysis=analysis,
                conversation_history=conversation_history
            )
        except Exception as e:
            return {"error": f"AI service error: {str(e)}"}
        
        # Format response
        return {
            "answer": response.answer,
            "language_detected": response.language_detected,
            "citations": [asdict(c) for c in response.citations],
            "confidence": response.confidence,
            "follow_up_suggestions": response.follow_up_suggestions,
            "tender_reference": tender.reference,
            "documents_used": len(documents)
        }
    
    def get_tender_summary(self, tender_id: UUID) -> dict:
        """
        Get a summary of available tender information.
        
        Useful for the frontend to show what context is available.
        """
        tender = self.db.query(Tender).filter(Tender.id == tender_id).first()
        if not tender:
            return {"error": "Tender not found"}
        
        documents = self._get_documents(tender_id)
        analysis = self._get_analysis(tender_id)
        
        return {
            "tender_id": str(tender_id),
            "reference": tender.reference,
            "title": tender.title,
            "has_documents": len(documents) > 0,
            "document_count": len(documents),
            "document_names": [d["filename"] for d in documents],
            "has_analysis": analysis is not None,
            "can_ask": len(documents) > 0 and self.is_configured()
        }
    
    def get_suggested_questions(self, tender_id: UUID, language: str = "fr") -> list[str]:
        """
        Get suggested questions based on tender content.
        
        Args:
            tender_id: Tender UUID
            language: 'fr' or 'ar-ma' for Darija
            
        Returns:
            List of suggested questions
        """
        if language == "ar-ma":
            return [
                "شنو هي الوثائق اللي خاصني نقدم؟",
                "شحال الثمن ديال الكفالة؟",
                "كيفاش نقدر نشارك فهاد الصفقة؟",
                "آش هي الشروط التقنية؟",
                "فين وفوقتاش نقدر نقدم العرض ديالي؟",
                "واش كاين شي زيارة للموقع؟",
                "شحال المدة ديال التنفيذ؟"
            ]
        else:
            return [
                "Quels documents dois-je fournir pour soumissionner ?",
                "Quel est le montant de la caution provisoire ?",
                "Quelles sont les conditions d'éligibilité ?",
                "Quelle est la date limite de dépôt des offres ?",
                "Quels sont les critères d'attribution ?",
                "Y a-t-il une visite des lieux obligatoire ?",
                "Quel est le délai d'exécution prévu ?",
                "Quelles sont les garanties demandées ?"
            ]

"""
Ask AI Service - Conversational Q&A for tenders.

Accepts French and Moroccan Darija input.
Uses full tender context with source citations.
No embeddings (V1) - sends full context to LLM.
"""

import json
import httpx
from dataclasses import dataclass, field
from typing import Optional, Any
from uuid import UUID
from datetime import datetime

from app.config import settings


@dataclass
class SourceCitation:
    """Citation to source document section."""
    document_name: str
    section: Optional[str] = None
    page: Optional[int] = None
    quote: Optional[str] = None


@dataclass
class AskAIResponse:
    """Response from Ask AI."""
    answer: str
    language_detected: str  # fr, ar-ma (Darija), ar, en
    citations: list[SourceCitation] = field(default_factory=list)
    confidence: float = 0.0
    follow_up_suggestions: list[str] = field(default_factory=list)


# Ask AI System Prompt
ASK_AI_PROMPT = """Tu es un assistant expert en marchés publics et appels d'offres.
Tu réponds aux questions sur les appels d'offres en utilisant UNIQUEMENT les informations fournies dans le contexte.

RÈGLES STRICTES:
1. Réponds dans la même langue que la question (Français, Darija marocain, ou Arabe)
2. Si la question est en Darija (dialecte marocain), réponds en Darija
3. CITE TOUJOURS tes sources avec le format: [Document: nom_du_document, Section: section]
4. Si l'information n'est pas dans le contexte, dis-le clairement
5. Ne fabrique JAMAIS d'information
6. Sois précis et concis

FORMAT DE RÉPONSE (JSON):
{
    "answer": "Ta réponse détaillée avec citations inline",
    "language_detected": "fr" | "ar-ma" | "ar" | "en",
    "citations": [
        {
            "document_name": "Nom du document",
            "section": "Section ou titre",
            "page": null,
            "quote": "Citation exacte si pertinente"
        }
    ],
    "confidence": 0.0-1.0,
    "follow_up_suggestions": ["Question suggérée 1", "Question suggérée 2"]
}

EXEMPLES DE QUESTIONS EN DARIJA:
- "شنو هي الوثائق اللي خاصني نقدم؟" (Quels documents dois-je soumettre?)
- "شحال الثمن ديال الكفالة؟" (Quel est le montant de la caution?)
- "فين نقدر نجيب الملف؟" (Où puis-je retirer le dossier?)
- "آش هي الشروط باش نشارك؟" (Quelles sont les conditions de participation?)

Réponds UNIQUEMENT avec le JSON, sans markdown ni explications."""


class AskAIService:
    """
    Conversational Q&A service for tenders.
    
    Features:
    - French and Moroccan Darija support
    - Full tender context (no embeddings in V1)
    - Source citations
    """
    
    def __init__(self):
        self.api_key = settings.deepseek_api_key
        self.base_url = settings.deepseek_base_url
        self.model = settings.deepseek_model
        self.timeout = 60.0
        self.max_context_chars = 100000  # ~25k tokens for context
    
    def is_configured(self) -> bool:
        """Check if API key is configured."""
        return bool(self.api_key)
    
    def _build_context(
        self,
        tender_info: dict,
        documents: list[dict],
        analysis: Optional[dict] = None
    ) -> str:
        """
        Build full tender context for the LLM.
        
        Args:
            tender_info: Basic tender metadata
            documents: List of {filename, content} dicts
            analysis: Optional AI analysis results
        """
        context_parts = []
        
        # Tender metadata
        context_parts.append("=" * 60)
        context_parts.append("INFORMATIONS GÉNÉRALES DE L'APPEL D'OFFRES")
        context_parts.append("=" * 60)
        context_parts.append(f"Référence: {tender_info.get('reference', 'N/A')}")
        context_parts.append(f"Titre: {tender_info.get('title', 'N/A')}")
        context_parts.append(f"Organisation: {tender_info.get('organization', 'N/A')}")
        context_parts.append(f"Catégorie: {tender_info.get('category', 'N/A')}")
        context_parts.append(f"Date limite: {tender_info.get('deadline', 'N/A')}")
        context_parts.append(f"Budget estimé: {tender_info.get('budget_estimate', 'N/A')}")
        context_parts.append(f"Montant caution: {tender_info.get('caution_amount', 'N/A')}")
        context_parts.append("")
        
        # AI Analysis if available
        if analysis:
            context_parts.append("=" * 60)
            context_parts.append("ANALYSE IA")
            context_parts.append("=" * 60)
            
            if analysis.get('eligibility_criteria'):
                context_parts.append("\nCritères d'éligibilité:")
                for crit in analysis['eligibility_criteria']:
                    context_parts.append(f"  - {crit}")
            
            if analysis.get('submission_requirements'):
                context_parts.append("\nExigences de soumission:")
                for req in analysis['submission_requirements']:
                    context_parts.append(f"  - {req}")
            
            if analysis.get('required_documents'):
                context_parts.append("\nDocuments requis:")
                for doc in analysis['required_documents']:
                    context_parts.append(f"  - {doc}")
            
            if analysis.get('lots'):
                context_parts.append("\nLots:")
                for lot in analysis['lots']:
                    context_parts.append(f"  - Lot {lot.get('lot_number', '?')}: {lot.get('title', 'N/A')}")
            
            context_parts.append("")
        
        # Document contents
        current_length = len("\n".join(context_parts))
        remaining_chars = self.max_context_chars - current_length
        chars_per_doc = remaining_chars // max(len(documents), 1)
        
        for doc in documents:
            context_parts.append("=" * 60)
            context_parts.append(f"DOCUMENT: {doc['filename']}")
            context_parts.append("=" * 60)
            
            content = doc.get('content', '')
            if len(content) > chars_per_doc:
                content = content[:chars_per_doc] + "\n[... document tronqué ...]"
            
            context_parts.append(content)
            context_parts.append("")
        
        return "\n".join(context_parts)
    
    async def ask(
        self,
        question: str,
        tender_info: dict,
        documents: list[dict],
        analysis: Optional[dict] = None,
        conversation_history: Optional[list[dict]] = None
    ) -> AskAIResponse:
        """
        Ask a question about a tender.
        
        Args:
            question: User's question (French, Darija, or Arabic)
            tender_info: Tender metadata
            documents: List of {filename, content}
            analysis: Optional AI analysis results
            conversation_history: Previous Q&A for context
            
        Returns:
            AskAIResponse with answer and citations
        """
        if not self.is_configured():
            raise ValueError("DeepSeek API key not configured")
        
        # Build context
        context = self._build_context(tender_info, documents, analysis)
        
        # Build messages
        messages = [
            {"role": "system", "content": ASK_AI_PROMPT}
        ]
        
        # Add conversation history if provided
        if conversation_history:
            for entry in conversation_history[-5:]:  # Last 5 exchanges
                messages.append({"role": "user", "content": entry.get("question", "")})
                messages.append({"role": "assistant", "content": entry.get("answer", "")})
        
        # Add current question with context
        user_message = f"""CONTEXTE DE L'APPEL D'OFFRES:
{context}

QUESTION DE L'UTILISATEUR:
{question}

Réponds en JSON avec les citations appropriées."""
        
        messages.append({"role": "user", "content": user_message})
        
        # Call DeepSeek API
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.3,  # Lower for factual responses
                    "max_tokens": 4000
                }
            )
            
            if response.status_code != 200:
                error_text = response.text
                raise Exception(f"DeepSeek API error {response.status_code}: {error_text}")
            
            result = response.json()
        
        # Parse response
        content = result["choices"][0]["message"]["content"]
        
        # Clean JSON
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        
        try:
            data = json.loads(content.strip())
        except json.JSONDecodeError:
            # Fallback: return raw answer
            return AskAIResponse(
                answer=content,
                language_detected="fr",
                citations=[],
                confidence=0.5,
                follow_up_suggestions=[]
            )
        
        # Build response
        citations = []
        for cit in data.get("citations", []):
            citations.append(SourceCitation(
                document_name=cit.get("document_name", "Unknown"),
                section=cit.get("section"),
                page=cit.get("page"),
                quote=cit.get("quote")
            ))
        
        return AskAIResponse(
            answer=data.get("answer", ""),
            language_detected=data.get("language_detected", "fr"),
            citations=citations,
            confidence=data.get("confidence", 0.8),
            follow_up_suggestions=data.get("follow_up_suggestions", [])
        )
    
    def detect_language(self, text: str) -> str:
        """
        Simple language detection for French/Darija/Arabic.
        
        Returns: 'fr', 'ar-ma' (Darija), 'ar', or 'en'
        """
        # Arabic script detection
        arabic_chars = sum(1 for c in text if '\u0600' <= c <= '\u06FF')
        total_alpha = sum(1 for c in text if c.isalpha())
        
        if total_alpha == 0:
            return "fr"
        
        arabic_ratio = arabic_chars / total_alpha
        
        if arabic_ratio > 0.5:
            # Check for Darija indicators
            darija_indicators = [
                "شنو", "كيفاش", "فين", "علاش", "واش", "شحال",
                "خاص", "بغيت", "عندي", "ديال", "ماشي", "كاين"
            ]
            for indicator in darija_indicators:
                if indicator in text:
                    return "ar-ma"
            return "ar"
        
        # Check for French
        french_indicators = ["le", "la", "les", "de", "du", "des", "est", "sont", "pour", "dans"]
        text_lower = text.lower()
        french_count = sum(1 for word in french_indicators if f" {word} " in f" {text_lower} ")
        
        if french_count >= 2:
            return "fr"
        
        # Check for English
        english_indicators = ["the", "is", "are", "for", "what", "how", "when", "where"]
        english_count = sum(1 for word in english_indicators if f" {word} " in f" {text_lower} ")
        
        if english_count >= 2:
            return "en"
        
        return "fr"  # Default to French

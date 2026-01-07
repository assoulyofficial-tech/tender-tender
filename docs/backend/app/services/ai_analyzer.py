"""
AI Process 1 — AVIS METADATA EXTRACTION.

Night Shift — minimal cost, immediate listing.
Extract searchable listing metadata with zero inference and full traceability.
"""

import json
import httpx
from dataclasses import dataclass, field, asdict
from typing import Optional, Any
from enum import Enum

from app.config import settings


class DocumentType(str, Enum):
    """Document types identified by content keywords."""
    AVIS = "avis"
    RC = "rc"
    CPS = "cps"
    ANNEXE = "annexe"
    UNKNOWN = "unknown"


# Document detection keywords (scan first page only)
DOCUMENT_DETECTION_KEYWORDS = {
    DocumentType.AVIS: [
        "avis de consultation",
        "avis d'appel d'offres",
        "aoon",
        "aooi"
    ],
    DocumentType.RC: [
        "règlement de consultation",
        "reglement de consultation",
        "rc",
        "référence de consultation"
    ],
    DocumentType.CPS: [
        "cahier des prescriptions spéciales",
        "cahier des prescriptions speciales"
    ],
    DocumentType.ANNEXE: [
        "annexe",
        "additif",
        "avenant",
        "modification"
    ]
}


@dataclass
class ProvenanceField:
    """Field with provenance tracking."""
    value: Optional[str] = None
    source_document: Optional[str] = None
    source_date: Optional[str] = None


@dataclass
class SubmissionDeadline:
    """Submission deadline with date and time."""
    date: ProvenanceField = field(default_factory=ProvenanceField)
    time: ProvenanceField = field(default_factory=ProvenanceField)


@dataclass
class LotMetadata:
    """Lot metadata from Avis."""
    lot_number: Optional[str] = None
    lot_subject: Optional[str] = None
    lot_estimated_value: Optional[float] = None
    caution_provisoire: Optional[float] = None


@dataclass
class Keywords:
    """Multilingual keywords for search."""
    keywords_fr: list[str] = field(default_factory=list)
    keywords_eng: list[str] = field(default_factory=list)
    keywords_ar: list[str] = field(default_factory=list)


@dataclass
class AvisMetadata:
    """
    AVIS METADATA EXTRACTION SCHEMA.
    
    All fields include provenance tracking.
    """
    reference_tender: ProvenanceField = field(default_factory=ProvenanceField)
    tender_type: ProvenanceField = field(default_factory=ProvenanceField)  # AOON | AOOI | null
    issuing_institution: ProvenanceField = field(default_factory=ProvenanceField)
    submission_deadline: SubmissionDeadline = field(default_factory=SubmissionDeadline)
    folder_opening_location: ProvenanceField = field(default_factory=ProvenanceField)
    subject: ProvenanceField = field(default_factory=ProvenanceField)
    total_estimated_value: ProvenanceField = field(default_factory=ProvenanceField)
    currency: Optional[str] = None
    lots: list[LotMetadata] = field(default_factory=list)
    keywords: Keywords = field(default_factory=Keywords)


# Avis Extraction Prompt
AVIS_EXTRACTION_PROMPT = """Tu es un moteur d'extraction juridique et technique.
Tu n'es PAS un rédacteur. Tu n'es PAS un résumeur.

OBJECTIF:
Extraire les métadonnées de l'Avis d'appel d'offres pour un référencement rapide et traçable.

DOCUMENTS D'ENTRÉE (ordre de priorité):
1. Avis de consultation (préféré)
2. RC (seulement si Avis manquant ou incomplet)
3. Annexes (logique de substitution applicable)

RÈGLES D'IDENTIFICATION DES DOCUMENTS:
- Scanner la première page uniquement
- Classifier par mots-clés du contenu (PAS par nom de fichier)
- Avis: "Avis de consultation", "Avis d'appel d'offres", "AOON", "AOOI"
- RC: "Règlement de consultation", "RC", "Référence de consultation"
- CPS: "Cahier des prescriptions spéciales"
- Annexe: "Annexe", "Additif", "Avenant", "Modification"

RÈGLES D'EXTRACTION STRICTES (PHASE 1):
❌ Aucune supposition
❌ Aucune inférence
❌ Aucune normalisation
❌ Aucune conversion de devise
✅ Si manquant → null
✅ Préserver le libellé original

LOGIQUE DE SUBSTITUTION DES ANNEXES:
- Si annexes présentes: extraire date/version
- Trier chronologiquement
- L'annexe la plus récente fait autorité
- Remplacer les champs en conflit
- Mettre à jour les métadonnées de provenance

GÉNÉRATION DES MOTS-CLÉS (CRITIQUE):
- Extraire UNIQUEMENT du texte de l'Avis
- Ne PAS inventer de concepts
- Générer 10 mots-clés par langue
- Basés sur l'objet du marché + articles
- Langues: Français, Anglais, Arabe (standard moderne)

SCHÉMA DE SORTIE (JSON STRICT):
{
  "reference_tender": {
    "value": null,
    "source_document": "nom_du_document.pdf",
    "source_date": null
  },
  "tender_type": {
    "value": "AOON | AOOI | null",
    "source_document": null,
    "source_date": null
  },
  "issuing_institution": {
    "value": null,
    "source_document": null,
    "source_date": null
  },
  "submission_deadline": {
    "date": {
      "value": "DD/MM/YYYY",
      "source_document": null,
      "source_date": null
    },
    "time": {
      "value": "HH:MM",
      "source_document": null,
      "source_date": null
    }
  },
  "folder_opening_location": {
    "value": null,
    "source_document": null,
    "source_date": null
  },
  "subject": {
    "value": null,
    "source_document": null,
    "source_date": null
  },
  "total_estimated_value": {
    "value": null,
    "currency": "MAD",
    "source_document": null,
    "source_date": null
  },
  "lots": [
    {
      "lot_number": null,
      "lot_subject": null,
      "lot_estimated_value": null,
      "caution_provisoire": null
    }
  ],
  "keywords": {
    "keywords_fr": [],
    "keywords_eng": [],
    "keywords_ar": []
  }
}

Réponds UNIQUEMENT avec le JSON valide. Pas de markdown. Pas d'explications."""


class AvisExtractor:
    """
    AI Process 1 - Avis Metadata Extraction.
    
    Runs during night shift for minimal cost.
    Extracts searchable listing metadata with full traceability.
    """
    
    def __init__(self):
        self.api_key = settings.deepseek_api_key
        self.base_url = settings.deepseek_base_url
        self.model = settings.deepseek_model
        self.timeout = 60.0
    
    def is_configured(self) -> bool:
        """Check if API key is configured."""
        return bool(self.api_key)
    
    def classify_document(self, first_page_text: str) -> DocumentType:
        """
        Classify document by content keywords (not filename).
        Scans first page only.
        """
        text_lower = first_page_text.lower()
        
        for doc_type, keywords in DOCUMENT_DETECTION_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return doc_type
        
        return DocumentType.UNKNOWN
    
    def sort_annexes_chronologically(self, documents: list[dict]) -> list[dict]:
        """
        Sort annexes chronologically.
        Most recent annex is authoritative.
        """
        annexes = [d for d in documents if d.get("doc_type") == DocumentType.ANNEXE]
        others = [d for d in documents if d.get("doc_type") != DocumentType.ANNEXE]
        
        # Sort by date if available, otherwise by position
        annexes.sort(key=lambda x: x.get("date") or x.get("position", 0))
        
        return others + annexes  # Annexes last = override
    
    async def extract_metadata(
        self,
        documents: list[dict],
        website_deadline: Optional[dict] = None
    ) -> AvisMetadata:
        """
        Extract Avis metadata from documents.
        
        Args:
            documents: List of {filename, content, doc_type}
            website_deadline: Optional {date, time} from website
            
        Returns:
            AvisMetadata with provenance tracking
        """
        if not self.is_configured():
            raise ValueError("DeepSeek API key not configured")
        
        # Classify and sort documents
        for doc in documents:
            if "doc_type" not in doc:
                first_page = doc.get("content", "")[:3000]
                doc["doc_type"] = self.classify_document(first_page)
        
        documents = self.sort_annexes_chronologically(documents)
        
        # Build document context
        doc_texts = []
        for doc in documents:
            doc_type_label = doc.get("doc_type", DocumentType.UNKNOWN).value.upper()
            doc_texts.append(
                f"\n{'='*60}\n"
                f"[{doc_type_label}] {doc['filename']}\n"
                f"{'='*60}\n"
                f"{doc['content'][:30000]}"  # Limit per document
            )
        
        combined_text = "\n\n".join(doc_texts)
        
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
                    "messages": [
                        {"role": "system", "content": AVIS_EXTRACTION_PROMPT},
                        {"role": "user", "content": f"Extraire les métadonnées:\n\n{combined_text}"}
                    ],
                    "temperature": 0.0,  # Zero for strict extraction
                    "max_tokens": 4000
                }
            )
            
            if response.status_code != 200:
                raise Exception(f"DeepSeek API error {response.status_code}: {response.text}")
            
            result = response.json()
        
        # Parse response
        content = result["choices"][0]["message"]["content"]
        
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        
        try:
            data = json.loads(content.strip())
        except json.JSONDecodeError as e:
            raise Exception(f"JSON parse error: {e}")
        
        # Apply website deadline override (MANDATORY)
        if website_deadline:
            if data.get("submission_deadline") is None:
                data["submission_deadline"] = {"date": {}, "time": {}}
            
            # Override if missing, partial, or ambiguous
            current_date = data["submission_deadline"].get("date", {}).get("value")
            current_time = data["submission_deadline"].get("time", {}).get("value")
            
            if not current_date or website_deadline.get("date"):
                data["submission_deadline"]["date"] = {
                    "value": website_deadline.get("date"),
                    "source_document": "Website",
                    "source_date": None
                }
            
            if not current_time or website_deadline.get("time"):
                data["submission_deadline"]["time"] = {
                    "value": website_deadline.get("time"),
                    "source_document": "Website",
                    "source_date": None
                }
        
        return self._parse_response(data)
    
    def _parse_response(self, data: dict) -> AvisMetadata:
        """Parse API response into AvisMetadata."""
        
        def parse_provenance(field_data) -> ProvenanceField:
            if isinstance(field_data, dict):
                return ProvenanceField(
                    value=field_data.get("value"),
                    source_document=field_data.get("source_document"),
                    source_date=field_data.get("source_date")
                )
            return ProvenanceField(value=field_data if field_data else None)
        
        # Parse submission deadline
        deadline_data = data.get("submission_deadline", {})
        submission_deadline = SubmissionDeadline(
            date=parse_provenance(deadline_data.get("date", {})),
            time=parse_provenance(deadline_data.get("time", {}))
        )
        
        # Parse lots
        lots = []
        for lot_data in data.get("lots", []):
            lots.append(LotMetadata(
                lot_number=lot_data.get("lot_number"),
                lot_subject=lot_data.get("lot_subject"),
                lot_estimated_value=lot_data.get("lot_estimated_value"),
                caution_provisoire=lot_data.get("caution_provisoire")
            ))
        
        # Parse keywords
        keywords_data = data.get("keywords", {})
        keywords = Keywords(
            keywords_fr=keywords_data.get("keywords_fr", [])[:10],
            keywords_eng=keywords_data.get("keywords_eng", [])[:10],
            keywords_ar=keywords_data.get("keywords_ar", [])[:10]
        )
        
        # Get currency from total_estimated_value
        tev = data.get("total_estimated_value", {})
        currency = tev.get("currency") if isinstance(tev, dict) else None
        
        return AvisMetadata(
            reference_tender=parse_provenance(data.get("reference_tender")),
            tender_type=parse_provenance(data.get("tender_type")),
            issuing_institution=parse_provenance(data.get("issuing_institution")),
            submission_deadline=submission_deadline,
            folder_opening_location=parse_provenance(data.get("folder_opening_location")),
            subject=parse_provenance(data.get("subject")),
            total_estimated_value=parse_provenance(data.get("total_estimated_value")),
            currency=currency,
            lots=lots,
            keywords=keywords
        )
    
    def to_dict(self, metadata: AvisMetadata) -> dict:
        """Convert AvisMetadata to dictionary."""
        return asdict(metadata)

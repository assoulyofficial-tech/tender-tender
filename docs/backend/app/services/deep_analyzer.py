"""
AI Process 2 — UNIVERSAL DEEP ANALYSIS.

User Shift — on click only.
Extract full operational, financial, and technical structure of the tender.
This phase is expensive and must only run on user intent.
"""

import json
import httpx
from dataclasses import dataclass, field, asdict
from typing import Optional, Any

from app.config import settings


@dataclass
class TraceableField:
    """Field with optional traceability."""
    value: Optional[str] = None
    source_document: Optional[str] = None
    page_number: Optional[int] = None


@dataclass
class LotItem:
    """Item within a lot."""
    item_name: Optional[str] = None
    quantity: Optional[str] = None
    technical_description_full: Optional[str] = None  # Verbatim, no simplification


@dataclass
class UniversalLot:
    """Full lot structure from Universal Deep Analysis."""
    lot_number: Optional[str] = None
    lot_subject: Optional[str] = None
    lot_estimated_value: Optional[float] = None
    caution_provisoire: Optional[float] = None
    caution_definitive_percentage: Optional[float] = None
    estimated_caution_definitive_value: Optional[float] = None  # Computed only if both exist
    execution_date: Optional[str] = None
    items: list[LotItem] = field(default_factory=list)


@dataclass 
class UniversalSubmissionDeadline:
    """Submission deadline structure."""
    date: Optional[str] = None
    time: Optional[str] = None


@dataclass
class UniversalFields:
    """
    UNIVERSAL FIELDS — EXTRACTION SCHEMA.
    
    Full operational, financial, and technical structure.
    """
    reference_tender: Optional[str] = None
    tender_type: Optional[str] = None  # AOON | AOOI | null
    issuing_institution: Optional[str] = None
    institution_address: Optional[str] = None
    submission_deadline: UniversalSubmissionDeadline = field(default_factory=UniversalSubmissionDeadline)
    folder_opening_location: Optional[str] = None
    subject: Optional[str] = None
    total_estimated_value: Optional[float] = None
    lots: list[UniversalLot] = field(default_factory=list)


# Universal Deep Analysis Prompt
UNIVERSAL_ANALYSIS_PROMPT = """Tu es un moteur d'extraction juridique et technique.
Tu n'es PAS un rédacteur. Tu n'es PAS un résumeur.

OBJECTIF:
Extraire la structure opérationnelle, financière et technique complète de l'appel d'offres.

DOCUMENTS D'ENTRÉE:
- CPS (texte complet)
- RC (texte complet)
- Annexes (toutes versions, triées chronologiquement)
- Avis (pour référence uniquement)

PRIORITÉ D'EXTRACTION (pour chaque champ):
1. Dernière annexe
2. CPS
3. RC
4. Avis (autorité la plus basse)

Toujours préférer: La déclaration la plus récente et explicite.

RÈGLES DE CALCUL:
- estimated_caution_definitive_value = lot_estimated_value × (caution_definitive_percentage / 100)
- Calculer UNIQUEMENT SI les deux valeurs existent
- Sinon → null
- Ne JAMAIS supposer les pourcentages

RÈGLES DE LANGUE:
- Préserver la langue originale
- Ne PAS traduire
- Ne PAS résumer
- Les descriptions techniques doivent être VERBATIM

RÈGLES STRICTES:
❌ Aucune hallucination
❌ Aucun article inventé
❌ Aucune fusion de lots non liés
❌ Aucune simplification des specs techniques
✅ Si manquant → null
✅ Texte original préservé

SCHÉMA DE SORTIE (JSON STRICT):
{
  "reference_tender": "",
  "tender_type": "AOON | AOOI | null",
  "issuing_institution": "",
  "institution_address": "",
  "submission_deadline": {
    "date": "",
    "time": ""
  },
  "folder_opening_location": "",
  "subject": "",
  "total_estimated_value": null,
  "lots": [
    {
      "lot_number": "",
      "lot_subject": "",
      "lot_estimated_value": null,
      "caution_provisoire": null,
      "caution_definitive_percentage": null,
      "estimated_caution_definitive_value": null,
      "execution_date": "",
      "items": [
        {
          "item_name": "",
          "quantity": "",
          "technical_description_full": ""
        }
      ]
    }
  ]
}

Réponds UNIQUEMENT avec le JSON valide. Pas de markdown. Pas d'explications."""


class DeepAnalyzer:
    """
    AI Process 2 - Universal Deep Analysis.
    
    Runs on user click only (expensive).
    Extracts full operational, financial, and technical structure.
    """
    
    def __init__(self):
        self.api_key = settings.deepseek_api_key
        self.base_url = settings.deepseek_base_url
        self.model = settings.deepseek_model
        self.timeout = 120.0  # Deep analysis takes longer
    
    def is_configured(self) -> bool:
        """Check if API key is configured."""
        return bool(self.api_key)
    
    def _sort_by_priority(self, documents: list[dict]) -> list[dict]:
        """
        Sort documents by extraction priority.
        
        Priority order:
        1. Latest annex (highest)
        2. CPS
        3. RC
        4. Avis (lowest)
        """
        priority_order = {"annexe": 0, "cps": 1, "rc": 2, "avis": 3, "unknown": 4}
        
        # Sort: highest priority last (to override)
        return sorted(
            documents,
            key=lambda x: priority_order.get(x.get("doc_type", "unknown"), 4),
            reverse=True  # Lower priority first, higher priority last
        )
    
    async def analyze_documents(
        self,
        documents: list[dict],
        existing_avis: Optional[dict] = None
    ) -> UniversalFields:
        """
        Perform Universal Deep Analysis.
        
        Args:
            documents: List of {filename, content, doc_type}
            existing_avis: Avis metadata for reference
            
        Returns:
            UniversalFields with full structure
        """
        if not self.is_configured():
            raise ValueError("DeepSeek API key not configured")
        
        # Sort by priority
        documents = self._sort_by_priority(documents)
        
        # Build document context
        doc_texts = []
        for doc in documents:
            doc_type = doc.get("doc_type", "unknown").upper()
            doc_texts.append(
                f"\n{'='*60}\n"
                f"[{doc_type}] {doc['filename']}\n"
                f"{'='*60}\n"
                f"{doc['content'][:40000]}"  # Larger limit for deep analysis
            )
        
        combined_text = "\n\n".join(doc_texts)
        
        # Add Avis reference if available
        avis_context = ""
        if existing_avis:
            avis_context = f"\n\n[RÉFÉRENCE AVIS]\n{json.dumps(existing_avis, indent=2, default=str)}\n"
        
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
                        {"role": "system", "content": UNIVERSAL_ANALYSIS_PROMPT},
                        {"role": "user", "content": f"Analyse complète:{avis_context}\n\n{combined_text}"}
                    ],
                    "temperature": 0.0,  # Zero for strict extraction
                    "max_tokens": 8000
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
        
        # Parse and compute
        return self._parse_response(data)
    
    def _parse_response(self, data: dict) -> UniversalFields:
        """Parse API response and compute derived values."""
        
        # Parse lots with items
        lots = []
        for lot_data in data.get("lots", []):
            # Parse items
            items = []
            for item_data in lot_data.get("items", []):
                items.append(LotItem(
                    item_name=item_data.get("item_name"),
                    quantity=item_data.get("quantity"),
                    technical_description_full=item_data.get("technical_description_full")
                ))
            
            # Get lot values
            lot_value = lot_data.get("lot_estimated_value")
            caution_pct = lot_data.get("caution_definitive_percentage")
            
            # COMPUTATION RULE: Only compute if BOTH exist
            estimated_caution = None
            if lot_value is not None and caution_pct is not None:
                try:
                    estimated_caution = float(lot_value) * (float(caution_pct) / 100)
                except (ValueError, TypeError):
                    estimated_caution = None
            
            lots.append(UniversalLot(
                lot_number=lot_data.get("lot_number"),
                lot_subject=lot_data.get("lot_subject"),
                lot_estimated_value=lot_value,
                caution_provisoire=lot_data.get("caution_provisoire"),
                caution_definitive_percentage=caution_pct,
                estimated_caution_definitive_value=estimated_caution,
                execution_date=lot_data.get("execution_date"),
                items=items
            ))
        
        # Parse deadline
        deadline_data = data.get("submission_deadline", {})
        submission_deadline = UniversalSubmissionDeadline(
            date=deadline_data.get("date") if isinstance(deadline_data, dict) else None,
            time=deadline_data.get("time") if isinstance(deadline_data, dict) else None
        )
        
        return UniversalFields(
            reference_tender=data.get("reference_tender"),
            tender_type=data.get("tender_type"),
            issuing_institution=data.get("issuing_institution"),
            institution_address=data.get("institution_address"),
            submission_deadline=submission_deadline,
            folder_opening_location=data.get("folder_opening_location"),
            subject=data.get("subject"),
            total_estimated_value=data.get("total_estimated_value"),
            lots=lots
        )
    
    def to_dict(self, fields: UniversalFields) -> dict:
        """Convert UniversalFields to dictionary."""
        return asdict(fields)

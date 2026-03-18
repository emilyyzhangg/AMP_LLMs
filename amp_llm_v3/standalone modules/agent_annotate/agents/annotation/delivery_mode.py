"""
Delivery Mode Annotation Agent.

Determines how the drug/intervention is administered.

v2 changes (from 70-trial concordance analysis):
  - Upgraded to two-pass design: Pass 1 extracts route evidence from all sources
    (protocol text, FDA labels, drug databases, literature), Pass 2 applies
    classification rules. This eliminates the "Injection/Infusion - Other/Unspecified"
    default problem by forcing the model to actively search for route specifics
    before classifying.
  - Enhanced prompt to prioritize FDA label routes and database info over
    generic protocol text.
"""

import re
import logging
from typing import Optional

from agents.base import BaseAnnotationAgent
from app.models.research import ResearchResult, SourceCitation
from app.models.annotation import FieldAnnotation

logger = logging.getLogger("agent_annotate.annotation.delivery_mode")

VALID_VALUES = [
    "Injection/Infusion - Intramuscular",
    "Injection/Infusion - Other/Unspecified",
    "Injection/Infusion - Subcutaneous/Intradermal",
    "IV",
    "Intranasal",
    "Oral - Tablet",
    "Oral - Capsule",
    "Oral - Food",
    "Oral - Drink",
    "Oral - Unspecified",
    "Topical - Cream/Gel",
    "Topical - Powder",
    "Topical - Spray",
    "Topical - Strip/Covering",
    "Topical - Wash",
    "Topical - Unspecified",
    "Other/Unspecified",
    "Inhalation",
]

# Pass 1: Extract ALL route evidence from every source
PASS1_SYSTEM = """You are a clinical pharmacology route-of-administration extraction specialist.

Your task: Search ALL available evidence to find how this drug is administered. Check EVERY source — do NOT stop at the first mention. Different sources may have different levels of specificity.

Extract the following:

1. PROTOCOL ROUTE: What does the ClinicalTrials.gov protocol say about route of administration? Look in intervention description, arm group descriptions, and detailed description. Quote the exact text.

2. FDA/DRUG LABEL ROUTE: Does any evidence mention an FDA-approved route, drug label route, or prescribing information route? (e.g., "for subcutaneous use", "administered intravenously"). FDA labels are MORE SPECIFIC and MORE RELIABLE than protocol text.

3. LITERATURE ROUTE: Do any PubMed/PMC publications describe how this drug is administered? Quote relevant excerpts.

4. DATABASE ROUTE: Do ChEMBL, UniProt, DRAMP, or other database entries mention route or formulation information?

5. DRUG FORMULATION: Is the drug described as a tablet, capsule, solution, suspension, cream, gel, powder, spray, patch, inhaler, or other formulation? The formulation strongly implies the route.

6. SPECIFICITY LEVEL: Based on ALL sources above, what is the MOST SPECIFIC route you can determine?
   - If ANY source says "subcutaneous" or "SC" → the route is subcutaneous
   - If ANY source says "intramuscular" or "IM" → the route is intramuscular
   - If ANY source says "intravenous" or "IV" → the route is IV
   - If NONE specify beyond "injection" → route is unspecified injection

Format your response EXACTLY as:
Protocol Route: [quote or "not specified"]
FDA/Label Route: [quote or "not found"]
Literature Route: [quote or "not found"]
Database Route: [info or "not found"]
Drug Formulation: [formulation or "not specified"]
Most Specific Route: [your determination]"""

# Pass 2: Classify into one of the 18 valid values
PASS2_SYSTEM = """You are a delivery mode classification specialist. You have extracted route-of-administration evidence. Now classify it into EXACTLY ONE delivery mode.

The route facts you extracted:
{pass1_output}

VALID VALUES (choose exactly one):

Injection/Infusion:
- IV: Intravenous (IV push, IV drip, IV infusion)
- Injection/Infusion - Intramuscular: IM injection (ONLY if "intramuscular" or "IM" explicitly stated)
- Injection/Infusion - Subcutaneous/Intradermal: SC, sub-Q, or intradermal (ONLY if explicitly stated)
- Injection/Infusion - Other/Unspecified: Any other injection route OR injection without IM/SC/IV specified

Intranasal: Nasal spray, nasal drops (NOT topical spray)
Inhalation: Inhaler, nebulizer, inhaled

Oral:
- Oral - Tablet, Oral - Capsule, Oral - Food, Oral - Drink, Oral - Unspecified

Topical:
- Topical - Cream/Gel, Topical - Powder, Topical - Spray, Topical - Strip/Covering, Topical - Wash, Topical - Unspecified

Other/Unspecified: Does not fit any category above

CLASSIFICATION RULES:
1. USE THE MOST SPECIFIC SOURCE. FDA label > Literature > Protocol text > Database.
2. If FDA/Label Route specifies "subcutaneous" but Protocol just says "injection" → use Subcutaneous/Intradermal.
3. If Literature says "administered intravenously" but Protocol is vague → use IV.
4. ONLY use "Injection/Infusion - Other/Unspecified" when NO source specifies IM, SC, or IV.
5. Nutritional formula/shake = Oral - Drink. Nasal spray = Intranasal (not Topical - Spray).

Format your response EXACTLY as:
Delivery Mode: [one of the 18 valid values, exactly as written]
Evidence: [cite which source determined the route]
Reasoning: [brief explanation]"""


class DeliveryModeAgent(BaseAnnotationAgent):
    """Determines drug delivery mode using two-pass route investigation."""

    field_name = "delivery_mode"

    async def annotate(
        self,
        nct_id: str,
        research_results: list[ResearchResult],
        metadata: Optional[dict] = None,
    ) -> FieldAnnotation:
        from app.services.config_service import config_service

        _config = config_service.get()
        is_server = _config.orchestrator.hardware_profile == "server"
        max_cites = 35 if is_server else 20
        max_snippet = 500 if is_server else 250

        # Build structured evidence — trial metadata and drug data
        # sections contain the route-of-administration information
        evidence_text, cited_sources = self.build_structured_evidence(
            nct_id, research_results,
            max_citations=max_cites,
            max_snippet_chars=max_snippet,
        )

        from app.services.ollama_client import ollama_client
        from app.services.config_service import config_service

        config = config_service.get()
        primary_model = None
        for model_key, model_cfg in config.verification.models.items():
            if model_cfg.role == "annotator":
                primary_model = model_cfg.name
                break
        if not primary_model:
            primary_model = "llama3.1:8b"

        # --- Pass 1: Extract route evidence from all sources ---
        try:
            logger.info(f"  delivery_mode: Pass 1 — extracting route evidence for {nct_id}")
            pass1_response = await ollama_client.generate(
                model=primary_model,
                prompt=evidence_text,
                system=PASS1_SYSTEM,
                temperature=config.ollama.temperature,
            )
            pass1_text = pass1_response.get("response", "")
        except Exception as e:
            return FieldAnnotation(
                field_name=self.field_name,
                value="Other/Unspecified",
                confidence=0.0,
                reasoning=f"Pass 1 LLM call failed: {e}",
                evidence=[],
                model_name=primary_model,
            )

        # --- Pass 2: Classify route into valid value ---
        try:
            logger.info(f"  delivery_mode: Pass 2 — classifying route for {nct_id}")
            pass2_prompt = PASS2_SYSTEM.format(pass1_output=pass1_text)
            pass2_response = await ollama_client.generate(
                model=primary_model,
                prompt=pass2_prompt + "\n\nOriginal evidence:\n" + evidence_text,
                temperature=config.ollama.temperature,
            )
            pass2_text = pass2_response.get("response", "")
        except Exception as e:
            # Fallback: infer from Pass 1
            value = self._infer_from_pass1(pass1_text)
            return FieldAnnotation(
                field_name=self.field_name,
                value=value,
                confidence=0.3,
                reasoning=f"Pass 2 failed ({e}), inferred from pass 1: {pass1_text[:300]}",
                evidence=cited_sources[:10],
                model_name=primary_model,
            )

        value = self._parse_value(pass2_text)
        reasoning = f"[Pass 1 route extraction] {pass1_text[:400]}\n[Pass 2 classification] {pass2_text[:300]}"
        quality = sum(c.quality_score for c in cited_sources[:10]) / max(len(cited_sources[:10]), 1)

        return FieldAnnotation(
            field_name=self.field_name,
            value=value,
            confidence=quality,
            reasoning=reasoning,
            evidence=cited_sources[:10],
            model_name=primary_model,
        )

    def _infer_from_pass1(self, pass1_text: str) -> str:
        """Fallback: infer delivery mode from Pass 1 extraction if Pass 2 fails."""
        lower = pass1_text.lower()

        # Check for explicit route mentions across all sources
        if any(kw in lower for kw in ["intravenous", " iv ", "iv infusion", "iv push"]):
            return "IV"
        if any(kw in lower for kw in ["subcutaneous", " sc ", "sub-q", "intradermal"]):
            return "Injection/Infusion - Subcutaneous/Intradermal"
        if any(kw in lower for kw in ["intramuscular", " im "]):
            return "Injection/Infusion - Intramuscular"
        if any(kw in lower for kw in ["intranasal", "nasal spray", "nasal drop"]):
            return "Intranasal"
        if any(kw in lower for kw in ["inhalation", "inhaler", "nebulizer", "inhaled"]):
            return "Inhalation"
        if any(kw in lower for kw in ["tablet"]):
            return "Oral - Tablet"
        if any(kw in lower for kw in ["capsule"]):
            return "Oral - Capsule"
        if any(kw in lower for kw in ["oral", "by mouth"]):
            return "Oral - Unspecified"
        if any(kw in lower for kw in ["injection", "infusion", "parenteral"]):
            return "Injection/Infusion - Other/Unspecified"
        if any(kw in lower for kw in ["cream", "gel", "ointment", "topical"]):
            return "Topical - Cream/Gel"

        return "Other/Unspecified"

    def _parse_value(self, text: str) -> str:
        match = re.search(r"Delivery Mode:\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
        if not match:
            return "Other/Unspecified"

        raw = match.group(1).strip()
        lower = raw.lower()

        # Exact match first (case-insensitive)
        for valid in VALID_VALUES:
            if valid.lower() == lower:
                return valid

        # Fuzzy matching by category

        # IV — check before general injection to avoid misclassification
        if lower in ("iv", "intravenous") or "intravenous" in lower:
            return "IV"

        # Injection/Infusion subtypes
        if "intramuscular" in lower:
            return "Injection/Infusion - Intramuscular"
        if "subcutaneous" in lower or "intradermal" in lower:
            return "Injection/Infusion - Subcutaneous/Intradermal"
        if "injection" in lower or "infusion" in lower:
            return "Injection/Infusion - Other/Unspecified"

        # Intranasal
        if "intranasal" in lower or "nasal" in lower:
            return "Intranasal"

        # Inhalation
        if "inhalation" in lower or "inhale" in lower or "nebuliz" in lower or "inhaler" in lower:
            return "Inhalation"

        # Oral subtypes
        if "oral" in lower or "tablet" in lower or "capsule" in lower or "food" in lower or "drink" in lower:
            if "tablet" in lower:
                return "Oral - Tablet"
            if "capsule" in lower:
                return "Oral - Capsule"
            if "food" in lower:
                return "Oral - Food"
            if "drink" in lower:
                return "Oral - Drink"
            return "Oral - Unspecified"

        # Topical subtypes
        if "topical" in lower or "cream" in lower or "gel" in lower or "ointment" in lower or "powder" in lower or "spray" in lower or "strip" in lower or "covering" in lower or "bandage" in lower or "dressing" in lower or "patch" in lower or "wash" in lower or "rinse" in lower or "mouthwash" in lower or "lotion" in lower:
            if "cream" in lower or "gel" in lower or "ointment" in lower or "lotion" in lower:
                return "Topical - Cream/Gel"
            if "powder" in lower:
                return "Topical - Powder"
            if "spray" in lower:
                return "Topical - Spray"
            if "strip" in lower or "covering" in lower or "bandage" in lower or "dressing" in lower or "patch" in lower:
                return "Topical - Strip/Covering"
            if "wash" in lower or "rinse" in lower or "mouthwash" in lower or "irrigat" in lower:
                return "Topical - Wash"
            return "Topical - Unspecified"

        return "Other/Unspecified"

    def _parse_reasoning(self, text: str) -> str:
        match = re.search(r"Reasoning:\s*(.+?)(?:\n\n|$)", text, re.DOTALL)
        if match:
            return match.group(1).strip()[:500]
        return text[:500]

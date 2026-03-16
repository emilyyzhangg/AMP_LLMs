"""
Delivery Mode Annotation Agent.

Determines how the drug/intervention is administered.
"""

import re
from typing import Optional

from agents.base import BaseAnnotationAgent
from app.models.research import ResearchResult, SourceCitation
from app.models.annotation import FieldAnnotation

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

SYSTEM_PROMPT = """You are a clinical trial delivery mode specialist.

Your task: Determine the SPECIFIC route of administration for the primary intervention in this clinical trial.

You must choose EXACTLY ONE of these 18 delivery modes:

Injection/Infusion routes:
- Injection/Infusion - Intramuscular: Intramuscular (IM) injection
- Injection/Infusion - Subcutaneous/Intradermal: Subcutaneous (SC) or intradermal injection
- Injection/Infusion - Other/Unspecified: Any other injection/infusion route (intrathecal, intraperitoneal, etc.) or injection route not specified
- IV: Intravenous administration (IV push, IV drip, IV infusion)

Intranasal:
- Intranasal: Delivered through the nasal passage (nasal spray, nasal drops)

Oral routes:
- Oral - Tablet: Oral tablet form
- Oral - Capsule: Oral capsule form
- Oral - Food: Delivered mixed into or as a food product (e.g., yogurt, functional food)
- Oral - Drink: Delivered as a drink or dissolved in liquid for drinking
- Oral - Unspecified: Oral route but specific form not stated or unclear

Topical routes:
- Topical - Cream/Gel: Applied as cream, gel, ointment, or lotion
- Topical - Powder: Applied as a powder to skin or wound
- Topical - Spray: Topical spray applied to skin/wound (not nasal — use Intranasal for that)
- Topical - Strip/Covering: Bandage, dressing, patch, or strip containing the intervention
- Topical - Wash: Rinse, wash, mouthwash, or irrigation solution
- Topical - Unspecified: Topical route but specific form not stated

Other:
- Other/Unspecified: Route does not fit any category above or is not stated
- Inhalation: Inhaled into the lungs (inhaler, nebulizer)

Guidance for choosing:
1. Look at the intervention description, arm group details, and drug labels for route information.
2. Be as specific as possible — prefer subtypes (e.g., "Topical - Cream/Gel") over unspecified (e.g., "Topical - Unspecified").
3. If the trial mentions IV or intravenous, use "IV" (not Injection/Infusion - Other/Unspecified).
4. Nasal sprays are "Intranasal", not "Topical - Spray".
5. If truly unclear, use the appropriate "Unspecified" subtype or "Other/Unspecified".

CRITICAL RULES — DO NOT GUESS:
6. NEVER guess the injection subtype. If the protocol says "injection" or "injectable" without explicitly specifying IM (intramuscular), SC/SQ (subcutaneous), or IV (intravenous), use "Injection/Infusion - Other/Unspecified". Do NOT default to Intramuscular or Subcutaneous.
7. If an FDA drug label specifies a route (e.g., "SUBCUTANEOUS"), use that as the primary signal.
8. Look for explicit terms: "intramuscular" or "IM" → Intramuscular. "subcutaneous", "SC", "sub-Q", "intradermal" → Subcutaneous/Intradermal. Do NOT infer from drug class or "likely" administration.
9. "Injection" alone, "parenteral", or "administered by injection" WITHOUT a specific route = "Injection/Infusion - Other/Unspecified". NEVER assume IM, SC, or IV from context.
10. Do NOT guess routes based on drug class. Even if "most vaccines are IM", if the protocol doesn't say IM, use "Injection/Infusion - Other/Unspecified".
11. If the evidence says "injection" and the route is unclear, the answer is ALWAYS "Injection/Infusion - Other/Unspecified". Saying Intramuscular or Subcutaneous without explicit evidence is WRONG.

Oral subtype rules:
12. "Oral - Food": the intervention IS a food product (functional food, fortified food, yogurt).
13. "Oral - Drink": the intervention is dissolved in liquid, a solution, nutritional formula, shake, or suspension to be consumed as a beverage. A nutritional formula or shake = Oral - Drink, NOT Oral - Food.
14. When in doubt between Oral - Food and Oral - Drink, prefer Oral - Drink for liquid formulations.

WORKED EXAMPLES:

Protocol says "Aviptadil administered by IV infusion over 12 hours"
→ Delivery Mode: IV
Why: "IV infusion" is explicitly stated.

Protocol says "apraglutide subcutaneous injection once weekly"
→ Delivery Mode: Injection/Infusion - Subcutaneous/Intradermal
Why: "subcutaneous" is explicitly stated.

Protocol says "peptide vaccine injection" (no route specified)
→ Delivery Mode: Injection/Infusion - Other/Unspecified
Why: "injection" without IM/SC/IV = Other/Unspecified. DO NOT guess Intramuscular.

Protocol says "administered by injection once daily"
→ Delivery Mode: Injection/Infusion - Other/Unspecified
Why: Only "injection" is stated — no IM/SC/IV route given. Do NOT assume Subcutaneous.

Protocol says "vaccine administered via injection"
→ Delivery Mode: Injection/Infusion - Other/Unspecified
Why: Even though many vaccines are given IM, the protocol doesn't specify. Do NOT default to Intramuscular.

FDA label says "for subcutaneous use", protocol says "injection"
→ Delivery Mode: Injection/Infusion - Subcutaneous/Intradermal
Why: FDA label specifying route overrides the generic "injection" in the protocol.

Protocol says "Kate Farm Peptide 1.5 nutritional formula"
→ Delivery Mode: Oral - Drink
Why: Nutritional formula consumed as a beverage = Oral - Drink, NOT Oral - Food.

Protocol says "colistin inhalation solution via nebulizer"
→ Delivery Mode: Inhalation
Why: "inhalation" and "nebulizer" explicitly stated.

IMPORTANT: Format your response EXACTLY as:

Delivery Mode: [one of the 18 values listed above, exactly as written]
Evidence: [Cite the specific source and excerpt]
Reasoning: [Brief explanation]"""


class DeliveryModeAgent(BaseAnnotationAgent):
    """Determines drug delivery mode."""

    field_name = "delivery_mode"

    async def annotate(
        self,
        nct_id: str,
        research_results: list[ResearchResult],
        metadata: Optional[dict] = None,
    ) -> FieldAnnotation:
        all_citations = []
        for result in research_results:
            weight = self.relevance_weight(result.agent_name)
            for citation in result.citations:
                all_citations.append((citation, weight))

        all_citations.sort(key=lambda x: x[1], reverse=True)

        evidence_text = f"Trial: {nct_id}\n\n"
        cited_sources = []
        for citation, weight in all_citations[:20]:
            evidence_text += f"[{citation.source_name}] {citation.identifier or ''}: {citation.snippet}\n"
            cited_sources.append(citation)

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

        try:
            response = await ollama_client.generate(
                model=primary_model,
                prompt=evidence_text,
                system=SYSTEM_PROMPT,
                temperature=config.ollama.temperature,
            )
            raw_text = response.get("response", "")
        except Exception as e:
            return FieldAnnotation(
                field_name=self.field_name,
                value="Other/Unspecified",
                confidence=0.0,
                reasoning=f"LLM call failed: {e}",
                evidence=[],
                model_name=primary_model,
            )

        value = self._parse_value(raw_text)
        reasoning = self._parse_reasoning(raw_text)
        quality = sum(c.quality_score for c in cited_sources[:10]) / max(len(cited_sources[:10]), 1)

        return FieldAnnotation(
            field_name=self.field_name,
            value=value,
            confidence=quality,
            reasoning=reasoning,
            evidence=cited_sources[:10],
            model_name=primary_model,
        )

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

"""
Classification Annotation Agent.

Determines whether a clinical trial involves an Antimicrobial Peptide (AMP) and its purpose.
"""

import re
from typing import Optional

from agents.base import BaseAnnotationAgent, FIELD_RELEVANCE
from app.models.research import ResearchResult, SourceCitation
from app.models.annotation import FieldAnnotation

VALID_VALUES = ["AMP(infection)", "AMP(other)", "Other"]

SYSTEM_PROMPT = """You are a clinical trial classification specialist. AMP stands for Antimicrobial Peptide.

Your task: Classify a clinical trial into one of exactly three categories using the three-step decision tree below.

You will be told whether the intervention is a peptide (Peptide determination provided below).

THREE-STEP DECISION TREE:

STEP 1 — Is the intervention a peptide?
  Check the Peptide determination. If Peptide = False → STOP → answer "Other".

STEP 2 — Is this peptide an ANTIMICROBIAL PEPTIDE (AMP)?

  AMPs (also called Host Defense Peptides) are peptides that participate in defense against pathogens through ANY of the following modes of action:

  MODE A — Direct antimicrobial activity:
    Peptides that directly kill or inhibit bacteria, viruses, fungi, or parasites via membrane disruption, pore formation, or intracellular targeting.
    Examples: colistin, polymyxin B, daptomycin, nisin, melittin, magainin, cecropin, gramicidin, bacitracin, vancomycin, tyrothricin, defensins (when used as direct antimicrobials)

  MODE B — Immunostimulatory / host defense activity:
    Peptides that PROMOTE immune defense against pathogens: recruiting neutrophils/macrophages, enhancing phagocytosis, activating dendritic cells, bridging innate and adaptive immunity, stimulating protective cytokine production.
    Examples: LL-37/cathelicidin, defensins (alpha/beta), thymosin alpha-1 (when boosting immune defense), lactoferricin

  MODE C — Anti-biofilm activity:
    Peptides that disrupt or prevent microbial biofilm formation.
    Examples: LL-37, DJK-5, IDR-1018

  MODE D — Pathogen-targeting vaccines and immunogens:
    Peptide-based vaccines that induce immune responses against specific pathogens.
    Examples: StreptInCor (S. pyogenes), peptide-based HIV vaccines, malaria peptide vaccines

  KEY CRITERION: The peptide must have a known or plausible role in DEFENSE AGAINST PATHOGENS — either by directly attacking them or by stimulating the immune system to fight them. The word "antimicrobial" is broad: it covers direct killing AND immune-mediated defense.

  DEFINITELY NOT AMPs — these are peptides with NO antimicrobial or host defense role:
  - GLP-1/GLP-2 analogues (semaglutide, liraglutide, tirzepatide, apraglutide) — metabolic hormones
  - GnRH analogues (leuprolide, goserelin) — reproductive hormones
  - Somatostatin analogues (octreotide, lanreotide) — growth hormone inhibitors
  - VIP/Aviptadil — vasoactive intestinal peptide (vasodilation, NOT immune defense)
  - C-type natriuretic peptides (vosoritide) — bone growth regulators
  - Peptides for diabetes, obesity, bone disorders, GI motility, psychiatric conditions
  - Peptides that SUPPRESS immune responses (e.g., for autoimmune diseases) — immunosuppression is the OPPOSITE of host defense
  - Radiolabeled peptide conjugates where the peptide is a targeting vector and the therapeutic mechanism is radiation (e.g., 177Lu-DOTATATE)

  BORDERLINE CASES — think carefully:
  - A peptide derived from a bacterial protein used to SUPPRESS immune responses in autoimmunity → NOT an AMP (suppressing defense, not promoting it)
  - A peptide that promotes wound healing WITHOUT any antimicrobial mechanism → NOT an AMP
  - A peptide that promotes wound healing AND has antimicrobial or immune-boosting properties → IS an AMP
  - Self-assembling peptides for dental remineralization → NOT an AMP (physical/chemical mechanism, not antimicrobial, even though caries are bacterial)

  If NOT an AMP → STOP → answer "Other".

STEP 3 — Does this AMP target infection specifically?
  AMP(infection): The trial's therapeutic goal is treating or preventing infection, infectious disease, antimicrobial resistance, sepsis, or pathogen-specific conditions.
  AMP(other): The AMP or AMP-derived peptide is used for a non-infection purpose: wound healing, cancer immunotherapy, anti-inflammatory, biofilm in non-infectious context.

WORKED EXAMPLES:

Colistin for urinary tract infection → AMP(infection)
  Step 1: Peptide=True. Step 2: Colistin is a classic AMP (Mode A: direct antimicrobial). Step 3: UTI is an infection.

LL-37 for diabetic wound healing → AMP(other)
  Step 1: Peptide=True. Step 2: LL-37 is an AMP (cathelicidin, Modes A+B+C). Step 3: Wound healing is NOT treating an active infection.

Thymosin alpha-1 for chronic hepatitis B → AMP(infection)
  Step 1: Peptide=True. Step 2: Thymosin alpha-1 boosts immune defense (Mode B: immunostimulatory). Step 3: Hepatitis B is an infection.

Defensin-based peptide for cancer immunotherapy → AMP(other)
  Step 1: Peptide=True. Step 2: Defensin is an AMP (Modes A+B). Step 3: Cancer, not infection.

StreptInCor vaccine against Streptococcus pyogenes → AMP(infection)
  Step 1: Peptide=True. Step 2: Peptide vaccine targeting a pathogen (Mode D). Step 3: S. pyogenes = infection.

Semaglutide for type 2 diabetes → Other
  Step 1: Peptide=True. Step 2: GLP-1 analogue — metabolic hormone, NO antimicrobial or immune defense role. NOT an AMP. STOP.

Tirzepatide for obesity/psychiatric conditions → Other
  Step 1: Peptide=True. Step 2: GIP/GLP-1 dual agonist — metabolic hormone. NOT an AMP. STOP.

dnaJP1 for rheumatoid arthritis → Other
  Step 1: Peptide=True. Step 2: Although derived from bacterial HSP, it SUPPRESSES T-cell responses for autoimmunity. Immunosuppression is the OPPOSITE of host defense. NOT an AMP. STOP.

Vosoritide (BMN 111) for achondroplasia → Other
  Step 1: Peptide=True. Step 2: C-type natriuretic peptide analogue for bone growth. NOT an AMP. STOP.

Pembrolizumab for melanoma → Other
  Step 1: Peptide=False (monoclonal antibody). STOP.

P11-4 self-assembling peptide for dental caries remineralization → Other
  Step 1: Peptide=True. Step 2: P11-4 works by nucleating hydroxyapatite crystals — a physical/chemical mechanism. It does not kill bacteria or stimulate immune defense. NOT an AMP despite caries being bacterial. STOP.

IMPORTANT: Format your response EXACTLY as:

Classification: [AMP(infection), AMP(other), or Other]
Evidence: [Cite the specific source, identifier, and excerpt that supports your decision]
Reasoning: [Walk through Step 1 → Step 2 → Step 3]"""


class ClassificationAgent(BaseAnnotationAgent):
    """Determines AMP vs Other classification."""

    field_name = "classification"

    async def annotate(
        self,
        nct_id: str,
        research_results: list[ResearchResult],
        metadata: Optional[dict] = None,
    ) -> FieldAnnotation:
        # Gather all relevant citations from research
        all_citations = []
        for result in research_results:
            weight = self.relevance_weight(result.agent_name)
            for citation in result.citations:
                all_citations.append((citation, weight))

        # Sort by relevance weight descending
        all_citations.sort(key=lambda x: x[1], reverse=True)

        # Build evidence text for the LLM prompt
        # Include peptide determination if available from metadata
        peptide_value = metadata.get("peptide_result", "Unknown") if metadata else "Unknown"
        evidence_text = f"Trial: {nct_id}\n\n"
        evidence_text += f"Peptide determination: {peptide_value}\n\n"
        cited_sources = []
        for citation, weight in all_citations[:20]:
            evidence_text += f"[{citation.source_name}] {citation.identifier or ''}: {citation.snippet}\n"
            cited_sources.append(citation)

        # Call LLM
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
                value="Unknown",
                confidence=0.0,
                reasoning=f"LLM call failed: {e}",
                evidence=[],
                model_name=primary_model,
            )

        # Parse response
        value = self._parse_value(raw_text)
        reasoning = self._parse_reasoning(raw_text)

        # Compute quality score from citations
        unique_sources = set(c.source_name for c in cited_sources)
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
        # Try to match the full classification line
        match = re.search(r"Classification:\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
        if match:
            raw = match.group(1).strip().lower()
            if "amp(infection)" in raw or "amp (infection)" in raw:
                return "AMP(infection)"
            if "amp(other)" in raw or "amp (other)" in raw:
                return "AMP(other)"
            if "other" in raw:
                return "Other"
            # If model just said "AMP" without subtype — default to "Other"
            # because bare "AMP" is ambiguous and most peptides are NOT AMPs.
            # This is safer than guessing a subtype.
            if "amp" in raw:
                return "Other"
            return "Other"
        # Fallback: scan for explicit AMP(subtype) mentions
        lower_text = text.lower()
        if "amp(infection)" in lower_text or "amp (infection)" in lower_text:
            return "AMP(infection)"
        if "amp(other)" in lower_text or "amp (other)" in lower_text:
            return "AMP(other)"
        return "Other"

    def _parse_reasoning(self, text: str) -> str:
        match = re.search(r"Reasoning:\s*(.+?)(?:\n\n|$)", text, re.DOTALL)
        if match:
            return match.group(1).strip()[:500]
        return text[:500]

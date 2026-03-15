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

STEP 2 — Is this peptide an ANTIMICROBIAL peptide (AMP)?
  AMPs are peptides that kill or inhibit microorganisms, OR peptide-based therapeutics designed to target pathogens.
  - YES, it is an AMP: colistin, polymyxin B, daptomycin, nisin, defensins, LL-37, gramicidin, bacitracin, melittin, magainin, cecropin, vancomycin, tyrothricin
  - YES, counts as AMP: peptide vaccines targeting pathogens (StreptInCor against S. pyogenes, peptide-based HIV vaccines)
  - NO, NOT an AMP: GLP-1/GLP-2 analogues (semaglutide, liraglutide, apraglutide) — these are metabolic hormone peptides
  - NO, NOT an AMP: VIP/Aviptadil — vasoactive intestinal peptide, a hormone, not antimicrobial
  - NO, NOT an AMP: GnRH analogues (leuprolide, goserelin) — reproductive hormone peptides
  - NO, NOT an AMP: Somatostatin analogues (octreotide, lanreotide) — growth hormone-inhibiting peptides
  - NO, NOT an AMP: Peptides for cancer, diabetes, obesity, GvHD, headaches, GI motility that have no antimicrobial activity
  If NOT an AMP → STOP → answer "Other".

STEP 3 — Does this AMP target infection specifically?
  - Infection, pathogens, antimicrobial resistance, bacterial/viral/fungal disease → "AMP(infection)"
  - Non-infection uses of AMPs: wound healing, cancer immunotherapy, biofilm disruption (non-infectious) → "AMP(other)"

WORKED EXAMPLES:

Colistin for urinary tract infection → AMP(infection)
  Step 1: Peptide=True. Step 2: Colistin is a classic AMP. Step 3: UTI is an infection.

LL-37 for diabetic wound healing → AMP(other)
  Step 1: Peptide=True. Step 2: LL-37 is an AMP (cathelicidin). Step 3: Wound healing, not infection.

StreptInCor vaccine against Streptococcus pyogenes → AMP(infection)
  Step 1: Peptide=True. Step 2: Peptide vaccine targeting a pathogen = counts as AMP. Step 3: S. pyogenes = infection.

VIP/Aviptadil for COVID-19 ARDS → Other
  Step 1: Peptide=True. Step 2: VIP is a vasoactive hormone peptide, NOT an antimicrobial peptide. STOP → Other.

Semaglutide for type 2 diabetes → Other
  Step 1: Peptide=True. Step 2: GLP-1 analogue, NOT an AMP. STOP → Other.

Apraglutide for GvHD → Other
  Step 1: Peptide=True. Step 2: GLP-2 analogue, NOT an AMP. STOP → Other.

Amoxicillin for bacterial pneumonia → Other
  Step 1: Peptide=False (small molecule). STOP → Other.

Pembrolizumab for melanoma → Other
  Step 1: Peptide=False (monoclonal antibody). STOP → Other.

Kate Farm Peptide 1.5 for gastroparesis → Other
  Step 1: Peptide=False (nutritional formula). STOP → Other.

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

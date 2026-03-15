"""
Classification Annotation Agent — Two-Pass Investigative Design.

Determines whether a clinical trial involves an Antimicrobial Peptide (AMP)
and its purpose. Uses a two-pass approach:
  Pass 1: Extract antimicrobial evidence (database hits, mechanism, target)
  Pass 2: Apply the AMP decision tree to extracted facts

Uses a larger model (14B on Mac Mini, 70B+ on server) because the 8B model
has demonstrated inability to follow the multi-step decision tree reliably.
"""

import logging
import re
from typing import Optional

from agents.base import BaseAnnotationAgent, FIELD_RELEVANCE
from app.models.research import ResearchResult, SourceCitation
from app.models.annotation import FieldAnnotation

logger = logging.getLogger("agent_annotate.annotation.classification")

VALID_VALUES = ["AMP(infection)", "AMP(other)", "Other"]

# Hardware profile → model selection for classification
# Classification uses a larger model because 8B ignores worked examples
MODEL_OVERRIDES = {
    "mac_mini": "qwen2.5:14b",
    "server": "qwen2.5:72b",
}

# --------------------------------------------------------------------------- #
#  Pass 1: Extract antimicrobial evidence from research data
# --------------------------------------------------------------------------- #

PASS1_SYSTEM = """You are a biochemistry fact-extraction specialist. Your job is to extract ONLY factual evidence about whether a peptide has antimicrobial or host defense properties. Do NOT classify — just extract facts.

For the clinical trial intervention below, answer these 5 questions using ONLY the provided evidence. If the evidence does not answer a question, write "No evidence found."

1. PEPTIDE IDENTITY: What is the intervention? Is it confirmed as a peptide? What is its amino acid length or molecular class?

2. DATABASE MATCHES: Was this peptide found in any antimicrobial peptide databases (DRAMP, APD3, UniProt with "antimicrobial" annotation)? List specific database hits.

3. MECHANISM OF ACTION: What is the peptide's known or proposed mechanism? Specifically:
   - Does it directly kill or inhibit microorganisms (bacteria, viruses, fungi)?
   - Does it stimulate immune defense (recruit immune cells, enhance phagocytosis, activate dendritic cells)?
   - Does it disrupt biofilms?
   - Does it work via a non-antimicrobial mechanism (metabolic hormone, bone growth, vasodilation, immunosuppression, physical/chemical)?

4. THERAPEUTIC TARGET: What disease or condition is the trial treating? Is it an infection, infectious disease, or pathogen-specific condition? Or is it cancer, autoimmune, metabolic, structural, or other?

5. IMMUNE DIRECTION: Does this peptide PROMOTE immune defense (stimulate, recruit, activate) or SUPPRESS immune responses (tolerize, inhibit, dampen)? Or is it immune-neutral (metabolic/structural)?

Format your response EXACTLY as:
Peptide Identity: [answer]
Database Matches: [answer]
Mechanism: [answer]
Therapeutic Target: [answer]
Immune Direction: [answer]"""

# --------------------------------------------------------------------------- #
#  Pass 2: Apply AMP decision tree to extracted facts
# --------------------------------------------------------------------------- #

PASS2_SYSTEM = """You are a clinical trial classification specialist. AMP stands for Antimicrobial Peptide.

You have been given EXTRACTED FACTS about a peptide intervention. Use ONLY these facts to classify the trial. Do NOT add information not present in the facts.

THREE-STEP DECISION TREE:

STEP 1 — Is the intervention a peptide?
  Check the Peptide determination. If Peptide = False → STOP → answer "Other".

STEP 2 — Is this peptide an AMP (Antimicrobial Peptide / Host Defense Peptide)?

  An AMP participates in defense against pathogens through ANY of these modes:
  A) Direct antimicrobial: kills/inhibits microorganisms
  B) Immunostimulatory: PROMOTES immune defense against pathogens
  C) Anti-biofilm: disrupts microbial biofilms
  D) Pathogen-targeting vaccine: induces immune responses against specific pathogens

  CHECK THE EXTRACTED FACTS:
  - Database Matches: If found in DRAMP or APD3 → strong evidence FOR AMP
  - Mechanism: If direct antimicrobial or immunostimulatory against pathogens → AMP
  - Immune Direction: If "PROMOTE" → supports AMP. If "SUPPRESS" → NOT an AMP. If "immune-neutral" → NOT an AMP.

  NOT AMPs (even if peptide=True):
  - Metabolic hormones (GLP-1, GLP-2, GnRH, somatostatin, GIP)
  - Vasodilators (VIP/Aviptadil)
  - Bone growth regulators (vosoritide/CNP)
  - Immunosuppressive peptides (suppress T-cells for autoimmune disease)
  - Self-assembling/structural peptides (physical mechanism, not biological)
  - Cancer neoantigen vaccines (target tumor cells, NOT pathogens)
  - Radiolabeled peptide conjugates (peptide is targeting vector, not the drug)

  If NOT an AMP → STOP → answer "Other".

STEP 3 — Does this AMP target infection?
  AMP(infection): Trial treats infection, infectious disease, AMR, sepsis, or pathogen-specific conditions.
  AMP(other): AMP used for wound healing, cancer immunotherapy, anti-inflammatory, or non-infectious biofilm.

CRITICAL RULES:
- If Database Matches says "No evidence found" AND Mechanism shows no antimicrobial/immunostimulatory activity → almost certainly "Other"
- If Immune Direction says "SUPPRESS" → always "Other" regardless of peptide origin
- Cancer neoantigen vaccines target tumor antigens NOT pathogen antigens → "Other"
- Collagen peptides, nutritional peptides, structural peptides → "Other"

Format your response EXACTLY as:
Classification: [AMP(infection), AMP(other), or Other]
Reasoning: [Walk through Step 1 → 2 → 3 using the extracted facts]"""

# --------------------------------------------------------------------------- #
#  Deterministic fallback if Pass 2 fails
# --------------------------------------------------------------------------- #

def _fallback_classify(pass1_text: str, peptide_value: str) -> str:
    """Keyword-based fallback if Pass 2 LLM call fails."""
    if peptide_value == "False":
        return "Other"

    lower = pass1_text.lower()

    # Strong AMP signals from database matches
    has_dramp = "dramp" in lower and "no evidence" not in lower.split("database matches")[1][:100] if "database matches" in lower else False
    has_antimicrobial_mechanism = any(kw in lower for kw in [
        "kills bacteria", "inhibits bacteria", "membrane disruption",
        "pore formation", "bactericidal", "bacteriostatic", "antimicrobial activity"
    ])
    has_immunostim = "promote" in lower and "immune" in lower
    has_suppress = "suppress" in lower and "immune" in lower

    # Immune suppression → always Other
    if has_suppress:
        return "Other"

    # Strong NOT-AMP signals
    not_amp_keywords = [
        "metabolic hormone", "glp-1", "glp-2", "gnrh", "somatostatin",
        "vasoactive", "bone growth", "natriuretic", "self-assembling",
        "remineralization", "neoantigen", "radiolabeled", "nutritional",
        "collagen", "immune-neutral",
    ]
    if any(kw in lower for kw in not_amp_keywords):
        return "Other"

    if has_dramp or has_antimicrobial_mechanism or has_immunostim:
        # Check if infection target
        infection_keywords = ["infection", "bacterial", "viral", "fungal",
                              "sepsis", "antimicrobial resistance", "pathogen"]
        if any(kw in lower for kw in infection_keywords):
            return "AMP(infection)"
        return "AMP(other)"

    return "Other"


class ClassificationAgent(BaseAnnotationAgent):
    """Two-pass AMP classification with hardware-aware model selection."""

    field_name = "classification"

    def _get_model(self, config) -> str:
        """Select model based on hardware profile. Classification uses a
        larger model because 8B models ignore the multi-step decision tree."""
        profile = config.orchestrator.hardware_profile
        override = MODEL_OVERRIDES.get(profile)
        if override:
            return override
        # Fallback: use reconciler model (largest available)
        for model_key, model_cfg in config.verification.models.items():
            if model_cfg.role == "reconciler":
                return model_cfg.name
        return "qwen2.5:14b"

    async def annotate(
        self,
        nct_id: str,
        research_results: list[ResearchResult],
        metadata: Optional[dict] = None,
    ) -> FieldAnnotation:
        from app.services.ollama_client import ollama_client
        from app.services.config_service import config_service

        config = config_service.get()
        model = self._get_model(config)

        # Gather citations sorted by relevance
        all_citations = []
        for result in research_results:
            weight = self.relevance_weight(result.agent_name)
            for citation in result.citations:
                all_citations.append((citation, weight))
        all_citations.sort(key=lambda x: x[1], reverse=True)

        cited_sources = [c for c, _ in all_citations[:30]]

        # Build evidence text with DRAMP/database signals highlighted
        peptide_value = metadata.get("peptide_result", "Unknown") if metadata else "Unknown"
        evidence_text = f"Trial: {nct_id}\n"
        evidence_text += f"Peptide determination: {peptide_value}\n\n"

        # Highlight database matches at top of evidence
        dramp_hits = []
        uniprot_hits = []
        for result in research_results:
            if result.agent_name == "peptide_identity" and not result.error:
                for citation in result.citations:
                    if citation.source_name == "dramp":
                        dramp_hits.append(citation)
                    elif citation.source_name == "uniprot":
                        uniprot_hits.append(citation)

        if dramp_hits:
            evidence_text += "DRAMP (Antimicrobial Peptide Database) MATCHES:\n"
            for c in dramp_hits:
                evidence_text += f"  {c.identifier}: {c.snippet}\n"
            evidence_text += "\n"
        if uniprot_hits:
            evidence_text += "UniProt MATCHES:\n"
            for c in uniprot_hits:
                evidence_text += f"  {c.identifier}: {c.snippet}\n"
            evidence_text += "\n"

        evidence_text += "ALL EVIDENCE:\n"
        for citation in cited_sources:
            evidence_text += f"[{citation.source_name}] {citation.identifier or ''}: {citation.snippet}\n"

        # --- Pass 1: Extract antimicrobial evidence ---
        logger.info(f"  classification: Pass 1 — extracting AMP evidence for {nct_id}")
        try:
            pass1_response = await ollama_client.generate(
                model=model,
                prompt=evidence_text,
                system=PASS1_SYSTEM,
                temperature=config.ollama.temperature,
            )
            pass1_text = pass1_response.get("response", "")
        except Exception as e:
            logger.error(f"  classification: Pass 1 failed: {e}")
            return FieldAnnotation(
                field_name=self.field_name,
                value="Other",
                confidence=0.0,
                reasoning=f"Pass 1 LLM call failed: {e}",
                evidence=[],
                model_name=model,
            )

        # --- Pass 2: Apply decision tree to extracted facts ---
        logger.info(f"  classification: Pass 2 — applying decision tree for {nct_id}")
        pass2_prompt = f"Trial: {nct_id}\n"
        pass2_prompt += f"Peptide determination: {peptide_value}\n\n"
        pass2_prompt += f"EXTRACTED FACTS FROM EVIDENCE:\n{pass1_text}\n"

        try:
            pass2_response = await ollama_client.generate(
                model=model,
                prompt=pass2_prompt,
                system=PASS2_SYSTEM,
                temperature=config.ollama.temperature,
            )
            pass2_text = pass2_response.get("response", "")
        except Exception as e:
            logger.warning(f"  classification: Pass 2 failed, using fallback: {e}")
            value = _fallback_classify(pass1_text, peptide_value)
            return FieldAnnotation(
                field_name=self.field_name,
                value=value,
                confidence=0.3,
                reasoning=f"[Pass 2 failed, fallback used] Pass 1: {pass1_text[:400]}",
                evidence=cited_sources[:10],
                model_name=model,
            )

        # Parse Pass 2 response
        value = self._parse_value(pass2_text)
        # Combine both passes in reasoning for audit trail
        reasoning = f"[Pass 1 extraction] {pass1_text[:400]}\n[Pass 2 decision] {pass2_text[:400]}"

        quality = sum(c.quality_score for c in cited_sources[:10]) / max(len(cited_sources[:10]), 1)

        return FieldAnnotation(
            field_name=self.field_name,
            value=value,
            confidence=quality,
            reasoning=reasoning,
            evidence=cited_sources[:10],
            model_name=model,
        )

    def _parse_value(self, text: str) -> str:
        match = re.search(r"Classification:\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
        if match:
            raw = match.group(1).strip().lower()
            if "amp(infection)" in raw or "amp (infection)" in raw:
                return "AMP(infection)"
            if "amp(other)" in raw or "amp (other)" in raw:
                return "AMP(other)"
            if "other" in raw:
                return "Other"
            if "amp" in raw:
                return "Other"
            return "Other"
        lower_text = text.lower()
        if "amp(infection)" in lower_text or "amp (infection)" in lower_text:
            return "AMP(infection)"
        if "amp(other)" in lower_text or "amp (other)" in lower_text:
            return "AMP(other)"
        return "Other"

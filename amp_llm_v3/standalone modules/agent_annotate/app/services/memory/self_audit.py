"""
EDAM Self-Audit: Evidence-driven consistency checking.

Runs post-annotation on every trial (not just flagged ones) and catches
cases where the agent's output contradicts its own research evidence.
No human annotations needed — the structured data IS the ground truth.

Two audit types:
1. Delivery mode audit: checks if research contains explicit route keywords
   (INTRAVENOUS, SUBCUTANEOUS, INTRAMUSCULAR, etc.) that the agent ignored.
2. Peptide audit: checks if research contains amino acid counts or database
   matches that contradict the agent's peptide=True/False decision.

Corrections from self-audit are stored with the concrete evidence citation
and weighted as "self_review" (moderate decay, evidence-grounded).
"""

import json
import logging
import re
from typing import Optional

from app.services.memory.memory_store import MemoryStore

logger = logging.getLogger("agent_annotate.edam.self_audit")

# ---------------------------------------------------------------------------
# Delivery mode: route keywords in structured data
# ---------------------------------------------------------------------------
# These map evidence keywords to the correct delivery mode value.
# Only triggers when the agent output a LESS specific value.
_ROUTE_EVIDENCE_MAP = {
    # FDA route field values (exact matches from OpenFDA)
    "intravenous": "IV",
    "oral": None,  # too ambiguous alone — need subtype
    "subcutaneous": "Injection/Infusion - Subcutaneous/Intradermal",
    "intramuscular": "Injection/Infusion - Intramuscular",
    "intranasal": "Intranasal",
    "inhalation": "Inhalation",
    "topical": None,  # too ambiguous alone
    # Protocol text patterns
    "iv infusion": "IV",
    "iv push": "IV",
    "iv injection": "IV",
    "intravenous infusion": "IV",
    "intravenous injection": "IV",
    "subcutaneous injection": "Injection/Infusion - Subcutaneous/Intradermal",
    "intramuscular injection": "Injection/Infusion - Intramuscular",
    "sub-q": "Injection/Infusion - Subcutaneous/Intradermal",
    "s.c.": "Injection/Infusion - Subcutaneous/Intradermal",
    "i.m.": "Injection/Infusion - Intramuscular",
    "i.v.": "IV",
}

# Agent outputs that are "less specific" — these are the ones we might correct
_UNSPECIFIC_ROUTES = {
    "Injection/Infusion - Other/Unspecified",
    "Other/Unspecified",
}

# ---------------------------------------------------------------------------
# Peptide: amino acid evidence in structured data
# ---------------------------------------------------------------------------
_PEPTIDE_TRUE_PATTERNS = [
    # UniProt/DRAMP evidence of peptide nature
    r"(\d+)\s*amino\s*acid",
    r"(\d+)\s*(?:aa|AA|a\.a\.)\b",
    r"(\d+)\s*residues?\b",
    r"peptide\s+(?:hormone|analogue|vaccine|therapeutic|drug|antibiotic)",
    r"(?:GLP-[12]|GnRH|somatostatin|calcitonin|oxytocin|vasopressin)\s+(?:analog|analogue|agonist|receptor)",
    r"antimicrobial\s+peptide",
    r"lipopeptide",
    r"glycopeptide",
    r"cyclic\s+peptide",
    r"neuropeptide",
]

_PEPTIDE_FALSE_PATTERNS = [
    # Evidence that it's NOT a peptide therapeutic
    r"monoclonal\s+antibody",
    r"(?:mAb|IgG\d?)\b",
    r"nutritional\s+formula",
    r"hydrolyzed\s+protein",
    r"small\s+molecule",
    r"gene\s+therapy",
]


class SelfAuditor:
    """Post-annotation evidence consistency checker."""

    def __init__(self, memory: MemoryStore):
        self._memory = memory

    async def audit_trial(self, nct_id: str, trial_result: dict,
                          config_hash: str, git_commit: str) -> list[dict]:
        """
        Audit a single trial's annotations against its research evidence.

        Returns a list of correction dicts for any inconsistencies found.
        Each correction has concrete evidence citations.
        """
        corrections = []

        annotations = trial_result.get("annotations", [])
        research_results = trial_result.get("research_results", [])
        verification = trial_result.get("verification", {})
        fields = verification.get("fields", [])

        ann_by_field = {}
        for a in annotations:
            fn = a.get("field_name", "")
            ann_by_field[fn] = a

        final_by_field = {}
        for f in fields:
            fn = f.get("field_name", "")
            final_by_field[fn] = f.get("final_value", "")

        # Build searchable evidence text from all research
        evidence_text = ""
        evidence_citations = []
        for rr in research_results:
            if isinstance(rr, dict) and not rr.get("error"):
                for c in rr.get("citations", []):
                    snippet = c.get("snippet", "")
                    source = c.get("source_name", "")
                    identifier = c.get("identifier", "")
                    evidence_text += f" {snippet}"
                    evidence_citations.append({
                        "source": source,
                        "identifier": identifier,
                        "text": snippet[:200],
                    })
            # Also check raw_data for structured fields
            if isinstance(rr, dict) and rr.get("raw_data"):
                raw = rr["raw_data"]
                if isinstance(raw, dict):
                    evidence_text += f" {json.dumps(raw)}"

        evidence_lower = evidence_text.lower()

        # --- Delivery mode audit ---
        dm_correction = self._audit_delivery_mode(
            nct_id, final_by_field.get("delivery_mode", ""),
            evidence_lower, evidence_citations,
        )
        if dm_correction:
            corrections.append(dm_correction)

        # --- Peptide audit ---
        pep_correction = self._audit_peptide(
            nct_id, final_by_field.get("peptide", ""),
            evidence_lower, evidence_citations,
        )
        if pep_correction:
            corrections.append(pep_correction)

        # Store any corrections found
        for corr in corrections:
            try:
                corr_id = self._memory.store_correction(
                    nct_id=nct_id,
                    field_name=corr["field_name"],
                    job_id=corr.get("job_id", ""),
                    original_value=corr["original_value"],
                    corrected_value=corr["corrected_value"],
                    source="self_audit",
                    reflection=corr["reflection"],
                    evidence_citations=corr["evidence_citations"],
                    config_hash=config_hash,
                    git_commit=git_commit,
                )
                # Store embedding for similarity search
                embed_text = (
                    f"Trial {nct_id}, field {corr['field_name']}: "
                    f"corrected from '{corr['original_value']}' to "
                    f"'{corr['corrected_value']}'. {corr['reflection'][:200]}"
                )
                try:
                    await self._memory.store_embedding("corrections", corr_id, embed_text)
                except Exception:
                    pass

                logger.info(
                    "EDAM self-audit: %s/%s — '%s' → '%s' (%s)",
                    nct_id, corr["field_name"],
                    corr["original_value"], corr["corrected_value"],
                    corr["reflection"][:80],
                )
            except Exception as e:
                logger.warning("EDAM self-audit correction storage failed: %s", e)

        return corrections

    def _audit_delivery_mode(
        self, nct_id: str, agent_value: str,
        evidence_lower: str, all_citations: list[dict],
    ) -> Optional[dict]:
        """Check if evidence contains explicit route that agent missed."""
        if agent_value not in _UNSPECIFIC_ROUTES:
            return None  # agent was already specific

        # Search evidence for route keywords
        best_match = None
        best_citation = None
        for keyword, correct_value in _ROUTE_EVIDENCE_MAP.items():
            if correct_value is None:
                continue  # ambiguous keyword
            if keyword in evidence_lower:
                # Find the citation that contains this keyword
                for c in all_citations:
                    if keyword in c.get("text", "").lower():
                        best_match = correct_value
                        best_citation = c
                        break
                if best_match:
                    break

        if not best_match or best_match == agent_value:
            return None

        return {
            "field_name": "delivery_mode",
            "original_value": agent_value,
            "corrected_value": best_match,
            "reflection": (
                f"Evidence contains explicit route '{best_match}' "
                f"(source: {best_citation['source']}) but agent defaulted to "
                f"'{agent_value}'. The specific route in the evidence should "
                f"override the generic classification."
            ),
            "evidence_citations": [best_citation],
        }

    def _audit_peptide(
        self, nct_id: str, agent_value: str,
        evidence_lower: str, all_citations: list[dict],
    ) -> Optional[dict]:
        """Check if evidence about amino acid count contradicts the peptide annotation."""
        # Check for amino acid count evidence
        aa_count = None
        aa_citation = None
        for pattern in _PEPTIDE_TRUE_PATTERNS[:3]:  # first 3 are AA count patterns
            match = re.search(pattern, evidence_lower)
            if match:
                try:
                    count = int(match.group(1))
                    if 2 <= count <= 100:  # peptide range
                        aa_count = count
                        # Find citation
                        for c in all_citations:
                            if match.group(0) in c.get("text", "").lower():
                                aa_citation = c
                                break
                        break
                except (ValueError, IndexError):
                    pass

        # Check peptide=False with AA count in peptide range
        if agent_value == "False" and aa_count is not None:
            # But also check for False-confirming evidence
            for pattern in _PEPTIDE_FALSE_PATTERNS:
                if re.search(pattern, evidence_lower):
                    return None  # legitimate False (e.g., monoclonal antibody)

            citation = aa_citation or (all_citations[0] if all_citations else {"source": "evidence", "text": f"{aa_count} amino acids found"})
            return {
                "field_name": "peptide",
                "original_value": "False",
                "corrected_value": "True",
                "reflection": (
                    f"Evidence shows {aa_count} amino acid residues (peptide range 2-100), "
                    f"but agent classified as False. Source: {citation.get('source', '?')}. "
                    f"No monoclonal antibody or nutritional formula evidence found to justify False."
                ),
                "evidence_citations": [citation],
            }

        # Check peptide=True with strong non-peptide evidence
        if agent_value == "True":
            for pattern in _PEPTIDE_FALSE_PATTERNS:
                match = re.search(pattern, evidence_lower)
                if match:
                    citation = None
                    for c in all_citations:
                        if match.group(0) in c.get("text", "").lower():
                            citation = c
                            break
                    if citation:
                        return {
                            "field_name": "peptide",
                            "original_value": "True",
                            "corrected_value": "False",
                            "reflection": (
                                f"Evidence indicates this is a {match.group(0)} "
                                f"(not a peptide therapeutic). Source: {citation['source']}."
                            ),
                            "evidence_citations": [citation],
                        }

        return None

    async def audit_job(self, job_id: str, all_trial_results: list[dict],
                        config_hash: str, git_commit: str) -> dict:
        """
        Audit all trials in a completed job.

        Returns summary dict with correction counts.
        """
        total_corrections = 0
        dm_corrections = 0
        pep_corrections = 0

        for trial in all_trial_results:
            nct_id = trial.get("nct_id", "")
            if not nct_id:
                continue

            corrections = await self.audit_trial(
                nct_id, trial, config_hash, git_commit
            )

            for c in corrections:
                c["job_id"] = job_id
                total_corrections += 1
                if c["field_name"] == "delivery_mode":
                    dm_corrections += 1
                elif c["field_name"] == "peptide":
                    pep_corrections += 1

        summary = {
            "total_corrections": total_corrections,
            "delivery_mode_corrections": dm_corrections,
            "peptide_corrections": pep_corrections,
        }

        logger.info(
            "EDAM self-audit: %d corrections (%d delivery_mode, %d peptide)",
            total_corrections, dm_corrections, pep_corrections,
        )
        return summary

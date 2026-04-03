"""
EDAM Self-Audit: Evidence-driven consistency checking (v11).

Runs post-annotation on every trial (not just flagged ones) and catches
cases where the agent's output contradicts its own research evidence.
No human annotations needed — the structured data IS the ground truth.

Three audit sources (v10):
1. Citation snippets: checks if citation text contains explicit keywords
2. Raw data: checks structured OpenFDA/ClinicalTrials.gov data
3. Agent reasoning: checks if the agent's own Pass 1 extraction found a
   specific value that Pass 2 then ignored (internal contradiction)

Four audit types (v11, expanded from 2):
1. Delivery mode audit: checks for route keywords (INTRAVENOUS, etc.)
2. Peptide audit: rebalanced — requires 2+ non-peptide signals for True→False,
   guards on database hits, expanded False→True patterns
3. Outcome audit (NEW): catches Positive without publications, missed Recruiting,
   Unknown with hasResults=true
4. Classification audit (NEW): catches missed AMP drugs classified as Other

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
# Peptide: amino acid evidence in structured data (v11 rebalanced)
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
    # v11: Expanded False→True patterns (more database/identity signals)
    r"uniprot",
    r"\bdramp\b",
    r"\bdbaasp\b",
    r"\bapd3?\b",
    r"peptide\s+bond",
    r"polypeptide",
    r"insulin\s+analog",
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

# ---------------------------------------------------------------------------
# Outcome: registry/evidence consistency (v11 NEW)
# ---------------------------------------------------------------------------
_RECRUITING_KEYWORDS = [
    "recruiting", "not yet recruiting", "enrolling by invitation",
    "actively recruiting", "open for enrollment",
]

# ---------------------------------------------------------------------------
# Classification: known AMP drugs (v11 NEW) — imported from classification.py
# ---------------------------------------------------------------------------
_KNOWN_AMP_DRUGS_AUDIT = {
    "colistin", "colistimethate", "polymyxin b", "polymyxin e",
    "daptomycin", "nisin", "gramicidin", "tyrothricin", "bacitracin",
    "vancomycin", "teicoplanin", "telavancin", "dalbavancin", "oritavancin",
    "ramoplanin", "surotomycin", "friulimicin",
    "ll-37", "ll37", "cathelicidin", "defensin", "hbd-1", "hbd-2", "hbd-3",
    "hnp-1", "hnp-2", "hnp-3", "hd-5", "hd-6",
    "thymosin alpha-1", "thymosin alpha 1", "thymalfasin", "zadaxin",
    "melittin", "magainin", "cecropin", "lactoferricin", "lactoferrin",
    "pexiganan", "msrdn-1", "omiganan", "iseganan",
    "djk-5", "idr-1018",
}

_INFECTION_KEYWORDS_AUDIT = {
    "infection", "infectious", "bacterial", "viral", "fungal", "sepsis",
    "septic", "pneumonia", "meningitis", "endocarditis", "bacteremia",
    "peritonitis", "osteomyelitis", "wound infection",
    "mrsa", "vre", "drug-resistant", "tuberculosis",
}


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
        raw_data_list = []
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
                    raw_data_list.append(raw)

        evidence_lower = evidence_text.lower()

        # --- Delivery mode audit ---
        dm_ann = ann_by_field.get("delivery_mode", {})
        dm_reasoning = dm_ann.get("reasoning", "")
        dm_correction = self._audit_delivery_mode(
            nct_id, final_by_field.get("delivery_mode", ""),
            evidence_lower, evidence_citations,
            annotation_reasoning=dm_reasoning,
        )
        if dm_correction:
            corrections.append(dm_correction)

        # --- Peptide audit (v11 rebalanced) ---
        pep_correction = self._audit_peptide(
            nct_id, final_by_field.get("peptide", ""),
            evidence_lower, evidence_citations,
        )
        if pep_correction:
            corrections.append(pep_correction)

        # --- Outcome audit (v11 NEW) ---
        outcome_ann = ann_by_field.get("outcome", {})
        outcome_reasoning = outcome_ann.get("reasoning", "")
        outcome_correction = self._audit_outcome(
            nct_id, final_by_field.get("outcome", ""),
            evidence_lower, evidence_citations, raw_data_list,
            annotation_reasoning=outcome_reasoning,
        )
        if outcome_correction:
            corrections.append(outcome_correction)

        # --- Classification audit (v11 NEW) ---
        class_correction = self._audit_classification(
            nct_id, final_by_field.get("classification", ""),
            evidence_lower, evidence_citations,
        )
        if class_correction:
            corrections.append(class_correction)

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
        annotation_reasoning: str = "",
    ) -> Optional[dict]:
        """Check if evidence or agent reasoning contains explicit route that was missed.

        v10: Also searches the agent's own Pass 1 output (stored in reasoning).
        This catches the common case where Pass 1 correctly extracts a specific
        route but Pass 2 defaults to Other/Unspecified anyway.
        """
        if agent_value not in _UNSPECIFIC_ROUTES:
            return None  # agent was already specific

        # --- Source 1: Search citation snippets + raw_data for route keywords ---
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

        if best_match and best_match != agent_value:
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

        # --- Source 2: Search agent's own Pass 1 reasoning for contradictions ---
        if annotation_reasoning:
            reasoning_lower = annotation_reasoning.lower()
            for keyword, correct_value in _ROUTE_EVIDENCE_MAP.items():
                if correct_value is None:
                    continue
                if keyword in reasoning_lower:
                    return {
                        "field_name": "delivery_mode",
                        "original_value": agent_value,
                        "corrected_value": correct_value,
                        "reflection": (
                            f"Agent's own Pass 1 extraction found '{keyword}' "
                            f"but Pass 2 defaulted to '{agent_value}'. The model's "
                            f"extraction contradicts its own classification."
                        ),
                        "evidence_citations": [],
                    }

        return None

    def _audit_peptide(
        self, nct_id: str, agent_value: str,
        evidence_lower: str, all_citations: list[dict],
    ) -> Optional[dict]:
        """Check if evidence about amino acid count contradicts the peptide annotation.

        v11: Rebalanced to reduce True→False overcorrection:
        - False→True: expanded patterns (database hits, peptide keywords)
        - True→False: now requires 2+ non-peptide signals AND no database hits
        """
        # --- Check peptide=False with peptide-confirming evidence ---
        if agent_value == "False":
            # First check for AA count evidence (strongest signal)
            aa_count = None
            aa_citation = None
            for pattern in _PEPTIDE_TRUE_PATTERNS[:3]:  # AA count patterns
                match = re.search(pattern, evidence_lower)
                if match:
                    try:
                        count = int(match.group(1))
                        if 2 <= count <= 100:  # peptide range (v27b: 2-100)
                            aa_count = count
                            for c in all_citations:
                                if match.group(0) in c.get("text", "").lower():
                                    aa_citation = c
                                    break
                            break
                    except (ValueError, IndexError):
                        pass

            if aa_count is not None:
                # Check for False-confirming evidence
                for pattern in _PEPTIDE_FALSE_PATTERNS:
                    if re.search(pattern, evidence_lower):
                        return None  # legitimate False
                citation = aa_citation or (all_citations[0] if all_citations else {"source": "evidence", "text": f"{aa_count} amino acids found"})
                return {
                    "field_name": "peptide",
                    "original_value": "False",
                    "corrected_value": "True",
                    "reflection": (
                        f"Evidence shows {aa_count} amino acid residues (peptide range 2-50), "
                        f"but agent classified as False. Source: {citation.get('source', '?')}. "
                        f"No monoclonal antibody or nutritional formula evidence found to justify False."
                    ),
                    "evidence_citations": [citation],
                }

            # v11: Also check for database hits or semantic peptide patterns
            has_db_hit = any(
                re.search(pattern, evidence_lower)
                for pattern in _PEPTIDE_TRUE_PATTERNS[10:]  # database patterns
            )
            has_semantic = any(
                re.search(pattern, evidence_lower)
                for pattern in _PEPTIDE_TRUE_PATTERNS[3:10]  # semantic patterns
            )
            if has_db_hit and has_semantic:
                # Both database hit AND semantic signal → likely peptide
                for pattern in _PEPTIDE_FALSE_PATTERNS:
                    if re.search(pattern, evidence_lower):
                        return None
                return {
                    "field_name": "peptide",
                    "original_value": "False",
                    "corrected_value": "True",
                    "reflection": (
                        "Evidence contains both peptide database hits and semantic "
                        "peptide keywords, but agent classified as False. "
                        "No non-peptide evidence found to justify False."
                    ),
                    "evidence_citations": all_citations[:1] if all_citations else [],
                }

        # --- Check peptide=True with strong non-peptide evidence (v11: require 2+ signals) ---
        if agent_value == "True":
            # v11: Guard — if ANY peptide database hit exists, do NOT correct True→False
            has_any_db = any(
                re.search(pattern, evidence_lower)
                for pattern in _PEPTIDE_TRUE_PATTERNS[10:]  # database patterns
            )
            if has_any_db:
                return None  # database evidence supports True

            # Require 2+ non-peptide signals (not just 1 keyword match)
            false_signal_count = 0
            false_match_text = None
            false_citation = None
            for pattern in _PEPTIDE_FALSE_PATTERNS:
                match = re.search(pattern, evidence_lower)
                if match:
                    false_signal_count += 1
                    if false_match_text is None:
                        false_match_text = match.group(0)
                        for c in all_citations:
                            if match.group(0) in c.get("text", "").lower():
                                false_citation = c
                                break

            if false_signal_count >= 2 and false_citation:
                return {
                    "field_name": "peptide",
                    "original_value": "True",
                    "corrected_value": "False",
                    "reflection": (
                        f"Evidence contains {false_signal_count} non-peptide signals "
                        f"(including '{false_match_text}') and no peptide database hits. "
                        f"Source: {false_citation['source']}."
                    ),
                    "evidence_citations": [false_citation],
                }

        return None

    def _audit_outcome(
        self, nct_id: str, agent_value: str,
        evidence_lower: str, all_citations: list[dict],
        raw_data_list: list[dict],
        annotation_reasoning: str = "",
    ) -> Optional[dict]:
        """v11: Check outcome annotation against registry evidence.

        Catches three common errors:
        1. Agent says "Positive" but no publication evidence exists
        2. Registry says recruiting but agent didn't output "Recruiting"
        3. Agent says "Unknown" but hasResults=true
        """
        # --- Check 1: Positive without ANY supporting evidence ---
        # v12: Widened keyword list and added result-related terms.
        # The v11 version was too aggressive, correcting Positive→Unknown
        # when evidence existed in forms not covered by the narrow keyword check.
        if agent_value == "Positive":
            has_evidence = any(kw in evidence_lower for kw in [
                "pubmed", "pmc", "doi:", "published", "journal",
                "efficacy", "effective", "met primary endpoint",
                "results", "phase ii", "phase iii", "phase 2", "phase 3",
                "approved", "fda", "ema", "market", "commercial",
                "succeeded", "successful", "completed",
            ])
            has_results_posted = False
            for raw in raw_data_list:
                proto = raw.get("protocol_section", raw.get("protocolSection", {}))
                status_mod = proto.get("statusModule", {})
                hr = status_mod.get("hasResults", False)
                if hr is True or str(hr).lower() == "true":
                    has_results_posted = True
                    break

            if not has_evidence and not has_results_posted:
                return {
                    "field_name": "outcome",
                    "original_value": "Positive",
                    "corrected_value": "Unknown",
                    "reflection": (
                        "Agent classified outcome as Positive but no supporting "
                        "evidence (publications, results, approval, later phases) "
                        "and no hasResults=true found. Positive requires corroboration."
                    ),
                    "evidence_citations": all_citations[:1] if all_citations else [],
                }

        # --- Check 2: Registry says recruiting but agent missed it ---
        if agent_value not in ("Recruiting",):
            for raw in raw_data_list:
                proto = raw.get("protocol_section", raw.get("protocolSection", {}))
                status_mod = proto.get("statusModule", {})
                overall_status = status_mod.get("overallStatus", "").upper()
                if overall_status in ("RECRUITING", "NOT_YET_RECRUITING", "ENROLLING_BY_INVITATION"):
                    return {
                        "field_name": "outcome",
                        "original_value": agent_value,
                        "corrected_value": "Recruiting",
                        "reflection": (
                            f"Registry overallStatus is '{overall_status}' but agent "
                            f"output '{agent_value}'. Registry status should take precedence."
                        ),
                        "evidence_citations": [],
                    }

        # --- Check 3: Unknown with hasResults=true ---
        if agent_value == "Unknown":
            for raw in raw_data_list:
                proto = raw.get("protocol_section", raw.get("protocolSection", {}))
                status_mod = proto.get("statusModule", {})
                hr = status_mod.get("hasResults", False)
                overall = status_mod.get("overallStatus", "").upper()
                if (hr is True or str(hr).lower() == "true") and overall == "COMPLETED":
                    return {
                        "field_name": "outcome",
                        "original_value": "Unknown",
                        "corrected_value": "Positive",
                        "reflection": (
                            "Agent classified as Unknown but registry shows "
                            "COMPLETED with hasResults=true. Results were posted, "
                            "indicating reportable outcomes."
                        ),
                        "evidence_citations": [],
                    }

        return None

    def _audit_classification(
        self, nct_id: str, agent_value: str,
        evidence_lower: str, all_citations: list[dict],
    ) -> Optional[dict]:
        """v11: Check if a known AMP drug was classified as Other.

        Only corrects when intervention name matches _KNOWN_AMP_DRUGS_AUDIT
        in the evidence text but agent output was "Other".
        """
        if agent_value != "Other":
            return None  # only correct Other → AMP

        # Search evidence for known AMP drug names
        matched_drug = None
        for drug in _KNOWN_AMP_DRUGS_AUDIT:
            if drug in evidence_lower:
                matched_drug = drug
                break

        if not matched_drug:
            # Also check for DRAMP/DBAASP database hits
            if "dramp" in evidence_lower or "dbaasp" in evidence_lower:
                matched_drug = "AMP database hit"
            else:
                return None

        # Determine infection context
        is_infection = any(kw in evidence_lower for kw in _INFECTION_KEYWORDS_AUDIT)
        corrected = "AMP"

        # Find citation
        citation = None
        for c in all_citations:
            text = c.get("text", "").lower()
            if matched_drug in text or "dramp" in text or "antimicrobial" in text:
                citation = c
                break

        return {
            "field_name": "classification",
            "original_value": "Other",
            "corrected_value": corrected,
            "reflection": (
                f"Evidence contains known AMP signal ('{matched_drug}') but agent "
                f"classified as Other. Infection context: {is_infection}."
            ),
            "evidence_citations": [citation] if citation else [],
        }

    async def audit_job(self, job_id: str, all_trial_results: list[dict],
                        config_hash: str, git_commit: str) -> dict:
        """
        Audit all trials in a completed job.

        Returns summary dict with correction counts.
        """
        total_corrections = 0
        dm_corrections = 0
        pep_corrections = 0
        outcome_corrections = 0
        class_corrections = 0

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
                elif c["field_name"] == "outcome":
                    outcome_corrections += 1
                elif c["field_name"] == "classification":
                    class_corrections += 1

        summary = {
            "total_corrections": total_corrections,
            "delivery_mode_corrections": dm_corrections,
            "peptide_corrections": pep_corrections,
            "outcome_corrections": outcome_corrections,
            "classification_corrections": class_corrections,
        }

        logger.info(
            "EDAM self-audit: %d corrections (%d dm, %d pep, %d outcome, %d class)",
            total_corrections, dm_corrections, pep_corrections,
            outcome_corrections, class_corrections,
        )
        return summary

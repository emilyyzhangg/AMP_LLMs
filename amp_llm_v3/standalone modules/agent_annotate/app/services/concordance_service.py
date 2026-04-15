"""
Agreement engine for agent-annotate.

Computes inter-rater agreement metrics between:
  - Agent annotations (from job result JSON files)
  - Human annotations (from CSV, two replicates: ann1/ann2)

Supports: agent_vs_r1, agent_vs_r2, r1_vs_r2, compare_jobs, concordance_history.
"""

import json
import logging
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

import csv
import re

from app.config import RESULTS_DIR
from app.services.concordance_stats import (
    cohens_kappa as _cohens_kappa_impl,
    kappa_confidence_interval,
    gwets_ac1_with_ci,
    prevalence_index,
    bias_index,
)
from app.models.concordance import (
    AnnotatorInfo,
    CategoryMetrics,
    ComparisonFieldDelta,
    ComparisonResult,
    ConcordanceHistory,
    ConcordanceHistoryEntry,
    ConcordanceResult,
    Disagreement,
    JobConcordance,
    SequenceAnalysis,
    SequenceAnalysisSummary,
    SequenceComparisonDetail,
)

logger = logging.getLogger("agent_annotate.concordance")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
CSV_PATH = Path(
    "/Users/amphoraxe/Developer/amphoraxe/dev-llm.amphoraxe.ca/amp_llm_v3/standalone modules/"
    "agent_annotate/docs/human_ground_truth_train_df.csv"
)
JSON_DIR = RESULTS_DIR / "json"

# ---------------------------------------------------------------------------
# Field definitions (CSV column name-based)
# ---------------------------------------------------------------------------
FIELDS = {
    "classification": {"csv_ann1": "Classification_ann1", "csv_ann2": "Classification_ann2", "blank_means_skip": True},
    "delivery_mode": {"csv_ann1": "Delivery Mode_ann1", "csv_ann2": "Delivery Mode_ann2", "blank_means_skip": True},
    "outcome": {"csv_ann1": "Outcome_ann1", "csv_ann2": "Outcome_ann2", "blank_means_skip": True},
    "reason_for_failure": {"csv_ann1": "Reason for Failure_ann1", "csv_ann2": "Reason for Failure_ann2", "blank_means_skip": False},
    "peptide": {"csv_ann1": "Peptide_ann1", "csv_ann2": "Peptide_ann2", "blank_means_skip": True},
    "sequence": {"csv_ann1": "Sequence_ann1", "csv_ann2": "Sequence_ann2", "blank_means_skip": True},
}

# ---------------------------------------------------------------------------
# Value normalisation aliases
# ---------------------------------------------------------------------------
CLASSIFICATION_ALIASES: dict[str, str] = {
    "amp": "AMP", "amp(infection)": "AMP", "amp(other)": "AMP",
    "amp (infection)": "AMP", "amp (other)": "AMP", "other": "Other",
}

DELIVERY_MODE_ALIASES: dict[str, str] = {
    "iv": "Injection/Infusion", "intravenous": "Injection/Infusion",
    "injection/infusion - intramuscular": "Injection/Infusion",
    "injection/infusion - subcutaneous/intradermal": "Injection/Infusion",
    "injection/infusion - other/unspecified": "Injection/Infusion",
    "injection/infusion": "Injection/Infusion",
    "subcutaneous": "Injection/Infusion", "intradermal": "Injection/Infusion",
    "subcutaneous/intradermal": "Injection/Infusion",
    "intramuscular": "Injection/Infusion", "intravitreal": "Injection/Infusion",
    "sc": "Injection/Infusion",
    "oral - tablet": "Oral", "oral - capsule": "Oral", "oral - food": "Oral",
    "oral - drink": "Oral", "oral - unspecified": "Oral", "oral": "Oral",
    "topical - cream/gel": "Topical", "topical - powder": "Topical",
    "topical - spray": "Topical", "topical - strip/covering": "Topical",
    "topical - wash": "Topical", "topical - unspecified": "Topical", "topical": "Topical",
    "inhalation": "Other", "intranasal": "Other",
    "other/unspecified": "Other", "other": "Other",
}

OUTCOME_ALIASES: dict[str, str] = {
    "active": "Active", "active, not recruiting": "Active",
    "active not recruiting": "Active", "recruiting": "Recruiting",
    "failed - completed trial": "Failed - completed trial",
    "positive": "Positive", "terminated": "Terminated",
    "withdrawn": "Withdrawn", "unknown": "Unknown",
}

REASON_ALIASES: dict[str, str] = {
    "business reason": "Business Reason",
    "business_reason": "Business Reason",
    "ineffective for purpose": "Ineffective for purpose",
    "ineffective_for_purpose": "Ineffective for purpose",
    "recruitment issues": "Recruitment issues",
    "recruitment_issues": "Recruitment issues",
    "toxic/unsafe": "Toxic/Unsafe",
    "toxic_unsafe": "Toxic/Unsafe",
    "due to covid": "Due to covid",
    "due_to_covid": "Due to covid",
    "unknown": "Unknown",
}

PEPTIDE_ALIASES: dict[str, str] = {
    "true": "TRUE", "false": "FALSE",
    "yes": "TRUE", "no": "FALSE",
    "1": "TRUE", "0": "FALSE",
}

# ---------------------------------------------------------------------------
# Blank handling standard (universal rule)
# ---------------------------------------------------------------------------
#
# BLANK_HANDLING_STANDARD:
#
# An NCT is considered "annotated" by a human only if at least one of the
# five annotation fields (classification, delivery_mode, outcome,
# reason_for_failure, peptide) has a non-blank value. Rows where all five
# fields are blank/None are treated as unannotated — the annotator was
# assigned the row but did not engage with it.
#
# This applies universally:
#   - Annotator NCT counts: only count rows with at least one filled field
#   - Annotator-filtered concordance: only include annotated rows
#   - Per-field concordance: blank_means_skip=True fields skip when EITHER
#     side is blank. reason_for_failure uses outcome-aware blank handling
#     (blank reason + blank outcome = skipped trial, not "no failure").
#   - Agent annotations always have all 5 fields filled (never blank).
#
# This standard exists because many annotators left large portions of their
# assigned rows blank (e.g., Ali 12%, Emre 7%, Berke 11% coverage). Without
# this filter, annotator counts are inflated and concordance includes
# unannotated trials as false disagreements.
# ---------------------------------------------------------------------------


def _has_any_annotation(field_data: dict[str, str]) -> bool:
    """Check if at least one annotation field has a non-blank value.

    Uses the universal blank handling standard: an NCT is only considered
    annotated if at least one of the five fields is filled.
    """
    for field_name in FIELDS:
        raw = field_data.get(field_name, "")
        _, is_blank = _normalise(raw, field_name)
        if not is_blank:
            return True
    return False


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------
def _normalise(value: object, field_name: str) -> tuple[str, bool]:
    """Normalise a value for comparison.

    Returns (normalised_string, is_blank).
    """
    if value is None:
        return ("", True)

    # CSV stores Peptide as string
    if isinstance(value, bool):
        return (str(value).upper(), False)

    s = str(value).strip()
    if s == "" or s.lower() in ("none", "n/a"):
        return ("", True)

    s_lower = s.lower()

    if field_name == "delivery_mode":
        # Multi-value: normalise each part, sort alphabetically
        parts = [p.strip() for p in s.split(",")]
        normalised_parts = []
        for part in parts:
            part_lower = part.strip().lower()
            normalised_parts.append(
                DELIVERY_MODE_ALIASES.get(part_lower, part.strip()).lower()
            )
        normalised_parts.sort()
        result = ", ".join(normalised_parts)
    elif field_name == "outcome":
        result = OUTCOME_ALIASES.get(s_lower, s)
    elif field_name == "classification":
        result = CLASSIFICATION_ALIASES.get(s_lower, s)
    elif field_name == "reason_for_failure":
        result = REASON_ALIASES.get(s_lower, s)
    elif field_name == "peptide":
        result = PEPTIDE_ALIASES.get(s_lower, s)
    else:
        result = s

    # Case-normalize for comparison: uppercase for peptide (TRUE/FALSE),
    # lowercase for everything else
    if field_name == "peptide":
        return (result.upper(), False)
    return (result.lower(), False)


# ---------------------------------------------------------------------------
# Grouped normalisation (simplified categories for high-level comparison)
# ---------------------------------------------------------------------------
def _normalise_grouped(value: str, field_name: str) -> str:
    """Apply grouping to an already-normalised value.

    Reduces granular categories to broad buckets:
    - Classification: AMP(infection)/AMP(other) → AMP
    - Delivery mode: injection subtypes → Injection/Infusion, oral → Oral, etc.
    - Outcome: Active not recruiting/Recruiting → Active
    - Peptide: unchanged (already binary)
    - Reason for failure: unchanged
    - Sequence: unchanged
    """
    if not value:
        return value

    v_lower = value.lower()

    if field_name == "classification":
        if v_lower.startswith("amp"):
            return "AMP"
        return "Other"

    elif field_name == "delivery_mode":
        # Handle multi-value (comma-separated)
        parts = [p.strip().lower() for p in value.split(",")]
        buckets = set()
        for p in parts:
            if "iv" == p or "injection" in p or "infusion" in p or "intravenous" in p or "subcutaneous" in p or "intradermal" in p or "intramuscular" in p:
                buckets.add("Injection/Infusion")
            elif "oral" in p:
                buckets.add("Oral")
            elif "topical" in p:
                buckets.add("Topical")
            elif "inhalation" in p or "inhaled" in p:
                buckets.add("Inhalation")
            else:
                buckets.add("Other")
        return ", ".join(sorted(buckets))

    elif field_name == "outcome":
        if v_lower in ("active, not recruiting", "recruiting"):
            return "Active"
        return value  # Positive, Failed, Terminated, Withdrawn, Unknown stay

    # peptide, reason_for_failure, sequence: no grouping
    return value



# ---------------------------------------------------------------------------
# Sequence-specific normalisation (v23: order-agnostic comparison)
# ---------------------------------------------------------------------------
def _canonicalise_single_sequence(seq: str) -> str:
    """Reduce a single sequence string to its canonical form for comparison.

    Strips: whitespace, hyphens, parenthesised modifications, case → uppercase.
    This lets us detect 'same molecule, different format' situations.
    """
    s = seq.strip()
    if not s or s.upper() in ("N/A", "NONE", ""):
        return ""
    # Remove parenthesised modifications: (Ac), (NH2), etc.
    s = re.sub(r"\([^)]*\)", "", s)
    # Remove hyphens (format artefact)
    s = s.replace("-", "")
    # Remove spaces
    s = s.replace(" ", "")
    # Uppercase (D-amino acid lowercase → uppercase for canonical)
    s = s.upper()
    return s


def _normalise_sequence_for_comparison(
    raw: str,
) -> tuple[frozenset[str], list[str]]:
    """Normalise a sequence field value for order-agnostic comparison.

    Returns:
        (canonical_set, display_list)
        - canonical_set: frozenset of canonical AA strings (uppercase, no mods)
        - display_list: sorted list of original (trimmed) sequence strings
    """
    if raw is None:
        return (frozenset(), [])
    s = str(raw).strip()
    if not s or s.upper() in ("N/A", "NONE"):
        return (frozenset(), [])

    # Split on pipe separator
    parts = [p.strip() for p in s.split("|")]
    parts = [p for p in parts if p]

    canonical_set: set[str] = set()
    display_list: list[str] = []
    for part in parts:
        canon = _canonicalise_single_sequence(part)
        if canon:
            canonical_set.add(canon)
            display_list.append(part)

    display_list.sort()
    return (frozenset(canonical_set), display_list)


def _compare_sequences(
    raw_a: str, raw_b: str, nct_id: str,
) -> SequenceComparisonDetail:
    """Compare two sequence field values and classify the match type.

    Match types:
      EXACT   — identical display strings
      ORDER   — same sequences, different order
      FORMAT  — same canonical set, different display formatting
      PARTIAL — some sequences overlap, but count differs
      MISMATCH — no canonical overlap at all
      MISSING — both sides blank/N/A
    """
    canon_a, display_a = _normalise_sequence_for_comparison(raw_a)
    canon_b, display_b = _normalise_sequence_for_comparison(raw_b)

    detail = SequenceComparisonDetail(
        nct_id=nct_id,
        agent_sequences=display_a,
        human_sequences=display_b,
        match_type="MISSING",
        matched_sequences=[],
        agent_only=[],
        human_only=[],
        format_differences=[],
    )

    # Both empty
    if not canon_a and not canon_b:
        detail.match_type = "MISSING"
        return detail

    # One side empty
    if not canon_a or not canon_b:
        detail.match_type = "MISMATCH"
        detail.agent_only = list(canon_a) if canon_a else []
        detail.human_only = list(canon_b) if canon_b else []
        return detail

    # Check canonical sets
    shared = canon_a & canon_b
    a_only = canon_a - canon_b
    b_only = canon_b - canon_a

    detail.matched_sequences = sorted(shared)
    detail.agent_only = sorted(a_only)
    detail.human_only = sorted(b_only)

    if canon_a == canon_b:
        # Same canonical set — check display formatting
        norm_a_str = str(raw_a).strip()
        norm_b_str = str(raw_b).strip()
        if norm_a_str == norm_b_str:
            detail.match_type = "EXACT"
        elif display_a == display_b:
            # Same sorted display but original order differed
            detail.match_type = "ORDER"
        else:
            # Same canonical set but display differs (formatting)
            detail.match_type = "FORMAT"
            # Build format diff descriptions
            # Map canonical → display for each side
            map_a: dict[str, str] = {}
            map_b: dict[str, str] = {}
            parts_a = [p.strip() for p in str(raw_a).split("|") if p.strip()]
            parts_b = [p.strip() for p in str(raw_b).split("|") if p.strip()]
            for p in parts_a:
                c = _canonicalise_single_sequence(p)
                if c:
                    map_a[c] = p
            for p in parts_b:
                c = _canonicalise_single_sequence(p)
                if c:
                    map_b[c] = p
            for canon_seq in shared:
                da = map_a.get(canon_seq, "?")
                db = map_b.get(canon_seq, "?")
                if da != db:
                    detail.format_differences.append(
                        f"Agent: {da}, Human: {db} (same canonical: {canon_seq})"
                    )
    elif shared:
        # Partial overlap
        detail.match_type = "PARTIAL"
    else:
        # No overlap at all
        detail.match_type = "MISMATCH"

    return detail


# ---------------------------------------------------------------------------
# Cohen's Kappa (from scratch, no sklearn)
# ---------------------------------------------------------------------------
def _cohens_kappa(labels_a: list[str], labels_b: list[str]) -> Optional[float]:
    """Compute Cohen's kappa via shared stats module.

    Returns kappa value, or None if computation is not possible (n=0).
    """
    if len(labels_a) == 0:
        return None
    kappa, po, pe = _cohens_kappa_impl(labels_a, labels_b)
    if math.isnan(kappa):
        return None
    return round(kappa, 4)


def _kappa_interpretation(k: Optional[float]) -> str:
    """Landis & Koch (1977) interpretation of kappa (delegates to stats module)."""
    from app.services.concordance_stats import landis_koch_interpretation
    if k is None:
        return "N/A"
    return landis_koch_interpretation(k)


# ---------------------------------------------------------------------------
# Data loading: CSV (human annotations)
# ---------------------------------------------------------------------------
_csv_cache: Optional[dict[str, dict]] = None
_csv_mtime: float = 0.0


def _load_csv_annotations() -> dict[str, dict]:
    """Load human annotations from training CSV.

    v35: Auto-reloads when CSV file is modified (mtime check).

    Returns: {nct_id: {
        'r1': {field: raw_value},  # ann1 = Emily
        'r2': {field: raw_value},  # ann2 = others
        'r1_annotator': 'Emily',
        'r2_annotator': str,       # from A2_annotator column
    }}
    """
    global _csv_cache, _csv_mtime
    if _csv_cache is not None and CSV_PATH.exists():
        current_mtime = CSV_PATH.stat().st_mtime
        if current_mtime == _csv_mtime:
            return _csv_cache
        logger.info("CSV file modified (mtime %.0f → %.0f), reloading", _csv_mtime, current_mtime)
        _csv_cache = None

    if not CSV_PATH.exists():
        logger.error("CSV file not found: %s", CSV_PATH)
        return {}

    logger.info("Loading human annotations from %s", CSV_PATH)
    data: dict[str, dict] = {}

    with open(CSV_PATH, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            nct = row.get("nct_id", "").strip()
            if not nct:
                continue
            # Normalize NCT ID to uppercase
            nct = nct.upper() if not nct.startswith("NCT") else "NCT" + nct[3:]

            entry = {"r1": {}, "r2": {}, "r1_annotator": "Emily", "r2_annotator": row.get("A2_annotator", "").strip()}

            for field_name, field_def in FIELDS.items():
                ann1_col = field_def["csv_ann1"]
                ann2_col = field_def["csv_ann2"]
                entry["r1"][field_name] = row.get(ann1_col, "").strip()
                entry["r2"][field_name] = row.get(ann2_col, "").strip()

            data[nct] = entry

    _csv_cache = data
    _csv_mtime = CSV_PATH.stat().st_mtime
    logger.info("Loaded %d NCT IDs from CSV (mtime %.0f)", len(_csv_cache), _csv_mtime)
    return _csv_cache


def invalidate_csv_cache() -> None:
    """Force reload of CSV data on next access (e.g. if file is updated)."""
    global _csv_cache, _csv_mtime
    _csv_cache = None
    _csv_mtime = 0.0


# ---------------------------------------------------------------------------
# Data loading: Agent annotations (from job JSON)
# ---------------------------------------------------------------------------
def _load_agent_annotations(job_id: str) -> dict[str, dict[str, str]]:
    """Load agent annotations from a single job JSON file.

    Extracts final_value from verification.fields for each trial,
    with fallback to annotations array.

    Returns: {nct_id: {field_name: value}}
    """
    json_path = JSON_DIR / f"{job_id}.json"
    if not json_path.exists():
        logger.error("Job JSON not found: %s", json_path)
        return {}

    with open(json_path, "r") as f:
        job = json.load(f)

    data: dict[str, dict[str, str]] = {}
    trials = job.get("trials", [])

    for trial in trials:
        nct_id = trial.get("nct_id", "")
        if not nct_id:
            continue

        entry: dict[str, str] = {}
        verification = trial.get("verification") or {}
        fields_list = verification.get("fields") or []

        for field_obj in fields_list:
            fname = field_obj.get("field_name", "")
            fval = field_obj.get("final_value", "")
            if fname in FIELDS:
                entry[fname] = fval

        # Fallback to annotations array for missing fields
        for anno in trial.get("annotations", []):
            fname = anno.get("field_name", "")
            if fname in FIELDS and fname not in entry:
                entry[fname] = anno.get("value", "")

        # Fill missing fields with empty
        for fname in FIELDS:
            if fname not in entry:
                entry[fname] = ""

        data[nct_id] = entry

    return data


def _load_agent_annotations_multi(job_ids: list[str]) -> dict[str, dict[str, str]]:
    """Load and merge agent annotations from multiple jobs.

    When the same NCT appears in multiple jobs, the LATEST job's annotation
    wins (based on job order in the list — callers should sort by timestamp).
    This represents the agent's best attempt with the most EDAM corrections.

    Returns: {nct_id: {field_name: value}}
    """
    merged: dict[str, dict[str, str]] = {}
    for job_id in job_ids:
        job_data = _load_agent_annotations(job_id)
        # Later jobs overwrite earlier ones for the same NCT
        merged.update(job_data)
    return merged


def _get_job_timestamp(job_id: str) -> Optional[str]:
    """Extract the timestamp from a job JSON file."""
    json_path = JSON_DIR / f"{job_id}.json"
    if not json_path.exists():
        return None
    try:
        with open(json_path, "r") as f:
            job = json.load(f)
        return job.get("version", {}).get("timestamp")
    except Exception:
        return None


def _list_completed_jobs() -> list[str]:
    """List all job IDs that have JSON result files."""
    if not JSON_DIR.exists():
        return []
    return sorted(
        p.stem for p in JSON_DIR.glob("*.json")
    )


# ---------------------------------------------------------------------------
# Core concordance computation
# ---------------------------------------------------------------------------
def _compute_field_concordance(
    data_a: dict[str, dict[str, str]],
    data_b: dict[str, dict[str, str]],
    label_a: str,
    label_b: str,
    field_name: str,
    common_ncts: list[str],
    grouped: bool = False,
) -> ConcordanceResult:
    """Compute concordance for a single field between two annotation sets.

    Parameters:
        data_a: {nct_id: {field: value}} for annotator A
        data_b: {nct_id: {field: value}} for annotator B
        label_a: Human-readable name for annotator A (e.g. "Agent", "R1")
        label_b: Human-readable name for annotator B
        field_name: The annotation field to compare
        common_ncts: Sorted list of NCT IDs present in both datasets
    """
    field_def = FIELDS[field_name]
    blank_means_skip = field_def["blank_means_skip"]

    labels_a: list[str] = []
    labels_b: list[str] = []
    disagreements: list[Disagreement] = []
    skipped = 0
    cascade_skipped = 0       # v34: peptide=False cascade skips
    cascade_victims: list[str] = []  # v34: agent N/A but GT has real values

    # Confusion matrix: {value_a: {value_b: count}}
    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    # Value distributions per annotator
    dist_a: Counter = Counter()
    dist_b: Counter = Counter()

    for nct in common_ncts:
        raw_a = data_a.get(nct, {}).get(field_name, "")
        raw_b = data_b.get(nct, {}).get(field_name, "")

        norm_a, blank_a = _normalise(raw_a, field_name)
        norm_b, blank_b = _normalise(raw_b, field_name)

        # v24: Skip non-peptide fields when either side has peptide=False
        if field_name != "peptide":
            pep_a = data_a.get(nct, {}).get("peptide", "")
            pep_b = data_b.get(nct, {}).get("peptide", "")
            pep_a_str = str(pep_a).strip().lower()
            pep_b_str = str(pep_b).strip().lower()
            if pep_a_str == "false" or pep_b_str == "false":
                skipped += 1
                cascade_skipped += 1
                # v34: Track cascade victims — agent=N/A but GT has real value
                if pep_a_str == "false" and pep_b_str == "true" and not blank_b:
                    cascade_victims.append(nct)
                elif pep_b_str == "false" and pep_a_str == "true" and not blank_a:
                    cascade_victims.append(nct)
                continue

        # Blank handling
        if blank_means_skip and (blank_a or blank_b):
            skipped += 1
            continue

        # For reason_for_failure: outcome-aware blank handling (v3/v24).
        # A blank reason is only meaningful if the annotator actually engaged
        # with the trial (i.e., filled in the outcome field). If both outcome
        # AND reason are blank, the annotator skipped the trial entirely.
        if field_name == "reason_for_failure":
            outcome_a = data_a.get(nct, {}).get("outcome", "")
            outcome_b = data_b.get(nct, {}).get("outcome", "")
            norm_outcome_a, outcome_a_blank = _normalise(outcome_a, "outcome")
            norm_outcome_b, outcome_b_blank = _normalise(outcome_b, "outcome")

            # Both outcome and reason blank on BOTH sides → skip
            if blank_a and outcome_a_blank and blank_b and outcome_b_blank:
                skipped += 1
                continue
            # One side blank outcome+reason → treat as "no failure" (empty string)
            # but don't skip the trial — the other side has data
            if blank_a and outcome_a_blank:
                norm_a = ""
            if blank_b and outcome_b_blank:
                norm_b = ""

            # v24: Blank reason + failed outcome → treat as "unknown"
            if blank_a and "failed" in norm_outcome_a:
                norm_a = "unknown"
                blank_a = False
            if blank_b and "failed" in norm_outcome_b:
                norm_b = "unknown"
                blank_b = False

            # Remaining blanks are legitimate "no failure" values
            if blank_a:
                norm_a = ""
            if blank_b:
                norm_b = ""
        elif not blank_means_skip:
            if blank_a:
                norm_a = ""
            if blank_b:
                norm_b = ""

        # Apply grouped normalisation if requested
        if grouped:
            norm_a = _normalise_grouped(norm_a, field_name)
            norm_b = _normalise_grouped(norm_b, field_name)

        # v23: Sequence field uses order-agnostic canonical comparison
        if field_name == "sequence":
            canon_a, _ = _normalise_sequence_for_comparison(norm_a)
            canon_b, _ = _normalise_sequence_for_comparison(norm_b)
            # For AC₁/kappa: use sorted canonical string as the label
            # Same canonical set (regardless of order/format) → same label → agreement
            label_a_seq = " | ".join(sorted(canon_a)) if canon_a else ""
            label_b_seq = " | ".join(sorted(canon_b)) if canon_b else ""
            labels_a.append(label_a_seq)
            labels_b.append(label_b_seq)
        else:
            labels_a.append(norm_a)
            labels_b.append(norm_b)

        # Track distributions
        dist_a[norm_a] += 1
        dist_b[norm_b] += 1

        # Confusion matrix
        confusion[norm_a][norm_b] += 1

        # v37b: For sequence fields, use canonical comparison for disagreement
        # detection (same as AC₁/kappa). Raw comparison wrongly flagged
        # formatting differences like "(nh2)" suffix as disagreements.
        if field_name == "sequence":
            is_disagree = label_a_seq != label_b_seq
        else:
            is_disagree = norm_a != norm_b
        if is_disagree:
            disagreements.append(
                Disagreement(
                    nct_id=nct,
                    field=field_name,
                    value_a=norm_a,
                    value_b=norm_b,
                )
            )

    n = len(labels_a)
    if n > 0:
        agree_count = sum(1 for a, b in zip(labels_a, labels_b) if a == b)
        agree_pct = round((agree_count / n) * 100, 1)
        kappa = _cohens_kappa(labels_a, labels_b)
        _, kappa_ci_lo, kappa_ci_hi = kappa_confidence_interval(labels_a, labels_b)
        ac1_val, ac1_ci_lo, ac1_ci_hi = gwets_ac1_with_ci(labels_a, labels_b)
        pi_val = prevalence_index(labels_a, labels_b)
        bi_val = bias_index(labels_a, labels_b)
    else:
        agree_count = 0
        agree_pct = 0.0
        kappa = None
        kappa_ci_lo, kappa_ci_hi = None, None
        ac1_val, ac1_ci_lo, ac1_ci_hi = None, None, None
        pi_val = None
        bi_val = None

    # Convert defaultdicts to regular dicts for serialisation
    confusion_dict = {k: dict(v) for k, v in confusion.items()}
    distribution = {
        label_a: dict(dist_a),
        label_b: dict(dist_b),
    }

    # ── Per-category precision / recall / F1 ──
    all_values = sorted(set(labels_a) | set(labels_b))
    cat_metrics: list[CategoryMetrics] = []
    for val in all_values:
        tp = sum(1 for a, b in zip(labels_a, labels_b) if a == val and b == val)
        fp = sum(1 for a, b in zip(labels_a, labels_b) if a == val and b != val)
        fn = sum(1 for a, b in zip(labels_a, labels_b) if a != val and b == val)
        cnt_a = tp + fp  # times annotator A said this value
        cnt_b = tp + fn  # times annotator B said this value
        precision = round(tp / (tp + fp), 4) if (tp + fp) > 0 else None
        recall = round(tp / (tp + fn), 4) if (tp + fn) > 0 else None
        if precision is not None and recall is not None and (precision + recall) > 0:
            f1_val = round(2 * precision * recall / (precision + recall), 4)
        else:
            f1_val = None
        cat_metrics.append(CategoryMetrics(
            value=val,
            count_a=cnt_a,
            count_b=cnt_b,
            precision=precision,
            recall=recall,
            f1=f1_val,
        ))

    # Interpretation is now based on AC1 (primary metric)
    interpretation = _kappa_interpretation(ac1_val)

    return ConcordanceResult(
        field_name=field_name,
        n=n,
        skipped=skipped,
        agree_count=agree_count,
        agree_pct=agree_pct,
        kappa=kappa,
        kappa_ci_lower=kappa_ci_lo,
        kappa_ci_upper=kappa_ci_hi,
        ac1=ac1_val,
        ac1_ci_lower=ac1_ci_lo,
        ac1_ci_upper=ac1_ci_hi,
        prevalence_idx=pi_val,
        bias_idx=bi_val,
        interpretation=interpretation,
        category_metrics=cat_metrics,
        confusion_matrix=confusion_dict,
        value_distribution=distribution,
        disagreements=disagreements,
        cascade_skipped=cascade_skipped,
        cascade_victims=cascade_victims,
    )


def _build_job_concordance(
    data_a: dict[str, dict[str, str]],
    data_b: dict[str, dict[str, str]],
    label_a: str,
    label_b: str,
    job_id: str,
    comparison_label: str,
    timestamp: Optional[str] = None,
    grouped: bool = False,
) -> JobConcordance:
    """Build full concordance results across all fields."""
    common_ncts = sorted(set(data_a.keys()) & set(data_b.keys()))

    fields: list[ConcordanceResult] = []
    total_agree = 0
    total_n = 0

    for field_name in FIELDS:
        result = _compute_field_concordance(
            data_a, data_b, label_a, label_b, field_name, common_ncts,
            grouped=grouped,
        )
        fields.append(result)
        total_agree += result.agree_count
        total_n += result.n

    overall_pct = round((total_agree / total_n) * 100, 1) if total_n > 0 else 0.0

    # v23: Build sequence analysis for this comparison
    seq_analysis = _build_sequence_analysis(data_a, data_b, common_ncts)

    return JobConcordance(
        job_id=job_id,
        comparison_label=comparison_label,
        timestamp=timestamp,
        n_overlapping=len(common_ncts),
        fields=fields,
        overall_agree_pct=overall_pct,
        sequence_analysis=seq_analysis,
    )



def _build_sequence_analysis(
    data_a: dict[str, dict[str, str]],
    data_b: dict[str, dict[str, str]],
    common_ncts: list[str],
) -> SequenceAnalysis:
    """Build detailed sequence comparison for all overlapping NCTs.

    v23: Analyses every NCT where at least one side has a sequence value,
    classifies match type, and produces aggregate summary stats.
    """
    details: list[SequenceComparisonDetail] = []
    summary = SequenceAnalysisSummary()

    for nct in common_ncts:
        raw_a = data_a.get(nct, {}).get("sequence", "")
        raw_b = data_b.get(nct, {}).get("sequence", "")

        # Normalise blanks
        _, blank_a = _normalise(raw_a, "sequence")
        _, blank_b = _normalise(raw_b, "sequence")

        if blank_a and blank_b:
            summary.missing_both += 1
            continue
        if blank_a or blank_b:
            # One side has data, other is blank — only include if the
            # non-blank side is not "N/A"
            non_blank = raw_a if not blank_a else raw_b
            norm_val = str(non_blank).strip().upper()
            if norm_val in ("N/A", "NONE", ""):
                summary.missing_both += 1
                continue

        detail = _compare_sequences(raw_a, raw_b, nct)
        if detail.match_type == "MISSING":
            summary.missing_both += 1
            continue

        details.append(detail)
        summary.total_compared += 1

        if detail.match_type == "EXACT":
            summary.exact_matches += 1
            summary.agreement_for_ac += 1
        elif detail.match_type == "ORDER":
            summary.order_matches += 1
            summary.agreement_for_ac += 1
        elif detail.match_type == "FORMAT":
            summary.format_matches += 1
            summary.agreement_for_ac += 1
        elif detail.match_type == "PARTIAL":
            summary.partial_matches += 1
        elif detail.match_type == "MISMATCH":
            summary.full_mismatches += 1

    return SequenceAnalysis(summary=summary, details=details)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def _human_data_as_flat(replicate: str) -> dict[str, dict[str, str]]:
    """Convert human CSV data for a replicate into flat {nct: {field: value}} format.

    Only includes NCTs where the annotator filled in at least one field.
    This matches the universal blank handling standard and the agent
    annotation format so we can reuse _build_job_concordance.
    """
    csv_data = _load_csv_annotations()
    flat: dict[str, dict[str, str]] = {}
    for nct_id, reps in csv_data.items():
        rep_data = reps.get(replicate, {})
        entry = {field: rep_data.get(field, "") for field in FIELDS}
        if _has_any_annotation(entry):
            flat[nct_id] = entry
    return flat


def agent_vs_r1(job_id: str, grouped: bool = False) -> JobConcordance:
    """Compare a single agent job against human replicate 1."""
    agent_data = _load_agent_annotations(job_id)
    if not agent_data:
        return JobConcordance(
            job_id=job_id,
            comparison_label="Agent vs R1",
        )

    r1_data = _human_data_as_flat("r1")
    timestamp = _get_job_timestamp(job_id)

    return _build_job_concordance(
        data_a=agent_data,
        data_b=r1_data,
        label_a="Agent",
        label_b="R1",
        job_id=job_id,
        comparison_label="Agent vs R1",
        timestamp=timestamp,
        grouped=grouped,
    )


def agent_vs_r2(job_id: str, grouped: bool = False) -> JobConcordance:
    """Compare a single agent job against human replicate 2."""
    agent_data = _load_agent_annotations(job_id)
    if not agent_data:
        return JobConcordance(
            job_id=job_id,
            comparison_label="Agent vs R2",
        )

    r2_data = _human_data_as_flat("r2")
    timestamp = _get_job_timestamp(job_id)

    return _build_job_concordance(
        data_a=agent_data,
        data_b=r2_data,
        label_a="Agent",
        label_b="R2",
        job_id=job_id,
        comparison_label="Agent vs R2",
        timestamp=timestamp,
        grouped=grouped,
    )


def r1_vs_r2(grouped: bool = False) -> JobConcordance:
    """Compare human replicate 1 against replicate 2 (inter-rater agreement)."""
    r1_data = _human_data_as_flat("r1")
    r2_data = _human_data_as_flat("r2")

    return _build_job_concordance(
        data_a=r1_data,
        data_b=r2_data,
        label_a="R1",
        label_b="R2",
        job_id="human",
        comparison_label="R1 vs R2",
        grouped=grouped,
    )


def agent_vs_r1_multi(job_ids: list[str], grouped: bool = False) -> JobConcordance:
    """Compare merged agent annotations from multiple jobs against R1.

    Jobs are sorted by timestamp (oldest first) so that later jobs
    overwrite earlier ones for overlapping NCTs — the latest annotation
    represents the agent's best attempt with the most EDAM corrections.
    """
    # Sort jobs by timestamp (oldest first, so latest overwrites)
    sorted_ids = sorted(job_ids, key=lambda jid: _get_job_timestamp(jid) or "")
    agent_data = _load_agent_annotations_multi(sorted_ids)
    if not agent_data:
        return JobConcordance(
            job_id="+".join(job_ids),
            comparison_label="Agent vs R1",
        )

    r1_data = _human_data_as_flat("r1")
    label = f"{len(agent_data)} unique NCTs from {len(job_ids)} jobs"

    return _build_job_concordance(
        data_a=agent_data,
        data_b=r1_data,
        label_a="Agent",
        label_b="R1",
        job_id="+".join(jid[:8] for jid in sorted_ids),
        comparison_label=f"Agent vs R1 ({label})",
        grouped=grouped,
    )


def agent_vs_r2_multi(job_ids: list[str], grouped: bool = False) -> JobConcordance:
    """Compare merged agent annotations from multiple jobs against R2."""
    sorted_ids = sorted(job_ids, key=lambda jid: _get_job_timestamp(jid) or "")
    agent_data = _load_agent_annotations_multi(sorted_ids)
    if not agent_data:
        return JobConcordance(
            job_id="+".join(job_ids),
            comparison_label="Agent vs R2",
        )

    r2_data = _human_data_as_flat("r2")
    label = f"{len(agent_data)} unique NCTs from {len(job_ids)} jobs"

    return _build_job_concordance(
        data_a=agent_data,
        data_b=r2_data,
        label_a="Agent",
        label_b="R2",
        job_id="+".join(jid[:8] for jid in sorted_ids),
        comparison_label=f"Agent vs R2 ({label})",
        grouped=grouped,
    )


def compare_jobs(job_id_a: str, job_id_b: str) -> ComparisonResult:
    """Compare two agent jobs field-by-field against R1.

    For each field, computes kappa for both jobs and reports the delta.
    Positive delta means job_b improved over job_a.
    """
    conc_a = agent_vs_r1(job_id_a)
    conc_b = agent_vs_r1(job_id_b)

    # Index by field for easy lookup
    kappas_a = {f.field_name: f.kappa for f in conc_a.fields}
    kappas_b = {f.field_name: f.kappa for f in conc_b.fields}

    per_field: list[ComparisonFieldDelta] = []
    improved = 0
    regressed = 0
    unchanged = 0

    for field_name in FIELDS:
        ka = kappas_a.get(field_name)
        kb = kappas_b.get(field_name)

        if ka is not None and kb is not None:
            delta = round(kb - ka, 4)
            is_improved = delta > 0.0
            is_regressed = delta < 0.0
        else:
            delta = None
            is_improved = False
            is_regressed = False

        if is_improved:
            improved += 1
        elif is_regressed:
            regressed += 1
        else:
            unchanged += 1

        per_field.append(
            ComparisonFieldDelta(
                field_name=field_name,
                kappa_a=ka,
                kappa_b=kb,
                delta=delta,
                improved=is_improved,
            )
        )

    return ComparisonResult(
        job_id_a=job_id_a,
        job_id_b=job_id_b,
        fields=per_field,
        improved_count=improved,
        regressed_count=regressed,
        unchanged_count=unchanged,
    )


def concordance_history() -> ConcordanceHistory:
    """Compute kappa per field (agent vs R1) across all completed jobs.

    Returns a chronological list of entries sorted by job timestamp.
    """
    job_ids = _list_completed_jobs()
    r1_data = _human_data_as_flat("r1")

    entries: list[ConcordanceHistoryEntry] = []

    for job_id in job_ids:
        agent_data = _load_agent_annotations(job_id)
        if not agent_data:
            continue

        timestamp = _get_job_timestamp(job_id)
        common_ncts = sorted(set(agent_data.keys()) & set(r1_data.keys()))

        if not common_ncts:
            continue

        field_kappas: dict[str, Optional[float]] = {}
        field_ac1s: dict[str, Optional[float]] = {}
        field_agreements: dict[str, Optional[float]] = {}
        for field_name in FIELDS:
            result = _compute_field_concordance(
                agent_data, r1_data, "Agent", "R1", field_name, common_ncts
            )
            field_kappas[field_name] = result.kappa
            field_ac1s[field_name] = result.ac1
            field_agreements[field_name] = result.agree_pct

        # Count trials in this job
        n_trials = len(agent_data)

        entries.append(
            ConcordanceHistoryEntry(
                job_id=job_id,
                timestamp=timestamp,
                field_kappas=field_kappas,
                field_ac1s=field_ac1s,
                field_agreements=field_agreements,
                n_trials=n_trials,
            )
        )

    # Sort by timestamp (None timestamps go first)
    entries.sort(key=lambda e: e.timestamp or "")

    return ConcordanceHistory(history=entries)


# ---------------------------------------------------------------------------
# Annotator-level concordance
# ---------------------------------------------------------------------------
def _human_data_for_annotator(
    annotator: str,
) -> tuple[dict[str, dict[str, str]], str]:
    """Return flat human data filtered to only NCTs by a specific annotator.

    Returns (flat_data, replicate) where replicate is 'r1' or 'r2'.
    Only includes NCTs where the annotator actually filled in at least one
    annotation field. Rows assigned to an annotator but left completely
    blank are excluded — see BLANK_HANDLING_STANDARD in docstring.
    """
    csv_data = _load_csv_annotations()
    flat: dict[str, dict[str, str]] = {}
    detected_replicate = ""

    # Determine which replicate this annotator belongs to.
    # ann1 is always Emily (r1). For r2, check A2_annotator column.
    if annotator == "Emily":
        detected_replicate = "r1"
    else:
        # Check if any NCT has this annotator in r2
        for reps in csv_data.values():
            if reps.get("r2_annotator") == annotator:
                detected_replicate = "r2"
                break
        if not detected_replicate:
            return flat, ""

    for nct_id, reps in csv_data.items():
        if reps.get(f"{detected_replicate}_annotator") == annotator:
            rep_data = reps.get(detected_replicate, {})
            entry = {field: rep_data.get(field, "") for field in FIELDS}
            # Only include if annotator actually filled in at least one field
            if _has_any_annotation(entry):
                flat[nct_id] = entry

    return flat, detected_replicate


def annotator_list() -> list[AnnotatorInfo]:
    """Return a list of all annotators with their ACTUAL annotation counts.

    Only counts NCTs where the annotator filled in at least one annotation
    field. Rows assigned but left blank are not counted.
    """
    csv_data = _load_csv_annotations()

    r1_counts: Counter = Counter()
    r2_counts: Counter = Counter()

    for reps in csv_data.values():
        r1_ann = reps.get("r1_annotator", "")
        r2_ann = reps.get("r2_annotator", "")
        r1_data = reps.get("r1", {})
        r2_data = reps.get("r2", {})

        if r1_ann and _has_any_annotation(r1_data):
            r1_counts[r1_ann] += 1
        if r2_ann and _has_any_annotation(r2_data):
            r2_counts[r2_ann] += 1

    result: list[AnnotatorInfo] = []
    for name, count in sorted(r1_counts.items()):
        result.append(AnnotatorInfo(name=name, replicate="r1", nct_count=count))
    for name, count in sorted(r2_counts.items()):
        result.append(AnnotatorInfo(name=name, replicate="r2", nct_count=count))

    return result


def agent_vs_annotator(job_id: str, annotator: str) -> JobConcordance:
    """Compare an agent job against a specific human annotator's NCTs only."""
    agent_data = _load_agent_annotations(job_id)
    if not agent_data:
        return JobConcordance(
            job_id=job_id,
            comparison_label=f"Agent vs {annotator}",
        )

    ann_data, replicate = _human_data_for_annotator(annotator)
    if not ann_data:
        return JobConcordance(
            job_id=job_id,
            comparison_label=f"Agent vs {annotator}",
        )

    timestamp = _get_job_timestamp(job_id)
    rep_label = replicate.upper()

    return _build_job_concordance(
        data_a=agent_data,
        data_b=ann_data,
        label_a="Agent",
        label_b=f"{annotator} ({rep_label})",
        job_id=job_id,
        comparison_label=f"Agent vs {annotator} ({rep_label})",
        timestamp=timestamp,
    )


def r1_vs_r2_for_annotator(annotator: str) -> JobConcordance:
    """R1 vs R2 filtered to only NCTs annotated by a specific annotator.

    The annotator can be from either replicate. Their NCTs are used to filter
    the comparison between R1 and R2.
    """
    ann_data, replicate = _human_data_for_annotator(annotator)
    if not ann_data:
        return JobConcordance(
            job_id="human",
            comparison_label=f"R1 vs R2 ({annotator})",
        )

    # Get full data for the other replicate, but only for the same NCTs
    other_rep = "r2" if replicate == "r1" else "r1"
    csv_data = _load_csv_annotations()
    other_flat: dict[str, dict[str, str]] = {}
    for nct_id in ann_data:
        if nct_id in csv_data:
            rep_data = csv_data[nct_id].get(other_rep, {})
            other_flat[nct_id] = {field: rep_data.get(field, "") for field in FIELDS}

    if replicate == "r1":
        data_r1, data_r2 = ann_data, other_flat
    else:
        data_r1, data_r2 = other_flat, ann_data

    return _build_job_concordance(
        data_a=data_r1,
        data_b=data_r2,
        label_a="R1",
        label_b="R2",
        job_id="human",
        comparison_label=f"R1 vs R2 ({annotator} NCTs)",
    )


# ---------------------------------------------------------------------------
# Multi-annotator concordance (replicate-aware)
# ---------------------------------------------------------------------------
def _human_data_for_annotators(
    annotator_names: list[str],
    replicate: str,
) -> dict[str, dict[str, str]]:
    """Return flat human data combining NCTs from multiple annotators in ONE replicate.

    Only includes NCTs where the annotator filled in at least one field
    (universal blank handling standard).

    Parameters:
        annotator_names: List of annotator names to include.
        replicate: 'r1' or 'r2' — which replicate sheet to draw from.

    Returns: {nct_id: {field: value}} for all NCTs by the selected annotators.
    """
    csv_data = _load_csv_annotations()
    flat: dict[str, dict[str, str]] = {}
    name_set = set(annotator_names)

    for nct_id, reps in csv_data.items():
        annotator = reps.get(f"{replicate}_annotator", "")
        if annotator not in name_set:
            continue
        rep_data = reps.get(replicate, {})
        entry = {field: rep_data.get(field, "") for field in FIELDS}
        if _has_any_annotation(entry):
            flat[nct_id] = entry

    return flat


def agent_vs_annotators(
    job_id: str,
    annotator_names: list[str],
    replicate: str,
) -> JobConcordance:
    """Compare agent job against multiple annotators from ONE replicate.

    Combines NCTs from all selected annotators in the specified replicate
    into one concordance computation.

    Parameters:
        job_id: Agent job to compare.
        annotator_names: List of annotator names (e.g. ["Mercan", "Maya"]).
        replicate: 'r1' or 'r2'.

    Returns: JobConcordance with combined data.
    """
    names_label = ", ".join(annotator_names)
    rep_label = replicate.upper()
    comparison_label = f"Agent vs {rep_label} ({names_label})"

    agent_data = _load_agent_annotations(job_id)
    if not agent_data:
        return JobConcordance(
            job_id=job_id,
            comparison_label=comparison_label,
        )

    human_data = _human_data_for_annotators(annotator_names, replicate)
    if not human_data:
        return JobConcordance(
            job_id=job_id,
            comparison_label=comparison_label,
        )

    timestamp = _get_job_timestamp(job_id)

    return _build_job_concordance(
        data_a=agent_data,
        data_b=human_data,
        label_a="Agent",
        label_b=rep_label,
        job_id=job_id,
        comparison_label=comparison_label,
        timestamp=timestamp,
    )


def r1_vs_r2_for_annotators(
    r1_names: Optional[list[str]] = None,
    r2_names: Optional[list[str]] = None,
) -> JobConcordance:
    """R1 vs R2 inter-rater agreement filtered by selected annotators.

    When annotators are selected for a replicate, only their NCTs are used
    for that side. When no annotators are selected for a replicate, ALL NCTs
    from that replicate are used (full replicate data).

    Parameters:
        r1_names: Selected R1 annotators, or None/empty for all R1.
        r2_names: Selected R2 annotators, or None/empty for all R2.

    Returns: JobConcordance comparing the filtered R1 vs R2 data.
    """
    # Build R1 side
    if r1_names:
        data_r1 = _human_data_for_annotators(r1_names, "r1")
        r1_label = ", ".join(r1_names)
    else:
        data_r1 = _human_data_as_flat("r1")
        r1_label = "All"

    # Build R2 side
    if r2_names:
        data_r2 = _human_data_for_annotators(r2_names, "r2")
        r2_label = ", ".join(r2_names)
    else:
        data_r2 = _human_data_as_flat("r2")
        r2_label = "All"

    comparison_label = f"R1 ({r1_label}) vs R2 ({r2_label})"

    return _build_job_concordance(
        data_a=data_r1,
        data_b=data_r2,
        label_a="R1",
        label_b="R2",
        job_id="human",
        comparison_label=comparison_label,
    )

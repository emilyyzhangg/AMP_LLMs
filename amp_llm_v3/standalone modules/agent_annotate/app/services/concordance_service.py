"""
Concordance engine for agent-annotate.

Computes agreement metrics between:
  - Agent annotations (from job result JSON files)
  - Human annotations (from Excel, two replicates: R1 and R2)

Supports: agent_vs_r1, agent_vs_r2, r1_vs_r2, compare_jobs, concordance_history.
"""

import json
import logging
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

import openpyxl

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
    ComparisonFieldDelta,
    ComparisonResult,
    ConcordanceHistory,
    ConcordanceHistoryEntry,
    ConcordanceResult,
    Disagreement,
    JobConcordance,
)

logger = logging.getLogger("agent_annotate.concordance")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
EXCEL_PATH = Path(
    "/Users/amphoraxe/Developer/amphoraxe/dev-llm.amphoraxe.ca/docs/"
    "clinical_trials-with-sequences.xlsx"
)
JSON_DIR = RESULTS_DIR / "json"

# ---------------------------------------------------------------------------
# Field definitions (Excel column indices are 0-based)
# Mirrors scripts/concordance_jobs.py column mapping exactly.
# ---------------------------------------------------------------------------
FIELDS = {
    "classification": {
        "excel_r1_col": 10,  # K
        "excel_r2_col": 10,  # K
        "blank_means_skip": True,
    },
    "delivery_mode": {
        "excel_r1_col": 12,  # M
        "excel_r2_col": 12,  # M
        "blank_means_skip": True,
    },
    "outcome": {
        "excel_r1_col": 17,  # R
        "excel_r2_col": 17,  # R
        "blank_means_skip": True,
    },
    "reason_for_failure": {
        "excel_r1_col": 18,  # S
        "excel_r2_col": 18,  # S
        "blank_means_skip": False,  # blank IS a valid value ("no failure")
    },
    "peptide": {
        "excel_r1_col": 21,  # V
        "excel_r2_col": 21,  # V
        "blank_means_skip": True,
    },
}

# ---------------------------------------------------------------------------
# Value normalisation aliases
# ---------------------------------------------------------------------------
DELIVERY_MODE_ALIASES: dict[str, str] = {
    "intravenous": "IV",
    "iv": "IV",
    "injection/infusion - intravenous": "IV",
    "oral - unspecified": "Oral - Unspecified",
    "oral - capsule": "Oral - Capsule",
    "oral - tablet": "Oral - Tablet",
    "oral - drink": "Oral - Drink",
    "oral - food": "Oral - Food",
    "injection": "Injection/Infusion - Other/Unspecified",
    "topical - unspecified": "Topical - Unspecified",
    "other/unspecified": "Other/Unspecified",
    "subcutaneous": "Subcutaneous/Intradermal",
    "sc": "Subcutaneous/Intradermal",
    "subcutaneous/intradermal": "Subcutaneous/Intradermal",
    "intradermal": "Subcutaneous/Intradermal",
}

OUTCOME_ALIASES: dict[str, str] = {
    "active": "Active, not recruiting",
    "active, not recruiting": "Active, not recruiting",
    "active not recruiting": "Active, not recruiting",
    "recruiting": "Recruiting",
    "failed": "Failed - completed trial",
    "failed - completed trial": "Failed - completed trial",
    "completed": "Failed - completed trial",
    "positive": "Positive",
    "terminated": "Terminated",
    "withdrawn": "Withdrawn",
    "unknown": "Unknown",
}

CLASSIFICATION_ALIASES: dict[str, str] = {
    "amp(infection)": "AMP(infection)",
    "amp(other)": "AMP(other)",
    "amp (infection)": "AMP(infection)",
    "amp (other)": "AMP(other)",
    "other": "Other",
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
}

PEPTIDE_ALIASES: dict[str, str] = {
    "true": "True",
    "false": "False",
    "yes": "True",
    "no": "False",
    "1": "True",
    "0": "False",
}

# ---------------------------------------------------------------------------
# Annotator row ranges (1-indexed Excel rows, data starts at row 2)
# Row numbers below are 1-indexed data rows (i.e. Excel row 2 = data row 1).
# ---------------------------------------------------------------------------
R1_ANNOTATOR_RANGES: list[tuple[str, int, int]] = [
    ("Mercan", 1, 309),
    ("Maya", 310, 617),
    ("Anat", 617, 822),
    ("Ali", 823, 926),
    ("Emre", 926, 1186),
    ("Iris", 1187, 1417),
    ("Ali", 1417, 1544),   # Ali has a second range
    ("Berke", 1545, 1846),
]

R2_ANNOTATOR_RANGES: list[tuple[str, int, int]] = [
    ("Anat", 462, 480),
    ("Ali", 923, 941),
    ("Iris", 1384, 1405),
]


def _get_annotator_for_row(row_num: int, replicate: str) -> str:
    """Determine which annotator produced a given data row (1-indexed).

    For R2, rows not in the explicit ranges default to Emily.
    """
    ranges = R1_ANNOTATOR_RANGES if replicate == "r1" else R2_ANNOTATOR_RANGES
    for name, start, end in ranges:
        if start <= row_num <= end:
            return name
    # R2 default is Emily; R1 should always match but fall back just in case
    return "Emily" if replicate == "r2" else "Unknown"


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------
def _normalise(value: object, field_name: str) -> tuple[str, bool]:
    """Normalise a value for comparison.

    Returns (normalised_string, is_blank).
    """
    if value is None:
        return ("", True)

    # Excel stores Peptide as bool
    if isinstance(value, bool):
        return (str(value), False)

    s = str(value).strip()
    if s == "" or s.lower() == "none":
        return ("", True)

    s_lower = s.lower()

    if field_name == "delivery_mode":
        # Multi-value: normalise each part, sort alphabetically
        parts = [p.strip() for p in s.split(",")]
        normalised_parts = []
        for part in parts:
            part_lower = part.strip().lower()
            normalised_parts.append(
                DELIVERY_MODE_ALIASES.get(part_lower, part.strip())
            )
        normalised_parts.sort()
        return (", ".join(normalised_parts), False)
    elif field_name == "outcome":
        return (OUTCOME_ALIASES.get(s_lower, s), False)
    elif field_name == "classification":
        return (CLASSIFICATION_ALIASES.get(s_lower, s), False)
    elif field_name == "reason_for_failure":
        return (REASON_ALIASES.get(s_lower, s), False)
    elif field_name == "peptide":
        return (PEPTIDE_ALIASES.get(s_lower, s), False)
    else:
        return (s, False)


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
# Data loading: Excel (human annotations)
# ---------------------------------------------------------------------------
_excel_cache: Optional[dict[str, dict]] = None


def _load_excel_annotations() -> dict[str, dict]:
    """Load human annotations from both replicate sheets.

    Returns: {nct_id: {
        'r1': {field: raw_value},
        'r2': {field: raw_value},
        'r1_annotator': str,
        'r2_annotator': str,
    }}

    Results are cached in-memory after first load.
    """
    global _excel_cache
    if _excel_cache is not None:
        return _excel_cache

    if not EXCEL_PATH.exists():
        logger.error("Excel file not found: %s", EXCEL_PATH)
        return {}

    logger.info("Loading human annotations from %s", EXCEL_PATH)
    wb = openpyxl.load_workbook(str(EXCEL_PATH), read_only=True, data_only=True)
    data: dict[str, dict] = defaultdict(
        lambda: {"r1": {}, "r2": {}, "r1_annotator": "", "r2_annotator": ""}
    )

    for replicate, sheet_name in [
        ("r1", "Trials Replicate 1"),
        ("r2", "Trials Replicate 2"),
    ]:
        try:
            ws = wb[sheet_name]
        except KeyError:
            logger.error("Sheet '%s' not found in Excel file", sheet_name)
            continue
        row_num = 0  # 1-indexed data row counter
        for row in ws.iter_rows(min_row=2, values_only=True):
            row_num += 1
            nct = row[0]
            if nct is None:
                continue
            nct = str(nct).strip()
            for field_name, field_def in FIELDS.items():
                col_idx = field_def[f"excel_{replicate}_col"]
                raw = row[col_idx] if col_idx < len(row) else None
                data[nct][replicate][field_name] = raw
            # Track which annotator produced this row
            annotator = _get_annotator_for_row(row_num, replicate)
            data[nct][f"{replicate}_annotator"] = annotator

    wb.close()
    _excel_cache = dict(data)
    logger.info("Loaded %d NCT IDs from Excel", len(_excel_cache))
    return _excel_cache


def invalidate_excel_cache() -> None:
    """Force reload of Excel data on next access (e.g. if file is updated)."""
    global _excel_cache
    _excel_cache = None


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

        # Blank handling
        if blank_means_skip and (blank_a or blank_b):
            skipped += 1
            continue

        # For reason_for_failure: outcome-aware blank handling (v3).
        # A blank reason is only meaningful if the annotator actually engaged
        # with the trial (i.e., filled in the outcome field). If both outcome
        # AND reason are blank, the annotator skipped the trial entirely.
        if field_name == "reason_for_failure":
            outcome_a = data_a.get(nct, {}).get("outcome", "")
            outcome_b = data_b.get(nct, {}).get("outcome", "")
            _, outcome_a_blank = _normalise(outcome_a, "outcome")
            _, outcome_b_blank = _normalise(outcome_b, "outcome")

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

            # Blanks that survive are legitimate "no failure" values
            if blank_a:
                norm_a = ""
            if blank_b:
                norm_b = ""
        elif not blank_means_skip:
            if blank_a:
                norm_a = ""
            if blank_b:
                norm_b = ""

        labels_a.append(norm_a)
        labels_b.append(norm_b)

        # Track distributions
        dist_a[norm_a] += 1
        dist_b[norm_b] += 1

        # Confusion matrix
        confusion[norm_a][norm_b] += 1

        if norm_a != norm_b:
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
        interpretation=_kappa_interpretation(kappa),
        confusion_matrix=confusion_dict,
        value_distribution=distribution,
        disagreements=disagreements,
    )


def _build_job_concordance(
    data_a: dict[str, dict[str, str]],
    data_b: dict[str, dict[str, str]],
    label_a: str,
    label_b: str,
    job_id: str,
    comparison_label: str,
    timestamp: Optional[str] = None,
) -> JobConcordance:
    """Build full concordance results across all fields."""
    common_ncts = sorted(set(data_a.keys()) & set(data_b.keys()))

    fields: list[ConcordanceResult] = []
    total_agree = 0
    total_n = 0

    for field_name in FIELDS:
        result = _compute_field_concordance(
            data_a, data_b, label_a, label_b, field_name, common_ncts
        )
        fields.append(result)
        total_agree += result.agree_count
        total_n += result.n

    overall_pct = round((total_agree / total_n) * 100, 1) if total_n > 0 else 0.0

    return JobConcordance(
        job_id=job_id,
        comparison_label=comparison_label,
        timestamp=timestamp,
        n_overlapping=len(common_ncts),
        fields=fields,
        overall_agree_pct=overall_pct,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def _human_data_as_flat(replicate: str) -> dict[str, dict[str, str]]:
    """Convert human Excel data for a replicate into flat {nct: {field: value}} format.

    This matches the agent annotation format so we can reuse _build_job_concordance.
    """
    excel_data = _load_excel_annotations()
    flat: dict[str, dict[str, str]] = {}
    for nct_id, reps in excel_data.items():
        rep_data = reps.get(replicate, {})
        flat[nct_id] = {field: rep_data.get(field, "") for field in FIELDS}
    return flat


def agent_vs_r1(job_id: str) -> JobConcordance:
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
    )


def agent_vs_r2(job_id: str) -> JobConcordance:
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
    )


def r1_vs_r2() -> JobConcordance:
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
        for field_name in FIELDS:
            result = _compute_field_concordance(
                agent_data, r1_data, "Agent", "R1", field_name, common_ncts
            )
            field_kappas[field_name] = result.kappa

        # Count trials in this job
        n_trials = len(agent_data)

        entries.append(
            ConcordanceHistoryEntry(
                job_id=job_id,
                timestamp=timestamp,
                field_kappas=field_kappas,
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
    An annotator belongs to whichever replicate their name appears in.
    If they appear in both, R1 is preferred (more granular breakdown).
    """
    excel_data = _load_excel_annotations()
    flat: dict[str, dict[str, str]] = {}
    detected_replicate = ""

    # Determine which replicate this annotator belongs to
    r1_names = {name for name, _, _ in R1_ANNOTATOR_RANGES}
    r2_names = {name for name, _, _ in R2_ANNOTATOR_RANGES}
    r2_names.add("Emily")  # Emily is the R2 default

    if annotator in r1_names:
        detected_replicate = "r1"
    elif annotator in r2_names:
        detected_replicate = "r2"
    else:
        return flat, ""

    for nct_id, reps in excel_data.items():
        if reps.get(f"{detected_replicate}_annotator") == annotator:
            rep_data = reps.get(detected_replicate, {})
            flat[nct_id] = {field: rep_data.get(field, "") for field in FIELDS}

    return flat, detected_replicate


def annotator_list() -> list[AnnotatorInfo]:
    """Return a list of all annotators with their NCT counts."""
    excel_data = _load_excel_annotations()

    # Count NCTs per annotator per replicate
    r1_counts: Counter = Counter()
    r2_counts: Counter = Counter()

    for reps in excel_data.values():
        r1_ann = reps.get("r1_annotator", "")
        r2_ann = reps.get("r2_annotator", "")
        if r1_ann:
            r1_counts[r1_ann] += 1
        if r2_ann:
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
    excel_data = _load_excel_annotations()
    other_flat: dict[str, dict[str, str]] = {}
    for nct_id in ann_data:
        if nct_id in excel_data:
            rep_data = excel_data[nct_id].get(other_rep, {})
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

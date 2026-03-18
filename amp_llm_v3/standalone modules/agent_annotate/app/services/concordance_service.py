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
from app.models.concordance import (
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
    """Compute Cohen's kappa for two lists of categorical labels.

    Returns kappa value, or None if computation is not possible (n=0 or pe=1).
    """
    n = len(labels_a)
    if n == 0:
        return None

    all_labels = sorted(set(labels_a) | set(labels_b))

    agreements = sum(1 for a, b in zip(labels_a, labels_b) if a == b)
    po = agreements / n

    count_a = Counter(labels_a)
    count_b = Counter(labels_b)
    pe = sum((count_a[lbl] / n) * (count_b[lbl] / n) for lbl in all_labels)

    if pe == 1.0:
        return 1.0 if po == 1.0 else 0.0

    kappa = (po - pe) / (1.0 - pe)
    return round(kappa, 4)


def _kappa_interpretation(k: Optional[float]) -> str:
    """Landis & Koch (1977) interpretation of kappa."""
    if k is None or (isinstance(k, float) and math.isnan(k)):
        return "N/A"
    if k < 0:
        return "Poor"
    elif k < 0.21:
        return "Slight"
    elif k < 0.41:
        return "Fair"
    elif k < 0.61:
        return "Moderate"
    elif k < 0.81:
        return "Substantial"
    else:
        return "Almost Perfect"


# ---------------------------------------------------------------------------
# Data loading: Excel (human annotations)
# ---------------------------------------------------------------------------
_excel_cache: Optional[dict[str, dict]] = None


def _load_excel_annotations() -> dict[str, dict]:
    """Load human annotations from both replicate sheets.

    Returns: {nct_id: {'r1': {field: raw_value}, 'r2': {field: raw_value}}}

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
    data: dict[str, dict] = defaultdict(lambda: {"r1": {}, "r2": {}})

    for replicate, sheet_name in [
        ("r1", "Trials Replicate 1"),
        ("r2", "Trials Replicate 2"),
    ]:
        try:
            ws = wb[sheet_name]
        except KeyError:
            logger.error("Sheet '%s' not found in Excel file", sheet_name)
            continue
        for row in ws.iter_rows(min_row=2, values_only=True):
            nct = row[0]
            if nct is None:
                continue
            nct = str(nct).strip()
            for field_name, field_def in FIELDS.items():
                col_idx = field_def[f"excel_{replicate}_col"]
                raw = row[col_idx] if col_idx < len(row) else None
                data[nct][replicate][field_name] = raw

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
            # One side has blank outcome + blank reason → that side skipped
            if blank_a and outcome_a_blank:
                skipped += 1
                continue
            if blank_b and outcome_b_blank:
                skipped += 1
                continue

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
    else:
        agree_count = 0
        agree_pct = 0.0
        kappa = None

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

        entries.append(
            ConcordanceHistoryEntry(
                job_id=job_id,
                timestamp=timestamp,
                field_kappas=field_kappas,
            )
        )

    # Sort by timestamp (None timestamps go first)
    entries.sort(key=lambda e: e.timestamp or "")

    return ConcordanceHistory(history=entries)

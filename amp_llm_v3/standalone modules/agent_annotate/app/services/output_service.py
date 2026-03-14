"""
CSV and JSON output generation for annotation results.
"""

import csv
import io
import json
from pathlib import Path
from datetime import datetime

from app.config import RESULTS_DIR
from app.services.version_service import get_version_stamp

ANNOTATION_FIELDS = ["classification", "delivery_mode", "outcome", "reason_for_failure", "peptide"]

# Standard CSV columns (matches existing AMP LLM annotation format)
STANDARD_COLUMNS = [
    "NCT ID",
    "Study Title",
    "Study Status",
    "Phase",
    "Conditions",
    "Interventions",
    "Classification",
    "Delivery Mode",
    "Outcome",
    "Reason for Failure",
    "Peptide",
]

# Full CSV adds evidence, verification, and review metadata per field
FULL_EXTRA_PER_FIELD = [
    "{field}_confidence",
    "{field}_consensus",
    "{field}_final_value",
    "{field}_verifier_opinions",
    "{field}_reconciler_used",
    "{field}_manual_review",
]

FULL_EXTRA_GLOBAL = [
    "flagged_for_review",
    "flag_reason",
    "version",
    "git_commit",
    "config_hash",
    "annotated_at",
]


def _build_full_columns() -> list[str]:
    cols = list(STANDARD_COLUMNS)
    for field in ANNOTATION_FIELDS:
        for template in FULL_EXTRA_PER_FIELD:
            cols.append(template.format(field=field))
    cols.extend(FULL_EXTRA_GLOBAL)
    return cols


FULL_COLUMNS = _build_full_columns()


def _extract_row(trial: dict, full: bool = False, version_info: dict = None) -> dict:
    """Extract a flat CSV row from a trial result dict."""
    meta = trial.get("metadata", {})
    annotations = trial.get("annotations", [])
    verification = trial.get("verification", {})

    # Index annotations by field_name
    ann_by_field = {}
    for a in annotations:
        ann_by_field[a.get("field_name", "")] = a

    # Index verification results by field_name
    ver_by_field = {}
    for f in verification.get("fields", []):
        ver_by_field[f.get("field_name", "")] = f

    row = {
        "NCT ID": trial.get("nct_id", meta.get("nct_id", "")),
        "Study Title": meta.get("title", ""),
        "Study Status": meta.get("status", ""),
        "Phase": meta.get("phase", ""),
        "Conditions": ", ".join(meta.get("conditions", [])) if isinstance(meta.get("conditions"), list) else meta.get("conditions", ""),
        "Interventions": ", ".join(meta.get("interventions", [])) if isinstance(meta.get("interventions"), list) else meta.get("interventions", ""),
    }

    for field in ANNOTATION_FIELDS:
        ann = ann_by_field.get(field, {})
        ver = ver_by_field.get(field, {})

        # Use verification final_value if available, else annotation value
        final = ver.get("final_value") or ann.get("value", "")
        row[field.replace("_", " ").title().replace(" ", " ")] = final

        # Map to standard column names
        col_map = {
            "classification": "Classification",
            "delivery_mode": "Delivery Mode",
            "outcome": "Outcome",
            "reason_for_failure": "Reason for Failure",
            "peptide": "Peptide",
        }
        row[col_map.get(field, field)] = final

        if full:
            row[f"{field}_confidence"] = ann.get("confidence", "")
            row[f"{field}_consensus"] = ver.get("consensus_reached", "")
            row[f"{field}_final_value"] = ver.get("final_value", "")
            opinions = ver.get("opinions", [])
            row[f"{field}_verifier_opinions"] = "; ".join(
                f"{o.get('model_name', '')}: {o.get('suggested_value', '')}"
                for o in opinions
            )
            row[f"{field}_reconciler_used"] = ver.get("reconciler_used", False)
            row[f"{field}_manual_review"] = not ver.get("consensus_reached", True)

    if full:
        row["flagged_for_review"] = verification.get("flagged_for_review", False)
        row["flag_reason"] = verification.get("flag_reason", "")
        if version_info:
            row["version"] = version_info.get("version", "")
            row["git_commit"] = version_info.get("git_commit", "")
            row["config_hash"] = version_info.get("config_hash", "")
        row["annotated_at"] = datetime.utcnow().isoformat()

    return row


def generate_standard_csv(trials: list[dict]) -> str:
    output = io.StringIO()
    version = get_version_stamp()
    output.write(f"# Agent Annotate v{version['version']} | commit: {version['git_commit']} | {version['timestamp']}\n")
    writer = csv.DictWriter(output, fieldnames=STANDARD_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for trial in trials:
        writer.writerow(_extract_row(trial, full=False))
    return output.getvalue()


def generate_full_csv(trials: list[dict]) -> str:
    output = io.StringIO()
    version = get_version_stamp()
    output.write(f"# Agent Annotate v{version['version']} (Full) | commit: {version['git_commit']} | {version['timestamp']}\n")
    writer = csv.DictWriter(output, fieldnames=FULL_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for trial in trials:
        writer.writerow(_extract_row(trial, full=True, version_info=version))
    return output.getvalue()


def save_csv(job_id: str, csv_content: str, label: str = "standard") -> Path:
    csv_dir = RESULTS_DIR / "csv"
    csv_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{job_id}_{label}_{timestamp}.csv"
    path = csv_dir / filename
    path.write_text(csv_content)
    return path


def save_json_output(job_id: str, data: dict) -> Path:
    json_dir = RESULTS_DIR / "json"
    json_dir.mkdir(parents=True, exist_ok=True)
    path = json_dir / f"{job_id}.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    return path


def load_json_output(job_id: str) -> dict:
    path = RESULTS_DIR / "json" / f"{job_id}.json"
    if not path.exists():
        return {}
    with open(path, "r") as f:
        return json.load(f)

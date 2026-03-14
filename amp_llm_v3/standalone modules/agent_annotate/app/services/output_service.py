"""
CSV and JSON output generation for annotation results.
"""

import csv
import io
import json
from pathlib import Path
from datetime import datetime

from app.config import RESULTS_DIR

# Standard CSV columns (matches existing AMP LLM output format)
STANDARD_COLUMNS = [
    "nct_id",
    "title",
    "phase",
    "status",
    "classification",
    "delivery_mode",
    "outcome",
    "reason_for_failure",
    "peptide",
]

# Full CSV adds evidence and verification metadata
FULL_COLUMNS = STANDARD_COLUMNS + [
    "classification_confidence",
    "classification_consensus",
    "classification_sources",
    "delivery_mode_confidence",
    "delivery_mode_consensus",
    "delivery_mode_sources",
    "outcome_confidence",
    "outcome_consensus",
    "outcome_sources",
    "reason_for_failure_confidence",
    "reason_for_failure_consensus",
    "reason_for_failure_sources",
    "peptide_confidence",
    "peptide_consensus",
    "peptide_sources",
    "flagged_for_review",
    "version",
    "config_hash",
    "annotated_at",
]


def _extract_row(trial: dict, full: bool = False) -> dict:
    """Extract a flat row dict from a VerifiedAnnotation-style dict."""
    meta = trial.get("metadata", trial)
    row = {
        "nct_id": meta.get("nct_id", trial.get("nct_id", "")),
        "title": meta.get("title", ""),
        "phase": meta.get("phase", ""),
        "status": meta.get("status", ""),
    }

    fields = {}
    for f in trial.get("fields", []):
        fields[f["field_name"]] = f

    for field_name in ["classification", "delivery_mode", "outcome", "reason_for_failure", "peptide"]:
        fdata = fields.get(field_name, {})
        row[field_name] = fdata.get("final_value", "")
        if full:
            row[f"{field_name}_confidence"] = fdata.get("agreement_ratio", "")
            row[f"{field_name}_consensus"] = fdata.get("consensus_reached", "")
            row[f"{field_name}_sources"] = "; ".join(
                o.get("model_name", "") for o in fdata.get("opinions", [])
            )

    if full:
        row["flagged_for_review"] = trial.get("flagged_for_review", False)
        row["version"] = ""
        row["config_hash"] = ""
        row["annotated_at"] = ""

    return row


def generate_standard_csv(trials: list[dict]) -> str:
    """Generate standard CSV string from trial results."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=STANDARD_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for trial in trials:
        writer.writerow(_extract_row(trial, full=False))
    return output.getvalue()


def generate_full_csv(trials: list[dict]) -> str:
    """Generate full CSV string with evidence metadata."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=FULL_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for trial in trials:
        writer.writerow(_extract_row(trial, full=True))
    return output.getvalue()


def save_csv(job_id: str, csv_content: str, label: str = "standard") -> Path:
    """Save CSV to the results directory and return the path."""
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{job_id}_{label}_{timestamp}.csv"
    path = RESULTS_DIR / filename
    path.write_text(csv_content)
    return path


def save_json_output(job_id: str, data: dict) -> Path:
    """Save full JSON output to the results directory."""
    json_dir = RESULTS_DIR / "json"
    json_dir.mkdir(parents=True, exist_ok=True)
    path = json_dir / f"{job_id}.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    return path

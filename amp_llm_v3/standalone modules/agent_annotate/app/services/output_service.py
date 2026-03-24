"""
CSV and JSON output generation for annotation results.

Includes full citation/source traceability for each annotation field:
- Which LLM model made the annotation
- Which agent was responsible
- Source identifiers and evidence text
- Verifier consensus summary
"""

import csv
import io
import json
from pathlib import Path
from datetime import datetime

from app.config import RESULTS_DIR
from app.services.version_service import get_version_stamp
from app.models.job import now_pacific
from app.services.review_service import review_service

ANNOTATION_FIELDS = ["classification", "delivery_mode", "outcome", "reason_for_failure", "peptide"]

# Map annotation field names to their responsible agent
FIELD_TO_AGENT = {
    "classification": "classification",
    "delivery_mode": "delivery_mode",
    "outcome": "outcome",
    "reason_for_failure": "reason_for_failure",
    "peptide": "peptide",
}

# Standard CSV columns (matches human annotation Excel + evidence links + traceability)
STANDARD_COLUMNS = [
    "NCT ID",
    "Study Title",
    "Study Status",
    "Phase",
    "Conditions",
    "Interventions",
    "Classification",
    "Classification Evidence",
    "Classification Sources",
    "Classification Evidence Text",
    "Delivery Mode",
    "Delivery Mode Evidence",
    "Delivery Mode Sources",
    "Delivery Mode Evidence Text",
    "Outcome",
    "Outcome Evidence",
    "Outcome Sources",
    "Outcome Evidence Text",
    "Reason for Failure",
    "Reason for Failure Evidence",
    "Reason for Failure Sources",
    "Reason for Failure Evidence Text",
    "Peptide",
    "Peptide Evidence",
    "Peptide Sources",
    "Peptide Evidence Text",
]

# Full CSV adds evidence, verification, traceability, and review metadata per field
FULL_EXTRA_PER_FIELD = [
    "{field}_annotator_model",
    "{field}_agent",
    "{field}_sources",
    "{field}_evidence_text",
    "{field}_verifier_summary",
    "{field}_confidence",
    "{field}_evidence_sources",
    "{field}_evidence_urls",
    "{field}_reasoning",
    "{field}_consensus",
    "{field}_final_value",
    "{field}_verifier_opinions",
    "{field}_reconciler_used",
    "{field}_manual_review",
    "{field}_review_status",
    "{field}_reviewer_value",
    "{field}_reviewer_note",
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


def _build_source_identifiers(evidence: list[dict]) -> list[str]:
    """Extract deduplicated source identifiers from evidence citations.

    Produces compact identifiers like PMID:12345, PMC:67890,
    clinicaltrials_gov:NCT123, or raw URLs as fallback.
    """
    parts = []
    seen = set()
    for e in evidence:
        src = e.get("source_name", "")
        ident = e.get("identifier", "")
        url = e.get("source_url", "")
        # Prefer structured identifiers
        if ident and ident.startswith("PMID:"):
            label = ident
        elif ident and ident.startswith("PMC:"):
            label = ident
        elif ident:
            label = f"{src}:{ident}" if src else ident
        elif url:
            label = url
        else:
            continue
        if label not in seen:
            seen.add(label)
            parts.append(label)
    return parts


def _build_evidence_text(evidence: list[dict], max_chars: int = 500) -> str:
    """Build a combined evidence text snippet from citations, truncated to max_chars.

    Selects the highest-quality snippets first and concatenates them.
    """
    if not evidence:
        return ""
    # Sort by quality_score descending so best evidence comes first
    sorted_ev = sorted(evidence, key=lambda e: e.get("quality_score", 0), reverse=True)
    parts = []
    total_len = 0
    for e in sorted_ev:
        snippet = (e.get("snippet") or "").strip()
        if not snippet:
            continue
        # Skip duplicate snippets
        if any(snippet == p for p in parts):
            continue
        if total_len + len(snippet) + 3 > max_chars:
            # Add as much as fits
            remaining = max_chars - total_len - 3
            if remaining > 50:
                parts.append(snippet[:remaining] + "...")
            break
        parts.append(snippet)
        total_len += len(snippet) + 3  # account for " | " separator
    return " | ".join(parts)


def _build_verifier_summary(ver: dict) -> str:
    """Build a compact verifier summary like '3/3 agree' or '1/3 agree, reconciled by qwen2.5:14b'.

    Reads opinions and reconciler info from the verification dict.
    """
    if not ver:
        return ""
    opinions = ver.get("opinions", [])
    if not opinions:
        return ""

    total = len(opinions)
    agree_count = sum(1 for o in opinions if o.get("agrees", False))

    summary = f"{agree_count}/{total} agree"

    if ver.get("reconciler_used", False):
        # Try to extract the reconciler model name from reconciler_reasoning or config
        # The reconciler model name isn't directly on the verification dict,
        # so we note that reconciliation was used
        summary += ", reconciled"

    if not ver.get("consensus_reached", True):
        summary += ", NO CONSENSUS"

    return summary


def _get_review_decisions(job_id: str) -> dict[str, "ReviewItem"]:
    """Fetch all review decisions for a job, keyed by '{nct_id}:{field_name}'.

    Re-reads from review_service each time (not cached) so exports always
    reflect the latest review state.
    """
    decisions = {}
    for item in review_service.get_all(job_id=job_id):
        if item.status in ("approved", "overridden", "skipped"):
            key = f"{item.nct_id}:{item.field_name}"
            decisions[key] = item
    return decisions


def _extract_row(trial: dict, full: bool = False, version_info: dict = None,
                 config_snapshot: dict = None, review_decisions: dict = None) -> dict:
    """Extract a flat CSV row from a trial result dict.

    Args:
        trial: Single trial result dict from the pipeline.
        full: If True, include all traceability and verification columns.
        version_info: Version stamp dict for full output.
        config_snapshot: Job config snapshot for resolving model names.
        review_decisions: Dict of review decisions keyed by '{nct_id}:{field_name}'.
    """
    meta = trial.get("metadata", {})
    annotations = trial.get("annotations", [])
    verification = trial.get("verification", {}) or {}

    # Index annotations by field_name
    ann_by_field = {}
    for a in annotations:
        ann_by_field[a.get("field_name", "")] = a

    # Index verification results by field_name
    ver_by_field = {}
    for f in verification.get("fields", []):
        ver_by_field[f.get("field_name", "")] = f

    # Resolve reconciler model name from config_snapshot if available
    reconciler_model = ""
    if config_snapshot:
        models = config_snapshot.get("verification", {}).get("models", {})
        recon = models.get("reconciliation", {})
        reconciler_model = recon.get("name", "")

    row = {
        "NCT ID": trial.get("nct_id", meta.get("nct_id", "")),
        "Study Title": meta.get("title", ""),
        "Study Status": meta.get("status", ""),
        "Phase": meta.get("phase", ""),
        "Conditions": ", ".join(meta.get("conditions", [])) if isinstance(meta.get("conditions"), list) else meta.get("conditions", ""),
        "Interventions": ", ".join(meta.get("interventions", [])) if isinstance(meta.get("interventions"), list) else meta.get("interventions", ""),
    }

    nct_id = trial.get("nct_id", meta.get("nct_id", ""))

    for field in ANNOTATION_FIELDS:
        ann = ann_by_field.get(field, {})
        ver = ver_by_field.get(field, {})

        # Use verification final_value if available, else annotation value
        final = ver.get("final_value") or ann.get("value", "")

        # Apply review decisions: overridden -> use reviewer_value; approved -> keep original
        review_status = ""
        reviewer_value = ""
        reviewer_note = ""
        if review_decisions:
            review_key = f"{nct_id}:{field}"
            decision = review_decisions.get(review_key)
            if decision:
                review_status = decision.status
                reviewer_value = decision.reviewer_value or ""
                reviewer_note = decision.reviewer_note or ""
                if decision.status == "overridden" and decision.reviewer_value:
                    final = decision.reviewer_value
                # approved: keep original value, just mark status

        # Map to standard column names
        col_map = {
            "classification": "Classification",
            "delivery_mode": "Delivery Mode",
            "outcome": "Outcome",
            "reason_for_failure": "Reason for Failure",
            "peptide": "Peptide",
        }
        col_name = col_map.get(field, field)
        row[col_name] = final

        # Standard evidence column: deduplicated identifiers (PMIDs, URLs)
        evidence = ann.get("evidence", [])
        evidence_parts = []
        for e in evidence:
            src = e.get("source_name", "")
            ident = e.get("identifier", "")
            url = e.get("source_url", "")
            if ident and ident.startswith("PMID:"):
                evidence_parts.append(ident)
            elif ident and ident.startswith("PMC:"):
                evidence_parts.append(ident)
            elif url:
                evidence_parts.append(url)
            elif ident:
                evidence_parts.append(f"{src}:{ident}")
        # Deduplicate while preserving order
        seen = set()
        unique_evidence = []
        for ep in evidence_parts:
            if ep not in seen:
                seen.add(ep)
                unique_evidence.append(ep)
        row[f"{col_name} Evidence"] = "; ".join(unique_evidence)

        # --- Standard CSV traceability columns ---
        source_ids = _build_source_identifiers(evidence)
        row[f"{col_name} Sources"] = "; ".join(source_ids)
        row[f"{col_name} Evidence Text"] = _build_evidence_text(evidence, max_chars=200)

        if full:
            # --- Full CSV traceability columns ---
            row[f"{field}_annotator_model"] = ann.get("model_name", "")
            row[f"{field}_agent"] = FIELD_TO_AGENT.get(field, field)
            row[f"{field}_sources"] = "; ".join(source_ids)
            row[f"{field}_evidence_text"] = _build_evidence_text(evidence, max_chars=500)

            # Verifier summary with reconciler model name
            ver_summary = _build_verifier_summary(ver)
            if ver.get("reconciler_used", False) and reconciler_model:
                # Replace generic "reconciled" with the actual model name
                ver_summary = ver_summary.replace(", reconciled", f", reconciled by {reconciler_model}")
            row[f"{field}_verifier_summary"] = ver_summary

            row[f"{field}_confidence"] = ann.get("confidence", "")

            # Evidence citations -- concrete identifiers and URLs
            seen_sources = []
            seen_urls = []
            for e in evidence:
                src = e.get("source_name", "")
                ident = e.get("identifier", "")
                url = e.get("source_url", "")
                label = f"{src}:{ident}" if ident else src
                if label and label not in seen_sources:
                    seen_sources.append(label)
                if url and url not in seen_urls:
                    seen_urls.append(url)
            row[f"{field}_evidence_sources"] = "; ".join(seen_sources)
            row[f"{field}_evidence_urls"] = "; ".join(seen_urls)
            row[f"{field}_reasoning"] = ann.get("reasoning", "")[:1000]

            row[f"{field}_consensus"] = ver.get("consensus_reached", "")
            row[f"{field}_final_value"] = ver.get("final_value", "")
            opinions = ver.get("opinions", [])
            row[f"{field}_verifier_opinions"] = "; ".join(
                f"{o.get('model_name', '')}: {o.get('suggested_value', '')}"
                for o in opinions
            )
            row[f"{field}_reconciler_used"] = ver.get("reconciler_used", False)
            row[f"{field}_manual_review"] = not ver.get("consensus_reached", True)
            row[f"{field}_review_status"] = review_status
            row[f"{field}_reviewer_value"] = reviewer_value
            row[f"{field}_reviewer_note"] = reviewer_note

    if full:
        row["flagged_for_review"] = verification.get("flagged_for_review", False)
        row["flag_reason"] = verification.get("flag_reason", "")
        if version_info:
            row["version"] = version_info.get("version", "")
            row["git_commit"] = version_info.get("git_commit", "")
            row["config_hash"] = version_info.get("config_hash", "")
        row["annotated_at"] = now_pacific().strftime("%Y-%m-%d %H:%M:%S PT")

    return row


def generate_standard_csv(trials: list[dict], job_id: str = None) -> str:
    output = io.StringIO()
    version = get_version_stamp()
    output.write(f"# Agent Annotate v{version['version']} | commit: {version['git_commit']} | {version['timestamp']}\n")
    writer = csv.DictWriter(output, fieldnames=STANDARD_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    # Dynamically read review state each time (not cached from completion)
    review_decisions = _get_review_decisions(job_id) if job_id else {}
    for trial in trials:
        writer.writerow(_extract_row(trial, full=False, review_decisions=review_decisions))
    return output.getvalue()


def generate_full_csv(trials: list[dict], config_snapshot: dict = None,
                      job_id: str = None) -> str:
    output = io.StringIO()
    version = get_version_stamp()
    output.write(f"# Agent Annotate v{version['version']} (Full) | commit: {version['git_commit']} | {version['timestamp']}\n")
    writer = csv.DictWriter(output, fieldnames=FULL_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    # Dynamically read review state each time (not cached from completion)
    review_decisions = _get_review_decisions(job_id) if job_id else {}
    for trial in trials:
        writer.writerow(_extract_row(trial, full=True, version_info=version,
                                     config_snapshot=config_snapshot,
                                     review_decisions=review_decisions))
    return output.getvalue()


def save_csv(job_id: str, csv_content: str, label: str = "standard") -> Path:
    csv_dir = RESULTS_DIR / "csv"
    csv_dir.mkdir(parents=True, exist_ok=True)
    timestamp = now_pacific().strftime("%Y%m%d_%H%M%S")
    filename = f"{job_id}_{label}_{timestamp}.csv"
    path = csv_dir / filename
    path.write_text(csv_content)
    return path


def _enrich_trial_json(trial: dict, config_snapshot: dict = None,
                       review_decisions: dict = None) -> dict:
    """Add structured traceability metadata to a trial dict for JSON output.

    Enriches each annotation in the trial with a 'traceability' block containing
    the annotator model, agent, sources, evidence text, verifier summary,
    and review status/decisions.
    Does not modify the original dict; returns a new one.
    """
    enriched = dict(trial)
    annotations = enriched.get("annotations", [])
    verification = enriched.get("verification", {}) or {}

    # Index verification by field_name
    ver_by_field = {}
    for f in verification.get("fields", []):
        ver_by_field[f.get("field_name", "")] = f

    # Resolve reconciler model name from config
    reconciler_model = ""
    if config_snapshot:
        models = config_snapshot.get("verification", {}).get("models", {})
        recon = models.get("reconciliation", {})
        reconciler_model = recon.get("name", "")

    enriched_annotations = []
    for ann in annotations:
        ann = dict(ann)  # shallow copy
        field = ann.get("field_name", "")
        evidence = ann.get("evidence", [])
        ver = ver_by_field.get(field, {})

        source_ids = _build_source_identifiers(evidence)

        # Build verifier summary
        ver_summary = _build_verifier_summary(ver)
        if ver.get("reconciler_used", False) and reconciler_model:
            ver_summary = ver_summary.replace(", reconciled", f", reconciled by {reconciler_model}")

        # Build structured opinions list for JSON
        opinions_detail = []
        for o in ver.get("opinions", []):
            opinions_detail.append({
                "model_name": o.get("model_name", ""),
                "agrees": o.get("agrees", False),
                "suggested_value": o.get("suggested_value", ""),
                "confidence": o.get("confidence", 0.0),
            })

        # Look up review decision for this field
        nct_id = trial.get("nct_id", "")
        review_status = None
        reviewer_value = None
        reviewer_note = None
        effective_final_value = ver.get("final_value", "")
        if review_decisions:
            review_key = f"{nct_id}:{field}"
            decision = review_decisions.get(review_key)
            if decision:
                review_status = decision.status
                reviewer_value = decision.reviewer_value
                reviewer_note = decision.reviewer_note
                if decision.status == "overridden" and decision.reviewer_value:
                    effective_final_value = decision.reviewer_value

        ann["traceability"] = {
            "annotator_model": ann.get("model_name", ""),
            "agent": FIELD_TO_AGENT.get(field, field),
            "sources": source_ids,
            "evidence_text": _build_evidence_text(evidence, max_chars=500),
            "verifier_summary": ver_summary,
            "verifier_opinions": opinions_detail,
            "consensus_reached": ver.get("consensus_reached", None),
            "agreement_ratio": ver.get("agreement_ratio", None),
            "reconciler_used": ver.get("reconciler_used", False),
            "reconciler_model": reconciler_model if ver.get("reconciler_used", False) else None,
            "reconciler_reasoning": ver.get("reconciler_reasoning", None),
            "final_value": effective_final_value,
            "review_status": review_status,
            "reviewer_value": reviewer_value,
            "reviewer_note": reviewer_note,
        }
        enriched_annotations.append(ann)

    enriched["annotations"] = enriched_annotations
    return enriched


def save_json_output(job_id: str, data: dict) -> Path:
    """Save JSON output with traceability enrichment on each trial's annotations."""
    json_dir = RESULTS_DIR / "json"
    json_dir.mkdir(parents=True, exist_ok=True)

    config_snapshot = data.get("config_snapshot", {})

    # Dynamically read review state each time (not cached from completion)
    review_decisions = _get_review_decisions(job_id)

    # Deduplicate trials by nct_id (keep first occurrence)
    seen_ncts: set[str] = set()
    unique_trials = []
    for trial in data.get("trials", []):
        nct_id = trial.get("nct_id", "")
        if nct_id not in seen_ncts:
            seen_ncts.add(nct_id)
            unique_trials.append(trial)

    # Enrich trials with traceability metadata
    enriched_data = dict(data)
    enriched_trials = []
    for trial in unique_trials:
        enriched_trials.append(_enrich_trial_json(trial, config_snapshot,
                                                  review_decisions=review_decisions))
    enriched_data["trials"] = enriched_trials

    path = json_dir / f"{job_id}.json"
    with open(path, "w") as f:
        json.dump(enriched_data, f, indent=2, default=str)
    return path


def load_json_output(job_id: str) -> dict:
    """Load JSON output and re-apply current review decisions dynamically.

    Re-reads review state so exports always reflect the latest decisions,
    not what was cached at job completion time.
    """
    path = RESULTS_DIR / "json" / f"{job_id}.json"
    if not path.exists():
        return {}
    with open(path, "r") as f:
        data = json.load(f)

    # Re-apply review decisions to traceability blocks and final values
    review_decisions = _get_review_decisions(job_id)
    if review_decisions:
        for trial in data.get("trials", []):
            nct_id = trial.get("nct_id", "")
            for ann in trial.get("annotations", []):
                field = ann.get("field_name", "")
                review_key = f"{nct_id}:{field}"
                decision = review_decisions.get(review_key)
                traceability = ann.get("traceability", {})
                if decision:
                    traceability["review_status"] = decision.status
                    traceability["reviewer_value"] = decision.reviewer_value
                    traceability["reviewer_note"] = decision.reviewer_note
                    if decision.status == "overridden" and decision.reviewer_value:
                        traceability["final_value"] = decision.reviewer_value
                else:
                    # Ensure review fields exist even if no decision
                    traceability.setdefault("review_status", None)
                    traceability.setdefault("reviewer_value", None)
                    traceability.setdefault("reviewer_note", None)
    return data

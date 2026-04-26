#!/usr/bin/env python3
"""
Commit-accuracy report (v42.7.2 phase 2 calibrated-decline).

Roadmap §11 specifies that downstream scoring should report TWO numbers:

  Coverage         = % of trials where the agent committed (i.e., not inconclusive)
  Commit accuracy  = matches / committed (precision when the agent commits)

This script post-processes a saved job result JSON, joins per-trial
predictions against the training-CSV ground truth, and emits a stratified
accuracy report by `evidence_grade`. Lets downstream filter:

  high-precision use  → keep only db_confirmed + deterministic
  balanced use        → keep db_confirmed + deterministic + pub_trial_specific
  high-recall use     → keep all (default)

Usage:
    python3 scripts/commit_accuracy_report.py <job_id>
    python3 scripts/commit_accuracy_report.py <job_id> --field outcome
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

from app.services.concordance_service import _normalise  # noqa: E402

CSV_PATH = PKG_ROOT / "docs" / "human_ground_truth_train_df.csv"
RESULTS_DIR = PKG_ROOT / "results" / "json"

CSV_FIELDS = {
    "peptide": "Peptide",
    "classification": "Classification",
    "delivery_mode": "Delivery Mode",
    "outcome": "Outcome",
    "reason_for_failure": "Reason for Failure",
    "sequence": "Sequence",
}

# Grade order from highest precision (top) to lowest (bottom).
GRADE_ORDER = [
    "db_confirmed",
    "deterministic",
    "pub_trial_specific",
    "llm",
    "inconclusive",
]


def load_gt() -> dict[str, dict]:
    if not CSV_PATH.exists():
        # Fall back to prod path (script is in dev folder, GT might be in prod folder)
        prod_csv = Path(
            "/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/"
            "amp_llm_v3/standalone modules/agent_annotate/docs/"
            "human_ground_truth_train_df.csv"
        )
        if prod_csv.exists():
            csv_path = prod_csv
        else:
            raise FileNotFoundError(f"GT CSV not found at {CSV_PATH} or prod path")
    else:
        csv_path = CSV_PATH
    gt: dict[str, dict] = {}
    with open(csv_path) as f:
        for row in csv.DictReader(f):
            nct = (row.get("nct_id") or "").upper().strip()
            if nct:
                gt[nct] = row
    return gt


def consensus(row: dict, csv_fld: str, agent_fld: str) -> str | None:
    a, _ = _normalise(row.get(f"{csv_fld}_ann1"), agent_fld); a = a.lower()
    b, _ = _normalise(row.get(f"{csv_fld}_ann2"), agent_fld); b = b.lower()
    if a and b:
        return a if a == b else None
    return a or b or None


def get_pred(trial: dict, agent_fld: str) -> tuple[str, str]:
    """Return (normalised_pred_value, evidence_grade)."""
    # Prefer verification.fields[*].final_value, fall back to annotations[*]
    pipeline_fld = "failure_reason" if agent_fld == "reason_for_failure" else agent_fld
    final_raw = ""
    grade = "llm"
    ver = trial.get("verification") or {}
    for f in ver.get("fields", []):
        if f.get("field_name") in (pipeline_fld, agent_fld):
            final_raw = f.get("final_value", "")
            break
    # The grade lives on the annotation, not verification. Find matching annotation.
    for a in trial.get("annotations", []):
        if a.get("field_name") in (pipeline_fld, agent_fld):
            grade = a.get("evidence_grade", "llm") or "llm"
            if not final_raw:
                final_raw = a.get("value", "")
            break
    norm, blank = _normalise(final_raw, agent_fld)
    return ("" if blank else norm.lower()), grade


def report(job_id: str, only_field: str | None = None) -> int:
    job_path = RESULTS_DIR / f"{job_id}.json"
    if not job_path.exists():
        # Try prod path
        prod_path = Path(
            "/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/"
            "amp_llm_v3/standalone modules/agent_annotate/results/json/"
            f"{job_id}.json"
        )
        if prod_path.exists():
            job_path = prod_path
        else:
            print(f"Job result not found: {job_id}", file=sys.stderr)
            return 1

    job = json.load(job_path.open())
    gt = load_gt()
    trials = job.get("trials", [])
    elapsed = job.get("timing", {}).get("elapsed_seconds", 0) / 60

    print(f"=== Commit-accuracy report — Job {job_id} ===")
    print(f"  trials: {len(trials)}  elapsed: {elapsed:.1f} min")
    print()

    fields = [only_field] if only_field else list(CSV_FIELDS)

    for fld in fields:
        if fld not in CSV_FIELDS:
            print(f"  [unknown field: {fld}]", file=sys.stderr)
            continue
        csv_fld = CSV_FIELDS[fld]

        # Bucket: per (grade, match_or_not), count trials
        # Also: total committed (not inconclusive), total scoreable (GT consensus)
        per_grade: dict[str, dict[str, int]] = defaultdict(lambda: {"matches": 0, "total": 0})
        total_committed = 0
        total_inconclusive = 0
        total_scoreable = 0
        total_skipped_nogt = 0

        for t in trials:
            nct = (t.get("nct_id") or "").upper()
            row = gt.get(nct)
            if not row:
                continue
            truth = consensus(row, csv_fld, fld)
            if not truth:
                total_skipped_nogt += 1
                continue
            total_scoreable += 1
            pred, grade = get_pred(t, fld)
            if grade == "inconclusive" or not pred:
                total_inconclusive += 1
                continue
            total_committed += 1
            match = pred == truth
            per_grade[grade]["total"] += 1
            if match:
                per_grade[grade]["matches"] += 1

        # Aggregates
        coverage = total_committed / total_scoreable * 100 if total_scoreable else 0
        all_matches = sum(g["matches"] for g in per_grade.values())
        all_total = sum(g["total"] for g in per_grade.values())
        commit_acc = all_matches / all_total * 100 if all_total else 0

        print(f"  {fld:24s} coverage={coverage:5.1f}%  commit_acc={commit_acc:5.1f}%   (committed {all_matches}/{all_total}, inconclusive {total_inconclusive}, no-GT {total_skipped_nogt})")
        for grade in GRADE_ORDER:
            if grade not in per_grade:
                continue
            g = per_grade[grade]
            pct = g["matches"] / g["total"] * 100 if g["total"] else 0
            print(f"    grade={grade:22s} {g['matches']:>3}/{g['total']:<3} = {pct:5.1f}%")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("job_id")
    p.add_argument("--field", default=None,
                   help="Only report this field (e.g. outcome)")
    args = p.parse_args()
    return report(args.job_id, args.field)


if __name__ == "__main__":
    sys.exit(main())

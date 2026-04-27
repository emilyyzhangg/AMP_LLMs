#!/usr/bin/env python3
"""
Compare two job result JSONs side-by-side, scored against GT.

Useful for:
  - LLM noise floor (run #89 vs #90 on identical code)
  - Cycle close-out (job before vs after a code change)
  - Held-out validation (baseline vs new commit)

Usage:
    python3 scripts/compare_jobs.py JOBA JOBB
    python3 scripts/compare_jobs.py JOBA JOBB --field outcome
    python3 scripts/compare_jobs.py JOBA JOBB --flips-only

For each field, prints:
  - Per-job correct/scoreable/% (against GT consensus)
  - Δ (B - A)
  - Per-NCT flip table when --field is given
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

from app.services.concordance_service import _normalise  # noqa: E402

CSV_FIELDS = {
    "peptide": "Peptide",
    "classification": "Classification",
    "delivery_mode": "Delivery Mode",
    "outcome": "Outcome",
    "reason_for_failure": "Reason for Failure",
    "sequence": "Sequence",
}

RESULTS_DIRS = [
    PKG_ROOT / "results" / "json",
    Path(
        "/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/"
        "amp_llm_v3/standalone modules/agent_annotate/results/json"
    ),
]
GT_CSV_CANDIDATES = [
    PKG_ROOT / "docs" / "human_ground_truth_train_df.csv",
    Path(
        "/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/"
        "amp_llm_v3/standalone modules/agent_annotate/docs/"
        "human_ground_truth_train_df.csv"
    ),
]


def find_job(job_id: str) -> Path:
    for d in RESULTS_DIRS:
        p = d / f"{job_id}.json"
        if p.exists():
            return p
    raise FileNotFoundError(f"Job {job_id} not in any of {RESULTS_DIRS}")


def find_gt() -> Path:
    for p in GT_CSV_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError(f"GT CSV not in any of {GT_CSV_CANDIDATES}")


def load_gt() -> dict[str, dict]:
    gt = {}
    with open(find_gt()) as f:
        for r in csv.DictReader(f):
            nct = (r.get("nct_id") or "").upper().strip()
            if nct:
                gt[nct] = r
    return gt


def gt_consensus(row: dict, csv_fld: str, agent_fld: str) -> str:
    a, blank_a = _normalise(row.get(f"{csv_fld}_ann1"), agent_fld)
    b, blank_b = _normalise(row.get(f"{csv_fld}_ann2"), agent_fld)
    if blank_a and blank_b:
        return ""
    if not blank_a and not blank_b:
        return a.lower() if a == b else ""
    return (a or b).lower()


def get_pred(trial: dict, agent_fld: str) -> tuple[str, str]:
    """Return (normalised_pred_lower, raw_pred)."""
    pipeline_fld = "failure_reason" if agent_fld == "reason_for_failure" else agent_fld
    raw = ""
    ver = trial.get("verification") or {}
    for f in ver.get("fields", []):
        if f.get("field_name") in (pipeline_fld, agent_fld):
            raw = f.get("final_value", "") or ""
            break
    if not raw:
        for a in trial.get("annotations", []):
            if a.get("field_name") in (pipeline_fld, agent_fld):
                raw = a.get("value", "") or ""
                break
    norm, blank = _normalise(raw, agent_fld)
    return ("" if blank else norm.lower(), raw)


def score(job: dict, gt: dict, only_field: str | None) -> dict:
    fields = [only_field] if only_field else list(CSV_FIELDS)
    out = {}
    per_nct = {}
    for fld in fields:
        csv_fld = CSV_FIELDS[fld]
        correct = 0
        scoreable = 0
        per_nct[fld] = {}
        for t in job.get("trials", []):
            nct = (t.get("nct_id") or "").upper()
            if nct not in gt:
                continue
            gt_v = gt_consensus(gt[nct], csv_fld, fld)
            if not gt_v:
                continue  # no consensus → not scoreable
            pred_norm, pred_raw = get_pred(t, fld)
            scoreable += 1
            ok = (pred_norm == gt_v)
            if ok:
                correct += 1
            per_nct[fld][nct] = (gt_v, pred_norm, pred_raw, ok)
        out[fld] = {"correct": correct, "scoreable": scoreable}
    return {"summary": out, "per_nct": per_nct}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("job_a")
    ap.add_argument("job_b")
    ap.add_argument("--field", help="Restrict to one field (also enables per-NCT flip table).")
    ap.add_argument("--flips-only", action="store_true",
                    help="Only show NCTs where A and B differ.")
    args = ap.parse_args()

    pa, pb = find_job(args.job_a), find_job(args.job_b)
    print(f"A: {pa}")
    print(f"B: {pb}")
    job_a = json.load(open(pa))
    job_b = json.load(open(pb))
    gt = load_gt()
    ra = score(job_a, gt, args.field)
    rb = score(job_b, gt, args.field)

    print(f"\n{'Field':<22}{'A':>20}{'B':>20}{'Δ(B-A)':>12}")
    for fld in (([args.field] if args.field else list(CSV_FIELDS))):
        a, b = ra["summary"][fld], rb["summary"][fld]
        a_pct = 100.0 * a["correct"] / a["scoreable"] if a["scoreable"] else 0.0
        b_pct = 100.0 * b["correct"] / b["scoreable"] if b["scoreable"] else 0.0
        print(
            f"{fld:<22}"
            f"{a['correct']:>3}/{a['scoreable']:<3}={a_pct:5.1f}%{' ':>4}"
            f"{b['correct']:>3}/{b['scoreable']:<3}={b_pct:5.1f}%{' ':>4}"
            f"{b_pct - a_pct:+6.1f}pp"
        )

    if args.field:
        print(f"\n--- Per-NCT (field={args.field}) ---")
        all_ncts = sorted(set(ra["per_nct"][args.field]) | set(rb["per_nct"][args.field]))
        for nct in all_ncts:
            ea = ra["per_nct"][args.field].get(nct)
            eb = rb["per_nct"][args.field].get(nct)
            if ea and eb:
                gt_v, pa_norm, pa_raw, oa = ea
                _,    pb_norm, pb_raw, ob = eb
                if args.flips_only and pa_norm == pb_norm:
                    continue
                marker = ""
                if pa_norm != pb_norm:
                    marker = " ⚡"  # flip
                ta = "✓" if oa else "✗"
                tb = "✓" if ob else "✗"
                print(f"  {nct} GT={gt_v!r:30} A={pa_raw!r:25}{ta} B={pb_raw!r:25}{tb}{marker}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

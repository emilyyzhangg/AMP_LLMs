#!/usr/bin/env python3
"""
Compare N job result JSONs side-by-side, scored against GT.

For 2 jobs use compare_jobs.py — this is for 3+ jobs (e.g. baseline ↔
first cycle ↔ second cycle to see whether each cycle moved the needle).

Usage:
    python3 scripts/compare_n_jobs.py JOB1 JOB2 JOB3 ...
    python3 scripts/compare_n_jobs.py JOB1 JOB2 JOB3 --field outcome

Each job's correct/scoreable/% printed in a column. Δ from previous
job is shown after each non-first column.
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


def find_job(jid: str) -> Path:
    for d in RESULTS_DIRS:
        p = d / f"{jid}.json"
        if p.exists():
            return p
    raise FileNotFoundError(f"Job {jid} not in any of {RESULTS_DIRS}")


def find_gt() -> Path:
    for p in GT_CSV_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError(f"GT CSV not in any of {GT_CSV_CANDIDATES}")


def load_gt() -> dict:
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


def get_pred(trial: dict, agent_fld: str) -> str:
    pipeline_fld = "failure_reason" if agent_fld == "reason_for_failure" else agent_fld
    raw = ""
    ver = trial.get("verification") or {}
    for f in ver.get("fields", []):
        if f.get("field_name") in (pipeline_fld, agent_fld):
            raw = f.get("final_value", "") or ""
            break
    if not raw:
        for a in trial.get("annotations", []) or []:
            if a.get("field_name") in (pipeline_fld, agent_fld):
                raw = a.get("value", "") or ""
                break
    norm, blank = _normalise(raw, agent_fld)
    return "" if blank else norm.lower()


def score_field(job: dict, gt: dict, agent_fld: str) -> tuple[int, int]:
    csv_fld = CSV_FIELDS[agent_fld]
    correct = 0
    scoreable = 0
    for t in job.get("trials", []) or job.get("results", []):
        nct = (t.get("nct_id") or "").upper()
        if nct not in gt:
            continue
        gt_v = gt_consensus(gt[nct], csv_fld, agent_fld)
        if not gt_v:
            continue
        pred = get_pred(t, agent_fld)
        scoreable += 1
        if pred == gt_v:
            correct += 1
    return correct, scoreable


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("jobs", nargs="+", help="Two or more job IDs")
    ap.add_argument("--field", help="Restrict to one field")
    args = ap.parse_args()
    if len(args.jobs) < 2:
        print("need at least 2 jobs", file=sys.stderr)
        return 2
    paths = [find_job(j) for j in args.jobs]
    print("Jobs:")
    for j, p in zip(args.jobs, paths):
        print(f"  {j} → {p.name}")
    print()
    gt = load_gt()
    jobs = [json.load(open(p)) for p in paths]

    fields = [args.field] if args.field else list(CSV_FIELDS)

    # Header
    header_cells = [f"{j[:8]}" for j in args.jobs]
    print(f"{'Field':<22}", end="")
    for h in header_cells:
        print(f"{h:>20}", end="")
        print(f"{'Δ':>10}", end="")
    print()
    print("-" * (22 + 30 * len(header_cells)))

    # Rows
    for fld in fields:
        print(f"{fld:<22}", end="")
        prev_pct = None
        for i, job in enumerate(jobs):
            c, s = score_field(job, gt, fld)
            pct = 100.0 * c / s if s else 0.0
            cell = f"{c}/{s}={pct:.1f}%"
            print(f"{cell:>20}", end="")
            if i == 0:
                print(f"{'—':>10}", end="")
            else:
                delta = pct - (prev_pct or 0)
                print(f"{delta:+8.1f}pp", end="")
            prev_pct = pct
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())

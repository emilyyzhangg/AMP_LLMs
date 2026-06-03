#!/usr/bin/env python3
"""Export a single completed agent-annotate job to standard + full CSV.

Use this for the new single-job full-corpus flow (the v42.11 sealed cohorts
are submitted as one job each, so there's nothing to merge). The companion
`merge_full_corpus_results.py` covers the legacy two-batch flow only.

Outputs are written next to the script as:
  scripts/<label>_<job_id>_<commit8>.csv         (standard, 16 cols)
  scripts/<label>_<job_id>_<commit8>_full.csv    (full audit, 61 cols)

Usage:
    python3 scripts/export_single_job_csv.py JOB_ID [--label NAME]

Examples (sealed cohorts on v42.11):
    python3 scripts/export_single_job_csv.py 5c8d0aa0431a --label dev_corpus
    python3 scripts/export_single_job_csv.py 8d9398b0af66 --label val
    python3 scripts/export_single_job_csv.py b9301e02fef5 --label test
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PROD_JSON_BASE = ROOT / "results" / "json"


def load_job(job_id: str) -> dict:
    p = PROD_JSON_BASE / f"{job_id}.json"
    if not p.exists():
        raise SystemExit(f"job result not found: {p}")
    return json.load(p.open())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("job_id", help="completed job ID (must have results/json/<id>.json on disk)")
    ap.add_argument("--label", default="single_job",
                    help="output filename prefix (e.g. 'dev_corpus', 'val', 'test')")
    args = ap.parse_args()

    job = load_job(args.job_id)
    trials = job.get("trials") or job.get("results") or []
    if not trials:
        raise SystemExit(f"job {args.job_id} has no trials in JSON")
    commit = (job.get("commit_hash") or "unknown")[:8]
    config_snapshot = job.get("config_snapshot") or {}

    sys.path.insert(0, str(ROOT))
    from app.services.output_service import generate_standard_csv, generate_full_csv

    out_std = HERE / f"{args.label}_{args.job_id}_{commit}.csv"
    out_full = HERE / f"{args.label}_{args.job_id}_{commit}_full.csv"

    out_std.write_text(generate_standard_csv(trials, job_id=args.job_id))
    out_full.write_text(generate_full_csv(trials, config_snapshot=config_snapshot, job_id=args.job_id))

    print(f"Wrote: {out_std} ({len(trials)} trials, commit {commit})")
    print(f"Wrote: {out_full}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

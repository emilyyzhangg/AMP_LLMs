#!/usr/bin/env python3
"""Merge two full-corpus batch result JSONs into one canonical output.

After both `--full-corpus-1` and `--full-corpus-2` jobs complete on
prod, this script combines their trial results into a single
"full corpus annotation set" — the publication-grade output that
covers all 630 NCTs in one unified payload.

Outputs:
  scripts/full_corpus_merged_<v42_7_X>.json — unified trials list,
    suitable for downstream analysis or republication.
  scripts/full_corpus_merged_<v42_7_X>.csv — canonical CSV via the
    same generate_standard_csv path the API uses (each trial gets a
    row with all 6 annotation fields + per-field evidence cols).

Usage:
    python3 scripts/merge_full_corpus_results.py JOB_ID_1 JOB_ID_2

Prereq: both job IDs must have completed (status=completed) and their
result JSONs must be on disk in the prod results path.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROD_JSON_BASE = Path(
    "/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/amp_llm_v3/"
    "standalone modules/agent_annotate/results/json"
)
HERE = Path(__file__).resolve().parent


def load_job(job_id: str) -> dict:
    p = PROD_JSON_BASE / f"{job_id}.json"
    if not p.exists():
        raise SystemExit(f"job result not found: {p}")
    return json.load(p.open())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("job_id_1", help="full-corpus batch 1 job ID")
    ap.add_argument("job_id_2", help="full-corpus batch 2 job ID")
    ap.add_argument("--label", default="full_corpus_merged",
                    help="output filename prefix (default: full_corpus_merged)")
    args = ap.parse_args()

    job1 = load_job(args.job_id_1)
    job2 = load_job(args.job_id_2)

    trials_1 = job1.get("trials") or job1.get("results") or []
    trials_2 = job2.get("trials") or job2.get("results") or []

    # Sanity check: jobs should be from the same code commit
    commit_1 = job1.get("commit_hash", "")
    commit_2 = job2.get("commit_hash", "")
    if commit_1 != commit_2:
        print(
            f"WARN: commits differ — batch 1 ran on {commit_1!r}, "
            f"batch 2 ran on {commit_2!r}. Merged output is heterogeneous.",
            file=sys.stderr,
        )

    # De-duplicate by NCT (in case overlap)
    seen: set[str] = set()
    merged_trials = []
    for t in (trials_1 + trials_2):
        nct = (t.get("nct_id") or "").upper()
        if nct in seen:
            print(f"  WARN: duplicate {nct} — keeping first occurrence", file=sys.stderr)
            continue
        seen.add(nct)
        merged_trials.append(t)

    print(
        f"Merged {len(trials_1)} + {len(trials_2)} = {len(merged_trials)} unique trials",
        file=sys.stderr,
    )
    print(f"Commit hashes: {commit_1}, {commit_2}", file=sys.stderr)

    out_json = HERE / f"{args.label}_{commit_1[:8] or 'unknown'}.json"
    out_json.write_text(json.dumps({
        "merged_from": [args.job_id_1, args.job_id_2],
        "commit_hashes": [commit_1, commit_2],
        "total_trials": len(merged_trials),
        "trials": merged_trials,
    }, indent=2))
    print(f"\nWrote: {out_json}", file=sys.stderr)

    # Try to also produce a CSV via output_service
    try:
        sys.path.insert(0, str(HERE.parent))
        from app.services.output_service import generate_standard_csv
        csv_content = generate_standard_csv(
            merged_trials,
            job_id=f"{args.job_id_1}+{args.job_id_2}",
        )
        out_csv = HERE / f"{args.label}_{commit_1[:8] or 'unknown'}.csv"
        out_csv.write_text(csv_content)
        print(f"Wrote: {out_csv}", file=sys.stderr)
    except Exception as e:
        print(f"  WARN: CSV generation skipped — {type(e).__name__}: {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Cross-job miss-pattern report.

For a given field (default outcome), prints per-job miss-pattern tallies
(gt→pred classes) and a list of NCTs that appear in ≥2 jobs' miss lists
— "cross-job confirmed" regressions vs slice-specific noise.

Usage:
    python3 scripts/cross_job_miss_patterns.py JOB1 JOB2 JOB3 [...]
    python3 scripts/cross_job_miss_patterns.py JOB1 JOB2 --field delivery_mode

Each job ID is the 12-char hash. The script reads the result JSONs from
`/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/.../results/json/`
and joins against `docs/human_ground_truth_train_df.csv` for GT.

Why cross-job? A pattern that recurs in ≥2 independent slices is signal;
a one-off is noise. v42.7.19 was scoped because the spurious-oral
delivery pattern showed in Jobs #92, #95, #96, #97 (4 separate slices),
while v42.7.20 outcome-recall is being deferred because the dominant
under-call pattern looks more like systemic conservatism than a
slice-specific bug class.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

JSON_BASE = Path(
    "/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/amp_llm_v3/"
    "standalone modules/agent_annotate/results/json"
)
DEFAULT_GT = Path(__file__).resolve().parents[1] / "docs" / "human_ground_truth_train_df.csv"

GT_COLUMN_BY_FIELD = {
    "outcome": ("Outcome_ann1", "Outcome_ann2"),
    "delivery_mode": ("Delivery Mode_ann1", "Delivery Mode_ann2"),
    "classification": ("Classification_ann1", "Classification_ann2"),
    "peptide": ("Peptide_ann1", "Peptide_ann2"),
    "reason_for_failure": ("Reason for Failure_ann1", "Reason for Failure_ann2"),
}


def norm(s: str) -> str:
    return (s or "").strip().lower()


def consensus(a: str, b: str) -> str | None:
    a, b = norm(a), norm(b)
    if a and b:
        return a if a == b else None
    return a or b or None


def load_gt(path: Path, field: str) -> dict[str, str]:
    cols = GT_COLUMN_BY_FIELD.get(field)
    if not cols:
        raise SystemExit(
            f"unknown field {field!r} — supported: "
            f"{sorted(GT_COLUMN_BY_FIELD.keys())}"
        )
    out: dict[str, str] = {}
    with path.open() as f:
        for row in csv.DictReader(f):
            nct = (row.get("nct_id") or "").upper().strip()
            if not nct:
                continue
            v = consensus(row.get(cols[0], ""), row.get(cols[1], ""))
            if v:
                out[nct] = v
    return out


def get_field(trial: dict, name: str) -> dict | None:
    for a in trial.get("annotations", []) or []:
        if isinstance(a, dict) and a.get("field_name") == name:
            return a
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("jobs", nargs="+", help="job_id (12-char hash) of each job to compare")
    ap.add_argument("--field", default="outcome", help="annotation field to analyze (default: outcome)")
    ap.add_argument(
        "--gt",
        default=str(DEFAULT_GT),
        help=f"path to GT CSV (default: {DEFAULT_GT.name})",
    )
    args = ap.parse_args()

    gt = load_gt(Path(args.gt), args.field)

    print(f"Cross-job miss-pattern report   (field={args.field}, jobs={len(args.jobs)})")
    print("=" * 80)

    # Per-job pattern tallies and per-NCT miss tracking
    job_pattern: dict[str, dict[str, int]] = {}
    job_total: dict[str, tuple[int, int]] = {}
    ncts_per_job: dict[str, set[str]] = {}

    for jid in args.jobs:
        p = JSON_BASE / f"{jid}.json"
        if not p.exists():
            print(f"  WARN: {jid} not found at {p}", file=sys.stderr)
            continue
        d = json.load(p.open())
        patterns: dict[str, int] = defaultdict(int)
        miss_ncts: set[str] = set()
        scoreable = 0
        misses = 0
        for t in d.get("trials", []) or []:
            nct = (t.get("nct_id") or "").upper()
            ann = get_field(t, args.field) or {}
            pred = norm(ann.get("value", ""))
            gt_v = gt.get(nct)
            if not gt_v or not pred:
                continue
            scoreable += 1
            if pred != gt_v:
                misses += 1
                key = f"{gt_v} → {pred}"
                patterns[key] += 1
                miss_ncts.add(nct)
        job_pattern[jid] = dict(patterns)
        job_total[jid] = (misses, scoreable)
        ncts_per_job[jid] = miss_ncts

    # Per-job summary
    print("\n--- Per-job miss patterns ---")
    for jid in args.jobs:
        if jid not in job_pattern:
            continue
        miss, scoreable = job_total[jid]
        pct = (scoreable - miss) / scoreable * 100 if scoreable else 0
        print(f"\n{jid}  ({scoreable - miss}/{scoreable} = {pct:.1f}%)")
        for pat, n in sorted(job_pattern[jid].items(), key=lambda kv: -kv[1]):
            print(f"  {n:2d}× {pat}")

    # Cross-job NCTs
    nct_count: dict[str, int] = defaultdict(int)
    nct_jobs: dict[str, list[str]] = defaultdict(list)
    for jid, ncts in ncts_per_job.items():
        for n in ncts:
            nct_count[n] += 1
            nct_jobs[n].append(jid)
    multi = sorted([n for n, c in nct_count.items() if c >= 2])
    print(f"\n--- NCTs that miss in ≥2 jobs ({len(multi)}) ---")
    if not multi:
        print("  (none — every miss is slice-specific)")
    for n in multi:
        gt_v = gt.get(n, "?")
        print(f"  {n}  GT={gt_v!r}  in {nct_count[n]} jobs: {', '.join(nct_jobs[n])}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

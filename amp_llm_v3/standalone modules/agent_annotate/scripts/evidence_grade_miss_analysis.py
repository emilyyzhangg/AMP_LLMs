#!/usr/bin/env python3
"""Evidence-grade-stratified miss-pattern analysis.

For a job + field, group misses by evidence_grade and show the LLM
reasoning. This surfaces WHICH layer of the agent is failing:

  - grade=db_confirmed  → structural override fired but got it wrong
                         (e.g. Job #92 FDA-approved cross-indication)
  - grade=deterministic → rule-based path got it wrong (e.g. v41 Active
                         guard mis-firing)
  - grade=pub_trial_specific → LLM-driven from publication evidence
                         (the dominant grade — usually the bottleneck)
  - grade=llm           → bare-LLM with no structural backing

This is what surfaced v42.7.20 — Job #98's pub_trial_specific misses
all showed the LLM rejecting [TRIAL-SPECIFIC]-tagged pubs as field
reviews, indicating the upstream classifier was over-tagging.

Usage:
    python3 scripts/evidence_grade_miss_analysis.py JOB_ID [--field outcome]

Default field is `outcome` (where the bottleneck is). Specify
`--field delivery_mode` etc. to analyze other fields.

Per training-CSV-only rule: GT comes from
docs/human_ground_truth_train_df.csv only.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
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
        raise SystemExit(f"unknown field {field!r}")
    gt: dict[str, str] = {}
    with path.open() as f:
        for r in csv.DictReader(f):
            nct = (r.get("nct_id") or "").upper().strip()
            if not nct:
                continue
            v = consensus(r.get(cols[0], ""), r.get(cols[1], ""))
            if v:
                gt[nct] = v
    return gt


def get_field(t: dict, name: str) -> dict | None:
    for a in t.get("annotations", []) or []:
        if isinstance(a, dict) and a.get("field_name") == name:
            return a
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("job_id", help="job_id (12-char hash) of the job to analyze")
    ap.add_argument("--field", default="outcome", help="annotation field (default: outcome)")
    ap.add_argument("--gt", default=str(DEFAULT_GT))
    args = ap.parse_args()

    gt = load_gt(Path(args.gt), args.field)
    p = JSON_BASE / f"{args.job_id}.json"
    if not p.exists():
        raise SystemExit(f"job not found: {p}")
    job = json.load(p.open())

    print("=" * 80)
    print(f"Evidence-grade miss analysis  job={args.job_id}  field={args.field}")
    print("=" * 80)

    by_grade: dict[str, list[dict]] = {}
    hits = misses = 0
    for t in job.get("trials", []) or []:
        nct = (t.get("nct_id") or "").upper()
        ann = get_field(t, args.field) or {}
        pred = norm(ann.get("value", ""))
        gt_v = gt.get(nct)
        if not gt_v or not pred:
            continue
        if pred == gt_v:
            hits += 1
            continue
        misses += 1
        grade = ann.get("evidence_grade", "unknown")
        rsn = (ann.get("reasoning") or "")
        # Extract LLM decision section if present
        llm_idx = rsn.find("[LLM decision]")
        if llm_idx > 0:
            llm_text = rsn[llm_idx + 15:llm_idx + 15 + 400]
        else:
            llm_text = rsn[:400]
        by_grade.setdefault(grade, []).append({
            "nct": nct,
            "pred": pred,
            "gt": gt_v,
            "rsn": llm_text,
        })

    total = hits + misses
    print(f"\nTotal scoreable: {total}  hits: {hits}  misses: {misses}  "
          f"(accuracy {hits/total*100:.1f}%)" if total else "no scoreable trials")

    for grade in sorted(by_grade.keys()):
        misses_g = by_grade[grade]
        print(f"\n--- grade={grade}: {len(misses_g)} misses ---")
        for m in misses_g:
            print(f"\n  [{m['nct']}] pred={m['pred']!r} GT={m['gt']!r}")
            text = m["rsn"].replace("\n", " ")[:300]
            print(f"  LLM: {text}")

    # Tally
    print("\n--- Miss tally by grade ---")
    for grade in sorted(by_grade.keys()):
        print(f"  grade={grade:25s}: {len(by_grade[grade])} miss(es)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

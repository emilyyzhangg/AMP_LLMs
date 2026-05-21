#!/usr/bin/env python3
"""
Standalone peptide-anchor evaluation harness.

Scores the DETERMINISTIC peptide anchor (agents/annotation/peptide_signals.py —
the same code the agent uses) against ground truth using CACHED research from a
past job. Instant: no LLM, no full pipeline run. Reports how many trials the
anchor settles confidently (and its precision) vs how many it defers to the LLM.

Usage:
    python3 scripts/eval_peptide.py <research_job_id> [--errors]
"""
import csv
import glob
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.research import ResearchResult                       # noqa: E402
from agents.annotation.peptide_signals import (                     # noqa: E402
    extract_peptide_signals, peptide_anchor,
)

GT_PATH = ROOT / "docs" / "human_ground_truth_train_df.csv"


def consensus(a, b):
    a, b = (a or "").strip(), (b or "").strip()
    if a and b:
        return a if a.lower() == b.lower() else None
    return a or b or None


def main():
    if len(sys.argv) < 2:
        print("usage: eval_peptide.py <research_job_id> [--errors]")
        sys.exit(1)
    job = sys.argv[1]
    show_errors = "--errors" in sys.argv
    gt = {}
    for r in csv.DictReader(GT_PATH.open()):
        nid = (r.get("nct_id") or "").strip().lower()
        if nid:
            gt[nid] = consensus(r.get("Peptide_ann1"), r.get("Peptide_ann2"))

    decided = correct = defer = 0
    defer_gt = Counter()
    errors = []
    for f in glob.glob(str(ROOT / "results" / "research" / job / "*.json")):
        if f.endswith("_meta.json"):
            continue
        d = json.load(open(f))
        nid = (d.get("nct_id") or "").lower()
        g = gt.get(nid)
        if not g or g.lower() not in ("true", "false"):
            continue
        sig = extract_peptide_signals([ResearchResult(**x) for x in (d.get("results") or [])])
        a = peptide_anchor(sig)
        if a is None:
            defer += 1
            defer_gt[g.lower()] += 1
            continue
        decided += 1
        if a.lower() == g.lower():
            correct += 1
        elif show_errors:
            errors.append((nid, f"anchor={a}", f"gt={g}", sig["names"][:1]))
    n = decided + defer
    print(f"job {job}: {n} peptide-GT trials")
    print(f"  anchor decided : {decided}/{n} ({decided/max(n,1)*100:.0f}%)  "
          f"precision {correct}/{decided} = {correct/max(decided,1)*100:.1f}%")
    print(f"  deferred to LLM: {defer}/{n}  (GT split {dict(defer_gt)})")
    for e in errors:
        print("  ANCHOR-ERR", *e)


if __name__ == "__main__":
    main()

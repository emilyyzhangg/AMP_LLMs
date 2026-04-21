#!/usr/bin/env python3
"""
v42 atomic shadow-mode disagreement triage (Phase 6 tooling).

Reads an atomic_preview/<run-id>/ output + R1 ground-truth CSV, then for every
atomic-vs-R1 disagreement assigns a *likely* category per
`docs/ATOMIC_EVIDENCE_DECOMPOSITION.md` §4:

  1. Evidence gap    — atomic arrived at Unknown/R8 because research pipeline
                        didn't retrieve the pubs R1 had; fix research, not
                        the agent.
  2. Question gap    — atomic saw trial-specific pubs but every Q1-Q5 answered
                        UNCLEAR/NA/NO even though R1 says Positive/Failed;
                        likely missing atomic question.
  3. Aggregator gap  — voting pubs' verdicts suggest a different label than
                        the rule picked; fix R1-R8 order or body.
  4. R1 judgment     — defensible disagreement; atomic chose differently but
                        for documentable reasons. Allowed to persist.

The categorization is automatic and best-effort; design doc says every
disagreement MUST be manually reviewed before fixes. This tool pre-sorts the
queue — it does not rewrite prompts or rules.

Outputs a markdown triage file to the preview dir for human review.

Usage:
    cd <agent_annotate_dir>
    python3 scripts/atomic_triage.py \
        --preview-dir results/atomic_preview/preview_2026_04_17_10nct
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
CSV_PATH_DEFAULT = PKG_ROOT / "docs" / "human_ground_truth_train_df.csv"


# Same mapping as atomic_vs_r1.py — atomic canonical → R1 CSV vocabulary.
ATOMIC_TO_R1: dict[str, str] = {
    "Positive": "positive",
    "Withdrawn": "withdrawn",
    "Terminated": "terminated",
    "Failed - completed trial": "failed - completed trial",
    "Recruiting": "",
    "Unknown": "unknown",
    "Active, not recruiting": "active",
}

# Which R1 values count as "definite" (i.e. not Unknown / blank).
# Disagreements that include a definite R1 value are higher-priority.
_R1_DEFINITE = {"positive", "terminated", "withdrawn", "failed - completed trial", "active"}


def _map_atomic(val: str) -> str:
    return ATOMIC_TO_R1.get(val or "", "").strip().lower()


def _agrees(atomic: str, r1: str) -> bool:
    return _map_atomic(atomic) == (r1 or "").strip().lower()


def _load_r1(csv_path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    with csv_path.open() as f:
        for row in csv.DictReader(f):
            nct = (row.get("nct_id") or "").strip().lower()
            if nct:
                out[nct] = (row.get("Outcome_ann1") or "").strip().lower()
    return out


# ---- Reasoning parsing --------------------------------------------------- #

_PUB_RE = re.compile(
    r"^\s*-\s+(POSITIVE|FAILED|INDETERMINATE)\s+\S+\s+\(([^\)]+)\)\s+"
    r"q1=(\S+)\s+q2=(\S+)\s+q3=(\S+)\s+q4=(\S+)\s+q5=(\S+)",
    re.IGNORECASE,
)


def _parse_voting_pubs(reasoning: str) -> list[dict]:
    """Best-effort parse of the 'voting:' block from the atomic reasoning."""
    pubs: list[dict] = []
    if not reasoning:
        return pubs
    for line in reasoning.splitlines():
        m = _PUB_RE.match(line)
        if not m:
            continue
        pubs.append({
            "verdict": m.group(1).upper(),
            "specificity": m.group(2).strip(),
            "q1": m.group(3), "q2": m.group(4),
            "q3": m.group(5), "q4": m.group(6), "q5": m.group(7),
        })
    return pubs


def _count_trial_specific(reasoning: str) -> int:
    """Extract 'N ts' from the 'pubs:' summary line."""
    m = re.search(r"pubs:\s+\d+\s+total\s+\((\d+)\s+ts", reasoning or "")
    return int(m.group(1)) if m else 0


# ---- Categorization ------------------------------------------------------ #

def categorize(row: dict, atomic_record: dict) -> tuple[str, str]:
    """
    Returns (category, rationale). Categories: 1|2|3|4.
    Applies heuristics in order — first match wins.
    """
    atomic_val = row.get("atomic") or ""
    rule = row.get("rule") or ""
    r1_val = row.get("r1") or ""
    reasoning = (atomic_record.get("atomic") or {}).get("reasoning") or ""
    voting = _parse_voting_pubs(reasoning)
    ts_count = _count_trial_specific(reasoning)
    r1_definite = r1_val in _R1_DEFINITE

    # Category 1: R8 Unknown vs definite R1 — strongest evidence-gap signal.
    # The research pipeline produced no trial-specific pubs *and* no voting
    # verdicts; R1 knew something we didn't.
    if atomic_val == "Unknown" and rule == "R8" and r1_definite:
        if ts_count == 0:
            return ("1", f"R8 Unknown with 0 trial-specific pubs; R1={r1_val} — research pipeline likely missed the definitive publication")
        if not voting:
            return ("1", f"R8 Unknown with 0 voting pubs; R1={r1_val} — trial-specific pubs present but all INDETERMINATE, evidence gap likely")

    # Category 2: trial-specific pubs present but LLM couldn't extract a
    # verdict — the Q1-Q5 questions didn't ask the right thing.
    if ts_count > 0 and not voting and r1_definite:
        return ("2", f"{ts_count} trial-specific pub(s) read by LLM but all INDETERMINATE; R1={r1_val} — question gap candidate")

    # Category 3: aggregator mis-fire. Voting pubs suggest one direction but
    # the rule chose another. Look at the majority of voting verdicts.
    if voting:
        pos = sum(1 for v in voting if v["verdict"] == "POSITIVE")
        fail = sum(1 for v in voting if v["verdict"] == "FAILED")
        majority = "POSITIVE" if pos > fail else ("FAILED" if fail > pos else "")
        if majority == "POSITIVE" and atomic_val not in ("Positive",):
            return ("3", f"{pos} POSITIVE / {fail} FAILED voting pubs but rule {rule} chose {atomic_val}; aggregator gap candidate")
        if majority == "FAILED" and atomic_val not in ("Failed - completed trial",):
            return ("3", f"{pos} POSITIVE / {fail} FAILED voting pubs but rule {rule} chose {atomic_val}; aggregator gap candidate")

    # Default: defensible judgment call.
    return ("4", f"Rule {rule} chose {atomic_val}, R1={r1_val}; atomic reasoning is defensible — manual review required")


# ---- Main ---------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--preview-dir", required=True, type=Path,
                   help="results/atomic_preview/<run-id>/")
    p.add_argument("--csv", type=Path, default=CSV_PATH_DEFAULT)
    args = p.parse_args(argv)

    summary_path = args.preview_dir / "_summary.json"
    if not summary_path.is_file():
        print(f"ERROR: {summary_path} not found")
        return 2

    r1 = _load_r1(args.csv)
    summary = json.loads(summary_path.read_text())
    per_nct = summary.get("per_nct", [])

    rows: list[dict] = []
    for row in per_nct:
        nct = (row.get("nct") or "").lower()
        r1_val = r1.get(nct)
        if r1_val is None:
            continue  # not in training set — skip
        atomic = row.get("atomic") or ""
        row2 = dict(row)
        row2["r1"] = r1_val
        row2["agree"] = _agrees(atomic, r1_val)
        rows.append(row2)

    disagreements = [r for r in rows if not r["agree"]]
    if not disagreements:
        print("No disagreements to triage.")
        return 0

    triaged = []
    for row in disagreements:
        rec_path = args.preview_dir / f"{row['nct']}.json"
        if rec_path.is_file():
            try:
                record = json.loads(rec_path.read_text())
            except json.JSONDecodeError:
                record = {}
        else:
            record = {}
        cat, rationale = categorize(row, record)
        triaged.append({**row, "category": cat, "rationale": rationale})

    # ---- Summary + markdown output ---- #
    cat_counts = Counter(r["category"] for r in triaged)
    print("=" * 80)
    print(f"DISAGREEMENT TRIAGE  ({len(triaged)} disagreements)")
    print("=" * 80)
    for cat in ("1", "2", "3", "4"):
        print(f"  Category {cat}: {cat_counts.get(cat, 0)}")
    print()
    print(f"  Cat 1 evidence gap      — fix: research pipeline")
    print(f"  Cat 2 question gap      — fix: add atomic question (budget: ≤5)")
    print(f"  Cat 3 aggregator gap    — fix: R1-R8 rule body")
    print(f"  Cat 4 R1 judgment call  — defensible; document, don't fix")
    print()

    md_path = args.preview_dir / "triage.md"
    lines = [
        f"# Shadow-mode disagreement triage — {summary.get('run_id', '')}",
        "",
        f"- total disagreements: **{len(triaged)}**",
        f"- Category 1 (evidence gap): {cat_counts.get('1', 0)}",
        f"- Category 2 (question gap): {cat_counts.get('2', 0)}",
        f"- Category 3 (aggregator gap): {cat_counts.get('3', 0)}",
        f"- Category 4 (R1 judgment call): {cat_counts.get('4', 0)}",
        "",
        "Category meanings per `docs/ATOMIC_EVIDENCE_DECOMPOSITION.md` §4.",
        "Category assignments are automatic heuristics — **every row requires manual review** before action.",
        "",
        "| NCT | rule | atomic | R1 | cat | rationale |",
        "|---|---|---|---|---|---|",
    ]
    for r in sorted(triaged, key=lambda r: (r["category"], r["nct"])):
        lines.append(
            f"| {r['nct']} | {r['rule']} | {r['atomic']} | {r['r1']} | "
            f"{r['category']} | {r['rationale']} |"
        )
    md_path.write_text("\n".join(lines) + "\n")
    print(f"Saved: {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

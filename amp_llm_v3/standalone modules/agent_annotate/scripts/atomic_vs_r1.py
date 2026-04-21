#!/usr/bin/env python3
"""
Compare v42 atomic outcome predictions to R1 human ground truth.

Reads an atomic_preview/<run-id>/_summary.json produced by scripts/atomic_preview.py
plus docs/human_ground_truth_train_df.csv (R1 = Outcome_ann1). For each NCT in the
preview summary that also has an R1 annotation, maps both sides to a common
vocabulary and reports:

  - overall raw agreement
  - breakdown by aggregator rule (TIER0, R1...R8) — shows which rules are
    reliable vs which drift from R1
  - divergence list with NCT, rule, atomic value, R1 value — the starting
    point for Phase 6 categorization (evidence gap / question gap /
    aggregator gap / R1 judgment call, per design doc §4)

Usage:
    cd <agent_annotate_dir>
    python3 scripts/atomic_vs_r1.py \
        --preview results/atomic_preview/preview_2026_04_17_10nct/_summary.json
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
CSV_PATH_DEFAULT = PKG_ROOT / "docs" / "human_ground_truth_train_df.csv"


# Atomic canonical label → R1 CSV vocabulary (lowercase as found in the CSV).
ATOMIC_TO_R1: dict[str, str] = {
    "Positive": "positive",
    "Withdrawn": "withdrawn",
    "Terminated": "terminated",
    "Failed - completed trial": "failed - completed trial",
    "Recruiting": "",  # R1 uses blank/"active" for enrolling trials
    "Unknown": "unknown",
    "Active, not recruiting": "active",
}


def normalize_r1(raw: str) -> str:
    """CSV values are sometimes whitespace-padded or different case."""
    return (raw or "").strip().lower()


def load_r1(csv_path: Path) -> dict[str, str]:
    """NCT id (lowercase per memory note) → R1 outcome string (lowercase)."""
    out: dict[str, str] = {}
    with csv_path.open() as f:
        for row in csv.DictReader(f):
            nct = (row.get("nct_id") or "").strip().lower()
            if not nct:
                continue
            val = normalize_r1(row.get("Outcome_ann1", ""))
            out[nct] = val
    return out


def load_preview(path: Path) -> dict:
    return json.loads(path.read_text())


def agreement(atomic: str, r1: str) -> bool:
    """Compare atomic canonical value to R1 CSV value via the mapping."""
    mapped = ATOMIC_TO_R1.get(atomic or "", "").strip().lower()
    return mapped == (r1 or "").strip().lower()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--preview", required=True, type=Path,
                   help="atomic_preview/<run-id>/_summary.json")
    p.add_argument("--csv", type=Path, default=CSV_PATH_DEFAULT,
                   help="docs/human_ground_truth_train_df.csv (default)")
    args = p.parse_args(argv)

    if not args.preview.is_file():
        print(f"ERROR: {args.preview} not found")
        return 2
    if not args.csv.is_file():
        print(f"ERROR: {args.csv} not found")
        return 2

    r1_by_nct = load_r1(args.csv)
    summary = load_preview(args.preview)
    per_nct = summary.get("per_nct", [])

    print(f"Preview:  {args.preview}")
    print(f"R1 CSV:   {args.csv}  ({len(r1_by_nct)} NCTs)")
    print(f"Preview NCTs: {len(per_nct)}")
    print()

    scored: list[dict] = []
    unmatched: list[str] = []
    for row in per_nct:
        nct = (row.get("nct") or "").lower()
        r1 = r1_by_nct.get(nct)
        if r1 is None:
            unmatched.append(row.get("nct", ""))
            continue
        atomic = row.get("atomic") or ""
        scored.append({
            "nct": row.get("nct"),
            "atomic": atomic,
            "rule": row.get("rule"),
            "r1": r1,
            "agree": agreement(atomic, r1),
        })

    print(f"Scored NCTs (atomic AND R1 present): {len(scored)}")
    if unmatched:
        print(f"Unmatched NCTs (not in R1 CSV): {len(unmatched)}")
        for nct in unmatched[:10]:
            print(f"  - {nct}")
        if len(unmatched) > 10:
            print(f"  (+{len(unmatched) - 10} more)")
    print()

    if not scored:
        print("no scorable NCTs — nothing to compare")
        return 0

    agreements = sum(1 for r in scored if r["agree"])
    print("=" * 80)
    print("AGREEMENT SUMMARY")
    print("=" * 80)
    print(f"  overall: {agreements}/{len(scored)}  ({agreements / len(scored):.1%})")
    print()

    by_rule: dict[str, list[dict]] = defaultdict(list)
    for r in scored:
        by_rule[r["rule"] or "?"].append(r)

    print("  by aggregator rule:")
    for rule in sorted(by_rule.keys()):
        rows = by_rule[rule]
        ok = sum(1 for r in rows if r["agree"])
        print(f"    {rule:<7s}  agree={ok:>2d}/{len(rows):<3d}  "
              f"({ok / len(rows):.0%})")
    print()

    disagreements = [r for r in scored if not r["agree"]]
    if disagreements:
        print("  disagreements:")
        print(f"    {'NCT':<14s}  {'rule':<6s}  {'atomic':<28s}  {'R1':<28s}")
        for r in disagreements:
            print(f"    {r['nct']:<14s}  {r['rule']:<6s}  "
                  f"{(r['atomic'] or '(none)'):<28s}  "
                  f"{(r['r1'] or '(blank)'):<28s}")
    print()

    # Confusion-ish matrix: atomic value × R1 value
    matrix: Counter[tuple[str, str]] = Counter()
    for r in scored:
        matrix[(r["atomic"] or "(none)", r["r1"] or "(blank)")] += 1
    print("  atomic × R1 confusion:")
    for (a, r1), n in matrix.most_common():
        mark = "=" if agreement(a, r1) else "!"
        print(f"    {mark} {a:<28s} × {r1:<28s}  {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

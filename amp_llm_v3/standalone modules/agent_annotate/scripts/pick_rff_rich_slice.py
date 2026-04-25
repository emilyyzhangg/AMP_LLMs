#!/usr/bin/env python3
"""Pick NCTs where GT has explicit RfF consensus — for first honest
RfF accuracy measurement."""
import csv, json, random, sys
from collections import Counter
from pathlib import Path

CSV = Path("/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/amp_llm_v3/standalone modules/agent_annotate/docs/human_ground_truth_train_df.csv")
TEST_BATCH = Path("/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/amp_llm_v3/standalone modules/agent_annotate/scripts/fast_learning_batch_50.txt")
JSON_BASE = Path("/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/amp_llm_v3/standalone modules/agent_annotate/results/json")
PRIOR_JOBS = ["c05f049fef32","fce16457226f","25cdead94bcc","c0f32e3ea9b8",
              "6e835a3e41a1","51a6c2a308f8","1796b3a3b35f","13e1c621d762"]


def load_excluded() -> set[str]:
    out: set[str] = set()
    if TEST_BATCH.exists():
        out |= {l.strip().upper() for l in TEST_BATCH.open() if l.strip()}
    for jid in PRIOR_JOBS:
        p = JSON_BASE / f"{jid}.json"
        if p.exists():
            d = json.load(p.open())
            for t in d.get("trials", []):
                out.add(t["nct_id"].upper())
    return out


def norm(s): return (s or "").strip().lower()


def consensus(a, b):
    a, b = norm(a), norm(b)
    if a and b:
        return a if a == b else None
    return a or b or None


def main() -> int:
    excluded = load_excluded()
    print(f"Excluding {len(excluded)} NCTs (test batch + prior jobs)", file=sys.stderr)

    # Pool by RfF category
    by_rff: dict[str, list[str]] = {
        "business reason": [],
        "toxic/unsafe": [],
        "recruitment issues": [],
        "ineffective for purpose": [],
        "due to covid": [],
    }
    seen = 0
    blank_rff = 0

    with CSV.open() as f:
        for row in csv.DictReader(f):
            nct = (row["nct_id"] or "").upper().strip()
            if not nct: continue
            seen += 1
            if nct in excluded: continue
            rff = consensus(row.get("Reason for Failure_ann1", ""),
                            row.get("Reason for Failure_ann2", ""))
            if not rff:
                blank_rff += 1
                continue
            if rff not in by_rff: continue
            # Also need outcome consensus = Failed/Terminated for RfF to fire
            # — but we WANT to test the agent's RfF gate, so include all RfF-set NCTs.
            by_rff[rff].append(nct)

    print(f"\nCandidate pool by RfF category (excluded GT-blank-RfF and prior NCTs):", file=sys.stderr)
    total = 0
    for k, v in by_rff.items():
        print(f"  {k}: {len(v)}", file=sys.stderr)
        total += len(v)
    print(f"  total: {total} (vs {seen} CSV rows, {blank_rff} GT-blank-RfF)", file=sys.stderr)

    # Stratified sample, target ~30 (pool is small for this niche)
    random.seed(42)
    targets = {
        "business reason": 8,
        "toxic/unsafe": 6,
        "recruitment issues": 8,
        "ineffective for purpose": 6,
        "due to covid": 4,
    }
    picks: list[str] = []
    for cat, n in targets.items():
        pool = by_rff[cat]
        take = min(n, len(pool))
        picks.extend(random.sample(pool, take))
    picks.sort()

    print(f"\nSelected {len(picks)} NCTs:", file=sys.stderr)
    for cat, n in targets.items():
        actual = min(n, len(by_rff[cat]))
        print(f"  {cat}: {actual}", file=sys.stderr)

    print(json.dumps(picks))
    return 0


if __name__ == "__main__":
    sys.exit(main())

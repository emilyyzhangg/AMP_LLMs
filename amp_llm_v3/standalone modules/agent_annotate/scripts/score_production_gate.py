#!/usr/bin/env python3
"""Score a completed production-gate job and emit a publication-grade report.

**Methodology note:** this script uses a strict R1==R2 (or only-one-filled)
GT consensus rule and exact string matching. Numbers will be LOWER than
the authoritative `compare_jobs.py` / `heldout_analysis.sh` output, which
uses fuzzier matching (e.g. variant tolerance). For the canonical
production-gate certification, run BOTH:
  1. `bash scripts/heldout_analysis.sh JOB_ID 51a6c2a308f8` — authoritative
     per-field accuracy + miss patterns
  2. `python3 scripts/score_production_gate.py JOB_ID` — per-outcome-class
     breakdown + Wald 95% CI half-widths + ship/accept decision template

This script's value is the per-outcome-class stratification (critical
because the production-gate slice is the FIRST scale measurement covering
terminated/failed/withdrawn) + Wald CI math. Treat per-field numbers
here as a stricter lower-bound sanity check, not the headline.

Math: 95% CI half-width via Wald approximation
  hw = 1.96 * sqrt(p*(1-p) / n)

Usage:
  python3 scripts/score_production_gate.py 826f2608ddd8 --write
  python3 scripts/score_production_gate.py JOB_ID --baseline 51a6c2a308f8
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path

PROD_JSON = Path(
    "/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca/amp_llm_v3/"
    "standalone modules/agent_annotate/results/json"
)
PKG_ROOT = Path(__file__).resolve().parents[1]
GT_PATH = PKG_ROOT / "docs" / "human_ground_truth_train_df.csv"
REPORT_OUT = PKG_ROOT / "docs" / "PRODUCTION_GATE_REPORT.md"

GT_COLS = {
    "classification": ("Classification_ann1", "Classification_ann2"),
    "peptide": ("Peptide_ann1", "Peptide_ann2"),
    "delivery_mode": ("Delivery Mode_ann1", "Delivery Mode_ann2"),
    "outcome": ("Outcome_ann1", "Outcome_ann2"),
    "reason_for_failure": ("Reason for Failure_ann1", "Reason for Failure_ann2"),
    # sequence is scored via sequences_match (set-containment), handled separately
}

PER_FIELD_TARGETS = {
    "classification": (0.95, 0.916),
    "peptide": (0.85, 0.484),
    "delivery_mode": (0.80, 0.682),
    "outcome": (0.65, 0.556),
    "sequence": (0.50, None),
    "reason_for_failure": (0.95, 0.913),
}


def norm(s: str) -> str:
    return (s or "").strip().lower()


def consensus(a: str, b: str) -> str | None:
    a, b = norm(a), norm(b)
    if a and b:
        return a if a == b else None
    return a or b or None


def wald_ci_half_width(p: float, n: int) -> float:
    if n == 0:
        return float("nan")
    return 1.96 * math.sqrt(p * (1 - p) / n)


def status_emoji(actual: float, target: float) -> str:
    if actual >= target:
        return "✅"
    if actual >= target - 0.05:
        return "⚠️"
    return "❌"


def load_gt() -> dict[str, dict[str, str]]:
    gt = {}
    with GT_PATH.open() as f:
        for r in csv.DictReader(f):
            nct = (r.get("nct_id") or "").upper().strip()
            if not nct:
                continue
            gt[nct] = {
                field: consensus(r.get(c1, ""), r.get(c2, ""))
                for field, (c1, c2) in GT_COLS.items()
            }
            # sequence GT is preserved raw for sequences_match
            gt[nct]["_raw_seq_r1"] = (r.get("Sequence_ann1") or "").strip()
            gt[nct]["_raw_seq_r2"] = (r.get("Sequence_ann2") or "").strip()
    return gt


def get_field(trial: dict, name: str) -> dict | None:
    for a in trial.get("annotations", []) or []:
        if isinstance(a, dict) and a.get("field_name") == name:
            return a
    return None


def score_field(trials: list[dict], gt: dict, field: str) -> dict:
    hits = 0
    misses = 0
    miss_pairs: Counter = Counter()
    for t in trials:
        nct = (t.get("nct_id") or "").upper()
        ann = get_field(t, field) or {}
        pred = norm(ann.get("value", ""))
        if not pred:
            continue
        gt_v = (gt.get(nct, {}) or {}).get(field)
        if not gt_v:
            continue
        if pred == gt_v:
            hits += 1
        else:
            misses += 1
            miss_pairs[f"{gt_v} → {pred}"] += 1
    return {"hits": hits, "misses": misses, "patterns": miss_pairs}


def score_sequence(trials: list[dict], gt: dict) -> dict:
    """Use sequences_match for set-containment scoring."""
    sys.path.insert(0, str(PKG_ROOT))
    from app.services.concordance_service import sequences_match

    hits = 0
    misses = 0
    for t in trials:
        nct = (t.get("nct_id") or "").upper()
        ann = get_field(t, "sequence") or {}
        pred = (ann.get("value") or "").strip()
        gt_entry = gt.get(nct, {})
        gt_seq = gt_entry.get("_raw_seq_r1") or gt_entry.get("_raw_seq_r2")
        if not gt_seq or gt_seq.lower() in ("n/a", "na"):
            continue
        if not pred or pred.lower() in ("n/a", "na"):
            misses += 1
            continue
        if sequences_match(gt_seq, pred):
            hits += 1
        else:
            misses += 1
    return {"hits": hits, "misses": misses, "patterns": Counter()}


def score_outcome_by_class(trials: list[dict], gt: dict) -> dict[str, dict]:
    """Stratify outcome accuracy by GT class (positive/unknown/terminated/etc)."""
    by_class: dict[str, dict[str, int]] = {}
    for t in trials:
        nct = (t.get("nct_id") or "").upper()
        ann = get_field(t, "outcome") or {}
        pred = norm(ann.get("value", ""))
        gt_v = (gt.get(nct, {}) or {}).get("outcome")
        if not gt_v or not pred:
            continue
        by_class.setdefault(gt_v, {"hits": 0, "n": 0})
        by_class[gt_v]["n"] += 1
        if pred == gt_v:
            by_class[gt_v]["hits"] += 1
    return by_class


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("job_id", help="completed production-gate job ID")
    ap.add_argument("--baseline", default="51a6c2a308f8")
    ap.add_argument("--write", action="store_true",
                    help=f"write report to {REPORT_OUT.relative_to(PKG_ROOT)}")
    args = ap.parse_args()

    job_path = PROD_JSON / f"{args.job_id}.json"
    if not job_path.exists():
        print(f"ERROR: job result not found at {job_path}", file=sys.stderr)
        return 1

    job = json.load(job_path.open())
    trials = job.get("trials") or job.get("results") or []
    gt = load_gt()

    elapsed_min = (job.get("progress", {}) or {}).get("elapsed_seconds", 0) / 60
    n_errors = len((job.get("progress", {}) or {}).get("errors", []) or [])
    n_warnings = len((job.get("progress", {}) or {}).get("warnings", []) or [])
    commit = job.get("commit_hash", "?")[:8]
    finished = job.get("finished_at", "?")

    out = []
    out.append(f"# Production Gate Certification Report\n")
    out.append(f"_Auto-generated by `scripts/score_production_gate.py {args.job_id}`_\n")

    out.append("## 1. Headline\n")
    out.append("| Item | Value |")
    out.append("|---|---|")
    out.append(f"| Code commit | `{commit}` |")
    out.append(f"| Slice | `production_gate_v42_7_22.json` ({len(trials)} trials) |")
    out.append(f"| Wall-clock | {elapsed_min/60:.1f} h ({int(elapsed_min)} min) |")
    out.append(f"| Errors | {n_errors} |")
    out.append(f"| Warnings | {n_warnings} |")
    out.append(f"| Job ID | `{args.job_id}` |")
    out.append(f"| Date completed | {finished} |\n")

    # Per-field accuracy
    out.append("## 2. Per-field accuracy (95% CI half-width via Wald approximation)\n")
    out.append("| Field | Target | Result | 95% CI | Status |")
    out.append("|---|---|---|---|---|")
    field_results: dict[str, dict] = {}
    for field, (target, _) in PER_FIELD_TARGETS.items():
        if field == "sequence":
            r = score_sequence(trials, gt)
        else:
            r = score_field(trials, gt, field)
        n = r["hits"] + r["misses"]
        p = r["hits"] / n if n else 0
        hw = wald_ci_half_width(p, n) if n else float("nan")
        emoji = status_emoji(p, target) if n else "—"
        ci_str = f"±{hw*100:.1f}pp" if n else "n/a"
        out.append(
            f"| {field} | ≥{int(target*100)}% | {r['hits']}/{n} = {p*100:.1f}% | {ci_str} | {emoji} |"
        )
        field_results[field] = {"hits": r["hits"], "n": n, "p": p, "hw": hw,
                                  "patterns": r["patterns"]}
    out.append("")

    # Outcome by class
    out.append("## 3. Outcome stratified by GT class\n")
    by_class = score_outcome_by_class(trials, gt)
    out.append("| GT outcome | n | hits | accuracy |")
    out.append("|---|---|---|---|")
    for cls in ("positive", "unknown", "terminated", "failed - completed trial", "withdrawn"):
        d = by_class.get(cls, {"n": 0, "hits": 0})
        n = d["n"]
        acc = d["hits"] / n * 100 if n else 0
        out.append(f"| {cls} | {n} | {d['hits']} | {acc:.1f}% |")
    out.append("")

    # vs human IRA
    out.append("## 4. Comparison to human inter-rater agreement\n")
    out.append("| Field | Human IRA | Agent | Δ (agent − human) |")
    out.append("|---|---|---|---|")
    for field, (_, human) in PER_FIELD_TARGETS.items():
        r = field_results[field]
        if human is None:
            out.append(f"| {field} | n/a | {r['p']*100:.1f}% | n/a |")
        else:
            delta = r["p"] - human
            out.append(
                f"| {field} | {human*100:.1f}% | {r['p']*100:.1f}% | "
                f"{'+' if delta >= 0 else ''}{delta*100:.1f}pp |"
            )
    out.append("")

    # Decision (strict-lower-bound bucketing only — NOT the headline)
    out.append("## 5. Strict-lower-bound bucketing (informational)\n")
    out.append(
        "> ⚠️ **NOT the headline.** This bucketing uses this script's strict "
        "exact-match scoring, which under-counts (e.g. RfF n=1 instead of n=22 on "
        "Job #100 because the agent legitimately emits blank for non-failed trials "
        "and this script doesn't credit blank-vs-blank). For the authoritative ship/accept/investigate "
        "decision, use `heldout_analysis.sh` numbers — they apply the same fuzzier "
        "matching as `compare_jobs.py` and are the canonical certification metric.\n"
    )
    ship = []
    accept = []
    investigate = []
    for field, (target, _) in PER_FIELD_TARGETS.items():
        r = field_results[field]
        if r["n"] == 0:
            continue
        p = r["p"]
        if p >= target:
            ship.append(f"{field} ({p*100:.1f}%, n={r['n']})")
        elif field == "outcome" and 0.55 <= p < target:
            accept.append(f"{field} ({p*100:.1f}%, n={r['n']}) — within GT-quality gray zone")
        else:
            investigate.append(f"{field} ({p*100:.1f}%, n={r['n']})")
    out.append(f"- Lower-bound SHIP ({len(ship)} fields): {', '.join(ship) or '(none)'}")
    out.append(f"- Lower-bound ACCEPT-with-CI ({len(accept)} fields): {', '.join(accept) or '(none)'}")
    out.append(f"- Lower-bound INVESTIGATE ({len(investigate)} fields): {', '.join(investigate) or '(none)'}")
    out.append("")

    # Methodology
    out.append("## 6. Methodology disclosure\n")
    out.append(
        "- **Data source:** `docs/human_ground_truth_train_df.csv` (680 NCTs total). "
        f"Production gate slice: {len(trials)} NCTs from training_csv − test_batch (50 reserved by API).\n"
        f"- **Code commit:** `{commit}`. Public via git history.\n"
        "- **Hardware:** Mac Mini M-series, Ollama-hosted qwen3:14b, 19 research agents in parallel per trial.\n"
        "- **GT consensus rule:** R1==R2, OR only one annotator filled in. Trials with R1≠R2 disagreement excluded.\n"
        "- **Sequence scoring:** `sequences_match` set-containment "
        "(canonicaliser strips terminal -OH/-NH₂ chemistry suffixes per v42.7.16).\n"
    )

    text = "\n".join(out)
    print(text)

    if args.write:
        REPORT_OUT.write_text(text)
        print(f"\n[written: {REPORT_OUT}]", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Run ONE annotation agent in isolation against CACHED research and score it.

Replays a single field's real agent (deterministic paths + its LLM calls) over
the research already saved from a past job — no full pipeline, no verification,
no other fields. Cross-field dependencies (peptide_result, classification_result,
outcome_result) are injected from GROUND TRUTH so the agent is tested with correct
upstream inputs.

Usage:
    python3 scripts/eval_agent.py <field> <research_job_id> [--limit N] [--errors]

    field ∈ peptide | classification | delivery_mode | outcome |
            reason_for_failure | sequence
"""
import asyncio
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.research import ResearchResult            # noqa: E402
from app.models.annotation import FieldAnnotation         # noqa: E402
from agents.annotation import ANNOTATION_AGENTS           # noqa: E402
from app.services.concordance_service import sequences_match  # noqa: E402

GT_PATH = ROOT / "docs" / "human_ground_truth_train_df.csv"
GT_COL = {
    "peptide": "Peptide", "classification": "Classification",
    "delivery_mode": "Delivery Mode", "outcome": "Outcome",
    "reason_for_failure": "Reason for Failure", "sequence": "Sequence",
}


def norm(s):
    return (s or "").strip().lower()


def consensus(a, b):
    a, b = norm(a), norm(b)
    if a and b:
        return a if a == b else None
    return a or b or None


def load_gt():
    gt = {}
    for r in csv.DictReader(GT_PATH.open()):
        nid = (r.get("nct_id") or "").strip().lower()
        if not nid:
            continue
        gt[nid] = {f: consensus(r.get(f"{c}_ann1"), r.get(f"{c}_ann2"))
                   for f, c in GT_COL.items()}
    return gt


def build_metadata(research, gt_row):
    """Interventions from clinical_protocol + upstream field deps from GT."""
    interventions, title, summary, detail = [], "", "", ""
    for r in research:
        if r.agent_name == "clinical_protocol" and r.raw_data:
            ps = r.raw_data.get("protocol_section") or r.raw_data.get("protocolSection") or {}
            idm = ps.get("identificationModule", {})
            dm = ps.get("descriptionModule", {})
            title = idm.get("briefTitle", "") or idm.get("officialTitle", "")
            summary = dm.get("briefSummary", "") or ""
            detail = dm.get("detailedDescription", "") or ""
            for iv in ps.get("armsInterventionsModule", {}).get("interventions", []):
                nm = iv.get("name", "")
                if nm:
                    interventions.append({"name": nm, "type": (iv.get("type") or "")})
    # enrich with EDAM resolved names (best-effort, like the orchestrator)
    try:
        from app.services.memory.memory_store import memory_store as _edam
        for iv in interventions:
            res = _edam.get_resolved_names(iv["name"]) or []
            if res:
                iv["resolved"] = res
    except Exception:
        pass
    md = {"interventions": interventions, "title": title,
          "brief_summary": summary, "detailed_description": detail}
    # inject upstream deps from GT (capitalized canonical values)
    if gt_row.get("peptide"):
        md["peptide_result"] = "True" if norm(gt_row["peptide"]) == "true" else "False"
    if gt_row.get("classification"):
        md["classification_result"] = gt_row["classification"]
    if gt_row.get("outcome"):
        md["outcome_result"] = gt_row["outcome"]
    return md


def matches(field, pred, gt):
    if field == "sequence":
        return sequences_match(gt, pred)
    return norm(pred) == norm(gt)


async def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__)
        sys.exit(1)
    field, job = args[0], args[1]
    limit = next((int(a.split("=")[1]) for a in sys.argv if a.startswith("--limit=")), None)
    if "--limit" in sys.argv:
        i = sys.argv.index("--limit")
        if i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])
    show_errors = "--errors" in sys.argv
    agent_cls = ANNOTATION_AGENTS.get(field)
    if not agent_cls:
        print(f"unknown field {field!r}; choose from {list(GT_COL)}")
        sys.exit(1)

    rdir = ROOT / "results" / "research" / job
    gt = load_gt()
    files = sorted(f for f in rdir.glob("*.json") if f.name != "_meta.json")
    hits = tot = blank = 0
    errors = []
    agent = agent_cls()
    for f in files:
        d = json.load(f.open())
        nid = (d.get("nct_id") or f.stem).lower()
        grow = gt.get(nid, {})
        gv = grow.get(field)
        if not gv or norm(gv) in ("", "n/a", "none"):
            continue
        research = [ResearchResult(**r) for r in (d.get("results") or [])]
        md = build_metadata(research, grow)
        try:
            ann = await agent.annotate(nid, research, metadata=md)
            pred = ann.value if isinstance(ann, FieldAnnotation) else str(ann)
        except Exception as e:
            pred = f"<error: {e}>"
        tot += 1
        if not pred or norm(pred) in ("n/a", "none", ""):
            blank += 1
        ok = matches(field, pred, gv)
        if ok:
            hits += 1
        elif show_errors:
            errors.append((nid, f"gt={gv!r}", f"pred={pred[:40]!r}"))
        if limit and tot >= limit:
            break
    print(f"{field} on job {job}: {hits}/{tot} = {hits/max(tot,1)*100:.1f}%"
          + (f" | blanks={blank}" if blank else ""))
    for e in errors:
        print("  MISS", *e)


if __name__ == "__main__":
    asyncio.run(main())

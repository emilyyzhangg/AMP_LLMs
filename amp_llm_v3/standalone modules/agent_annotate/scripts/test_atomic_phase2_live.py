#!/usr/bin/env python3
"""
Phase 2 live integration test for the atomic outcome pub-assessor.

Loads a small number of real annotation JSONs, picks their trial-specific (and
optionally ambiguous) publications, and runs PubAssessor against each via the
real ollama_client. Verifies:

  - LLM returns parseable JSON on our prompt
  - answers_from_json normalization survives real model quirks
  - compute_verdict produces sensible POSITIVE / FAILED / INDETERMINATE
  - Cache hit on second run

Usage:
    cd <agent_annotate_dir>
    python3 scripts/test_atomic_phase2_live.py \
        --annotation-dir /path/to/results/annotations/<job_id> \
        --nct NCT01661192 NCT02660008 \
        --model gemma3:12b \
        --limit-pubs 3 \
        --include-ambiguous
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import tempfile
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

from app.models.research import ResearchResult  # noqa: E402
from agents.annotation.outcome_atomic import OutcomeAtomicAgent  # noqa: E402
from agents.annotation.outcome_pub_assessor import (  # noqa: E402
    PubAssessor,
    PubAssessmentCache,
)
from app.services.ollama_client import ollama_client  # noqa: E402


def load_research_results(path: Path) -> list[ResearchResult]:
    data = json.loads(path.read_text())
    out: list[ResearchResult] = []
    for r in data.get("research_results", []):
        try:
            out.append(ResearchResult.model_validate(r))
        except Exception as e:
            print(f"  WARN: skipping malformed ResearchResult in {path.name}: {e}")
    return out


def extract_drug_names(research_results: list[ResearchResult]) -> list[str]:
    names: set[str] = set()
    for r in research_results:
        if r.agent_name == "clinical_protocol" and r.raw_data:
            proto = r.raw_data.get("protocol_section", r.raw_data.get("protocolSection", {}))
            arms = proto.get("armsInterventionsModule", {})
            for i in arms.get("interventions", []) or []:
                if i.get("name"):
                    names.add(i["name"])
    return sorted(names)


async def run(args) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    agent = OutcomeAtomicAgent()

    cache_dir = Path(args.cache_dir) if args.cache_dir else Path(tempfile.mkdtemp(prefix="pub_assess_"))
    print(f"cache dir: {cache_dir}")
    cache = PubAssessmentCache(cache_dir)

    assessor = PubAssessor(
        model=args.model,
        ollama_client=ollama_client,
        cache=cache,
        temperature=0.0,
    )

    all_ok = True
    for nct in args.nct:
        path = Path(args.annotation_dir) / f"{nct}.json"
        if not path.exists():
            print(f"\n=== {nct} === NOT FOUND at {path}")
            all_ok = False
            continue

        print(f"\n========== {nct} ==========")
        research_results = load_research_results(path)
        drug_names = extract_drug_names(research_results)
        print(f"  drugs: {drug_names[:3]}")
        snap = agent.compute_snapshot(nct, research_results)

        # Pick publications worth testing
        target_specs = {"trial_specific"}
        if args.include_ambiguous:
            target_specs.add("ambiguous")

        pubs_to_assess = [
            (pub, spec) for pub, spec in snap.classified_pubs if spec in target_specs
        ][: args.limit_pubs]

        print(f"  assessing {len(pubs_to_assess)} pub(s) out of {len(snap.classified_pubs)} total")

        for pub, spec in pubs_to_assess:
            print(f"\n  → PMID={pub.pmid or '(none)'} src={pub.source} spec={spec}")
            print(f"    title: {pub.title[:120]}")
            verdict = await assessor.assess(nct, pub, spec, drug_names)
            print(f"    verdict: {verdict.verdict}  "
                  f"cached={verdict.cached}  "
                  f"error={verdict.error or '-'}")
            a = verdict.answers
            print(f"    answers: q1={a.q1_reports_results} q2={a.q2_primary_met} "
                  f"q3={a.q3_efficacy} q4={a.q4_failure} q5={a.q5_advanced}")
            if a.evidence_quote:
                print(f"    quote: \"{a.evidence_quote[:140]}\"")
            if verdict.error:
                all_ok = False

    if not all_ok:
        return 1
    print("\nLive integration: OK")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--annotation-dir", required=True)
    p.add_argument("--nct", nargs="+", required=True)
    p.add_argument("--model", default="gemma3:12b")
    p.add_argument("--limit-pubs", type=int, default=3)
    p.add_argument("--include-ambiguous", action="store_true")
    p.add_argument("--cache-dir", default="")
    args = p.parse_args()
    sys.exit(asyncio.run(run(args)))

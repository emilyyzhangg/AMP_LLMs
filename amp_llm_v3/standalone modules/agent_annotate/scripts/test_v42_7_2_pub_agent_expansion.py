#!/usr/bin/env python3
"""
Test v42.7.2 pub-classifier agent expansion (2026-04-26).

Previously only `literature` agent's citations contributed to the outcome
dossier's publication list and keyword scan. OpenAlex, Semantic Scholar,
CrossRef, and bioRxiv (4 publication-shaped agents) were ignored —
discarding ~4 agents' worth of evidence.

This patch adds those 4 agent names to the publication-collection branch
in `_build_evidence_dossier`. Pub classifier's v42.6.15 review-shape
detection still filters review snippets out, so adding more pubs is safe.
"""
from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))


def test_pub_agents_set_includes_all_five():
    """Source check: _PUB_AGENTS tuple must include literature + the 4 new agents."""
    src = (PKG_ROOT / "agents" / "annotation" / "outcome.py").read_text()
    for ag in ('"literature"', '"openalex"', '"semantic_scholar"',
               '"crossref"', '"biorxiv"'):
        assert ag in src, f"_PUB_AGENTS missing {ag}"
    assert "_PUB_AGENTS = (" in src
    print("  ✓ _PUB_AGENTS includes literature + openalex + semantic_scholar + crossref + biorxiv")


def test_publication_data_block_uses_pub_agents():
    """The publication-data and keyword-scan blocks should both branch on
    `agent_name in _PUB_AGENTS` (was `agent_name == 'literature'`)."""
    src = (PKG_ROOT / "agents" / "annotation" / "outcome.py").read_text()
    # Two locations should now read 'in _PUB_AGENTS'
    occurrences = src.count("if result.agent_name in _PUB_AGENTS:")
    assert occurrences >= 2, (
        f"expected ≥2 'in _PUB_AGENTS' branches; got {occurrences}"
    )
    # The old narrow check should be gone for the publication block
    old_pat = "if result.agent_name == \"literature\":\n            for citation in getattr(result, \"citations\", []):\n                pmid"
    assert old_pat not in src, "old literature-only publication block still present"
    print("  ✓ publication-data + keyword-scan blocks both use _PUB_AGENTS")


def test_runtime_dossier_includes_openalex_pubs():
    """Build a stub research_results with an openalex citation and confirm
    it shows up in the dossier's publications list."""
    from app.models.research import ResearchResult, SourceCitation
    from agents.annotation.outcome import _build_evidence_dossier

    proto = ResearchResult(
        agent_name="clinical_protocol", nct_id="NCT00000001",
        citations=[],
        raw_data={"protocolSection": {
            "statusModule": {"overallStatus": "COMPLETED", "completionDateStruct": {"date": "2023-06-01"}},
            "armsInterventionsModule": {"interventions": []},
        }},
    )
    openalex_pub = ResearchResult(
        agent_name="openalex", nct_id="NCT00000001",
        citations=[SourceCitation(
            source_name="openalex",
            source_url="https://openalex.org/W123",
            identifier="W123",
            title="A randomized phase 2 trial of erenumab",
            snippet="A randomized phase 2 trial of erenumab in chronic migraine. NCT00000001 enrolled 100 patients...",
            quality_score=0.85,
            retrieved_at="2026-04-26T00:00:00",
        )],
        raw_data={},
    )
    dossier = _build_evidence_dossier([proto, openalex_pub], nct_id="NCT00000001")
    pubs = dossier.get("publications", [])
    assert len(pubs) >= 1, f"expected openalex pub in dossier; got {pubs}"
    assert any(p.get("source") == "openalex" for p in pubs), \
        f"openalex source not found in dossier: {[p.get('source') for p in pubs]}"
    # Should classify as trial_specific (NCT ID in snippet + phase marker)
    assert any(p.get("classification") == "trial_specific" for p in pubs)
    print("  ✓ openalex citation appears in dossier publications, classified trial_specific")


def test_runtime_dossier_includes_biorxiv_pub():
    from app.models.research import ResearchResult, SourceCitation
    from agents.annotation.outcome import _build_evidence_dossier
    proto = ResearchResult(
        agent_name="clinical_protocol", nct_id="NCT00000002",
        citations=[],
        raw_data={"protocolSection": {
            "statusModule": {"overallStatus": "COMPLETED"},
            "armsInterventionsModule": {"interventions": []},
        }},
    )
    biorxiv = ResearchResult(
        agent_name="biorxiv", nct_id="NCT00000002",
        citations=[SourceCitation(
            source_name="biorxiv_medrxiv",
            source_url="https://doi.org/10.1101/example",
            identifier="DOI:10.1101/example",
            title="Phase 1 trial preprint",
            snippet="Phase 1 first-in-human trial of XYZ. NCT00000002 reported safety.",
            quality_score=0.80,
            retrieved_at="2026-04-26T00:00:00",
        )],
        raw_data={},
    )
    dossier = _build_evidence_dossier([proto, biorxiv], nct_id="NCT00000002")
    pubs = dossier.get("publications", [])
    assert any(p.get("source") == "biorxiv_medrxiv" for p in pubs), \
        f"biorxiv source not in dossier: {[p.get('source') for p in pubs]}"
    print("  ✓ biorxiv citation appears in dossier publications")


def test_non_pub_agent_still_excluded():
    """An agent like dbaasp or chembl should NOT contribute to the
    publication list — those are DB-shaped, not pub-shaped."""
    from app.models.research import ResearchResult, SourceCitation
    from agents.annotation.outcome import _build_evidence_dossier
    proto = ResearchResult(
        agent_name="clinical_protocol", nct_id="NCT00000003",
        citations=[], raw_data={"protocolSection": {
            "statusModule": {"overallStatus": "COMPLETED"},
            "armsInterventionsModule": {"interventions": []},
        }},
    )
    dbaasp = ResearchResult(
        agent_name="dbaasp", nct_id="NCT00000003",
        citations=[SourceCitation(
            source_name="dbaasp",
            source_url="https://dbaasp.org/peptide/123",
            identifier="DBAASP:123",
            title="C16G2 - DBAASP",
            snippet="Peptide: C16G2\nSequence: TFFRLF...\nLength: 35 aa",
            quality_score=0.85,
            retrieved_at="2026-04-26T00:00:00",
        )],
        raw_data={},
    )
    dossier = _build_evidence_dossier([proto, dbaasp], nct_id="NCT00000003")
    pubs = dossier.get("publications", [])
    assert not any(p.get("source") == "dbaasp" for p in pubs), \
        f"dbaasp citations should NOT be in publications list: {pubs}"
    print("  ✓ dbaasp (non-pub agent) excluded from publications list")


def main() -> int:
    print("v42.7.2 pub-classifier agent-expansion tests")
    print("-" * 60)
    tests = [
        test_pub_agents_set_includes_all_five,
        test_publication_data_block_uses_pub_agents,
        test_runtime_dossier_includes_openalex_pubs,
        test_runtime_dossier_includes_biorxiv_pub,
        test_non_pub_agent_still_excluded,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            print(f"  ✗ {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            import traceback as tb
            print(f"  ✗ {t.__name__}: {type(e).__name__}: {e}")
            tb.print_exc()
            failed += 1
    print("-" * 60)
    print(f"{'FAIL' if failed else 'OK'}: {len(tests) - failed}/{len(tests)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

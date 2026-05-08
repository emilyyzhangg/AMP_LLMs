#!/usr/bin/env python3
"""Unit tests for v42.8.4 Lever 4 — drug-code → biological-name resolver.

Live tests hit PubChem + RxNorm public APIs. Skip-friendly: any test
that fails due to network is an environment issue, not a logic bug.

Run: python3 scripts/test_v42_8_4_drug_code_resolver.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

from agents.research.drug_code_resolver import (
    _is_uninformative_synonym,
    looks_like_pharma_code,
    resolve,
)


def test_looks_like_pharma_code():
    assert looks_like_pharma_code("PLG0206")
    assert looks_like_pharma_code("CBX129801")
    assert looks_like_pharma_code("GT-001")
    assert not looks_like_pharma_code("semaglutide")
    assert not looks_like_pharma_code("Heat Shock Protein 70")
    assert not looks_like_pharma_code("Whey")
    assert not looks_like_pharma_code("")


def test_uninformative_synonym_filters():
    # CAS numbers
    assert _is_uninformative_synonym("847061-43-2")
    # Database identifiers
    assert _is_uninformative_synonym("CHEMBL439312")
    assert _is_uninformative_synonym("UNII-12345")
    assert _is_uninformative_synonym("CID16152467")
    # Internal lab codes
    assert _is_uninformative_synonym("orb3142637")
    assert _is_uninformative_synonym("tp3849")
    # IUPAC stereo
    assert _is_uninformative_synonym(
        "L-ARGINYL-L-ARGINYL-L-TRYPTOPHYL-L-VALYL-L-ARGINYL-L-ARGINYL-L-VALYL-L-ARGINYL"
    )
    # Real names should pass through
    assert not _is_uninformative_synonym("WLBU2")
    assert not _is_uninformative_synonym("plectasin")
    assert not _is_uninformative_synonym("C-Peptide")


def test_resolve_pharma_code_pubchem():
    """Live test: PLG0206 → WLBU2."""
    candidates = asyncio.run(resolve("PLG0206"))
    assert candidates, "expected at least one candidate"
    names = [c["name"].lower() for c in candidates]
    assert any("wlbu2" in n for n in names), f"WLBU2 missing from {names}"


def test_resolve_pharma_code_pubchem_cbx():
    """Live test: CBX129801 → C-Peptide."""
    candidates = asyncio.run(resolve("CBX129801"))
    names = [c["name"].lower() for c in candidates]
    assert any("c-peptide" in n or "c peptide" in n for n in names), (
        f"C-Peptide missing from {names}"
    )


def test_resolve_marketed_drug_pubchem():
    """semaglutide should return brand names + alternative codes."""
    candidates = asyncio.run(resolve("semaglutide"))
    names = [c["name"].lower() for c in candidates]
    assert any(b in names for b in ("ozempic", "rybelsus", "wegovy")), (
        f"expected at least one brand name in {names}"
    )


def test_resolve_unknown_returns_empty():
    """Nonsense codes should return [] — no false fuzzy matches."""
    candidates = asyncio.run(resolve("FAKE-NONSENSE-12345"))
    assert candidates == [], f"expected empty list, got {candidates}"


def test_agent_research_outputs_resolved_map():
    """DrugCodeResolverAgent.research populates raw_data.resolved_drug_names."""
    from agents.research.drug_code_resolver import DrugCodeResolverAgent

    agent = DrugCodeResolverAgent()
    metadata = {"interventions": [{"name": "PLG0206"}, {"name": "Whey"}]}
    result = asyncio.run(agent.research("NCT00000001", metadata=metadata))
    assert result.agent_name == "drug_code_resolver"
    mapped = result.raw_data.get("resolved_drug_names", {})
    # PLG0206 should resolve; Whey is a food, not a drug — may or may not
    assert "PLG0206" in mapped, f"PLG0206 missing from {list(mapped.keys())}"
    assert any("wlbu2" in c["name"].lower() for c in mapped["PLG0206"])


def main() -> int:
    tests = [
        test_looks_like_pharma_code,
        test_uninformative_synonym_filters,
        test_resolve_pharma_code_pubchem,
        test_resolve_pharma_code_pubchem_cbx,
        test_resolve_marketed_drug_pubchem,
        test_resolve_unknown_returns_empty,
        test_agent_research_outputs_resolved_map,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ✓ {t.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"  ✗ {t.__name__}: {exc}")
        except Exception as exc:
            failed += 1
            print(f"  ✗ {t.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

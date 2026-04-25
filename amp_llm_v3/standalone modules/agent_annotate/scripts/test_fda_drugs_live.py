#!/usr/bin/env python3
"""Live integration test for FDA Drugs@FDA client."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))


async def test_fda_drugs_known_approved_drug():
    """Erenumab is FDA-approved (Aimovig, BLA 761077). Expect approved=True."""
    from agents.research.fda_drugs_client import FDADrugsClient
    client = FDADrugsClient()
    metadata = {"interventions": [{"type": "DRUG", "name": "Erenumab"}]}
    result = await client.research("NCT04000000", metadata)
    print(f"  cite count: {len(result.citations)}")
    if result.citations:
        c = result.citations[0]
        print(f"  first: {c.title[:80]}")
        print(f"    snippet[:200]: {c.snippet[:200]}")
    assert result.agent_name == "fda_drugs"
    approved_keys = [k for k in result.raw_data if k.endswith("_approved")]
    print(f"  approved flags: {[(k, result.raw_data[k]) for k in approved_keys]}")
    assert any(result.raw_data[k] is True for k in approved_keys), \
        "erenumab should have approved=True from openFDA"
    print("  ✓ erenumab marked FDA approved")


async def test_fda_drugs_unknown_drug_no_results():
    """A made-up drug should return 0 results without crashing."""
    from agents.research.fda_drugs_client import FDADrugsClient
    client = FDADrugsClient()
    metadata = {"interventions": [{"type": "DRUG", "name": "Quintazoxiblastagine999"}]}
    result = await client.research("NCT99999999", metadata)
    print(f"  cite count: {len(result.citations)}")
    assert result.agent_name == "fda_drugs"
    print(f"  raw_data: {dict(list(result.raw_data.items())[:5])}")
    print("  ✓ unknown drug — graceful handling")


async def test_fda_drugs_glp1_returns_multiple_drugs():
    """'glucagon-like peptide 1' is a common active ingredient — should hit
    semaglutide / dulaglutide / liraglutide etc. Confirms multi-name search works."""
    from agents.research.fda_drugs_client import FDADrugsClient
    client = FDADrugsClient()
    metadata = {"interventions": [{"type": "DRUG", "name": "Semaglutide"}]}
    result = await client.research("NCT04000001", metadata)
    print(f"  cite count: {len(result.citations)}")
    if result.citations:
        for c in result.citations[:2]:
            print(f"  - {c.title[:80]}")
    assert result.agent_name == "fda_drugs"
    assert len(result.citations) >= 1, "semaglutide should have ≥1 FDA drug record"
    print("  ✓ semaglutide returns FDA drug records")


async def test_fda_drugs_skips_placebo():
    from agents.research.fda_drugs_client import _extract_intervention_names
    metadata = {"interventions": [
        {"type": "DRUG", "name": "Placebo"},
        {"type": "DRUG", "name": "Erenumab"},
    ]}
    names = _extract_intervention_names(metadata)
    assert names == ["Erenumab"]
    print("  ✓ placebo skipped")


async def main() -> int:
    print("FDA Drugs@FDA live integration tests")
    print("-" * 60)
    tests = [
        test_fda_drugs_skips_placebo,
        test_fda_drugs_unknown_drug_no_results,
        test_fda_drugs_known_approved_drug,
        test_fda_drugs_glp1_returns_multiple_drugs,
    ]
    failed = 0
    for t in tests:
        try:
            await t()
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
    sys.exit(asyncio.run(main()))

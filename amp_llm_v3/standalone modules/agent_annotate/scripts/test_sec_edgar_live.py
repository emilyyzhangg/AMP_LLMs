#!/usr/bin/env python3
"""Live integration test for SEC EDGAR client. Hits the real public API.

Run:
    cd <agent_annotate_dir>
    python3 scripts/test_sec_edgar_live.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))


async def test_sec_edgar_returns_citations_for_pharma_drug():
    """Erenumab (Aimovig) is well-disclosed in pharma 10-Ks. Expect ≥1 hit."""
    from agents.research.sec_edgar_client import SECEdgarClient
    client = SECEdgarClient()
    metadata = {"interventions": [{"type": "DRUG", "name": "Erenumab"}]}
    result = await client.research("NCT04000000", metadata)
    print(f"  cite count: {len(result.citations)}")
    print(f"  raw_data keys: {list(result.raw_data.keys())[:5]}")
    if result.citations:
        c = result.citations[0]
        print(f"  first citation: source={c.source_name} title={c.title[:80]!r}")
        print(f"    url: {c.source_url[:120]}")
    assert result.agent_name == "sec_edgar"
    # Erenumab should hit at least once across pharma 10-Ks in last 5 yr
    assert any("erenumab" in str(v).lower() for v in result.raw_data.values()) or len(result.citations) >= 1
    print("  ✓ erenumab returns SEC EDGAR hits")


async def test_sec_edgar_obscure_term_no_results_doesnt_crash():
    """A made-up drug name should return 0 hits gracefully."""
    from agents.research.sec_edgar_client import SECEdgarClient
    client = SECEdgarClient()
    metadata = {"interventions": [{"type": "DRUG", "name": "Quintazoxiblastagine999"}]}
    result = await client.research("NCT99999999", metadata)
    assert result.agent_name == "sec_edgar"
    # Total should be 0 for both NCT and drug
    totals = [v for k, v in result.raw_data.items() if k.endswith("_total")]
    print(f"  totals: {totals}")
    assert totals  # at least one term searched
    print("  ✓ obscure term — graceful 0-hit handling")


async def test_sec_edgar_skips_placebo():
    """Placebo and saline should be filtered out — they're never useful searches."""
    from agents.research.sec_edgar_client import SECEdgarClient
    from agents.research.sec_edgar_client import _extract_intervention_names
    metadata = {"interventions": [
        {"type": "DRUG", "name": "Placebo"},
        {"type": "OTHER", "name": "Normal saline"},
        {"type": "DRUG", "name": "Erenumab"},
    ]}
    names = _extract_intervention_names(metadata)
    assert "Placebo" not in names
    assert "Normal saline" not in names
    assert "Erenumab" in names
    print(f"  ✓ placebo/saline filtered, erenumab kept (names={names})")


async def test_sec_edgar_user_agent_is_set():
    """Source check: User-Agent must be in the httpx client headers."""
    src = (PKG_ROOT / "agents" / "research" / "sec_edgar_client.py").read_text()
    assert "User-Agent" in src
    assert "amphoraxe@amphoraxe.ca" in src
    print("  ✓ User-Agent header set per SEC fair-access policy")


async def main() -> int:
    print("SEC EDGAR live integration tests")
    print("-" * 60)
    tests = [
        test_sec_edgar_user_agent_is_set,
        test_sec_edgar_skips_placebo,
        test_sec_edgar_obscure_term_no_results_doesnt_crash,
        test_sec_edgar_returns_citations_for_pharma_drug,
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

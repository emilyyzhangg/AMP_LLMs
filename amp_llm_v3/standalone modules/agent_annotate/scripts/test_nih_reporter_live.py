#!/usr/bin/env python3
"""Live integration test for NIH RePORTER client. Hits the real public API.

Run:
    cd <agent_annotate_dir>
    python3 scripts/test_nih_reporter_live.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))


async def test_nih_reporter_returns_citations_for_well_funded_drug():
    """Liraglutide is well-funded by NIH (325+ projects). Expect ≥1 hit."""
    from agents.research.nih_reporter_client import NIHRePORTERClient
    client = NIHRePORTERClient()
    metadata = {"interventions": [{"type": "DRUG", "name": "Liraglutide"}]}
    result = await client.research("NCT04000000", metadata)
    print(f"  cite count: {len(result.citations)}")
    print(f"  raw_data keys: {list(result.raw_data.keys())[:5]}")
    if result.citations:
        c = result.citations[0]
        print(f"  first citation: source={c.source_name} title={c.title[:80]!r}")
        print(f"    url: {c.source_url[:120]}")
    assert result.agent_name == "nih_reporter"
    counts = [v for k, v in result.raw_data.items() if k.endswith("_count")]
    print(f"  totals: {counts}")
    assert counts and counts[0] >= 100, \
        f"liraglutide should have ≥100 NIH-funded projects (got {counts})"
    assert len(result.citations) >= 1
    print("  ✓ liraglutide returns NIH RePORTER hits")


async def test_nih_reporter_obscure_term_no_results_doesnt_crash():
    """A made-up drug name should return 0 hits gracefully."""
    from agents.research.nih_reporter_client import NIHRePORTERClient
    client = NIHRePORTERClient()
    metadata = {"interventions": [{"type": "DRUG", "name": "Quintazoxiblastagine999"}]}
    result = await client.research("NCT99999999", metadata)
    assert result.agent_name == "nih_reporter"
    counts = [v for k, v in result.raw_data.items() if k.endswith("_count")]
    print(f"  counts: {counts}")
    assert counts == [0], f"obscure drug should have 0 NIH-funded projects (got {counts})"
    assert len(result.citations) == 0
    print("  ✓ obscure term — graceful 0-hit handling")


async def test_nih_reporter_skips_placebo():
    """Placebo and saline should be filtered out — same rule as SEC EDGAR / FDA Drugs."""
    from agents.research.nih_reporter_client import _extract_intervention_names
    metadata = {"interventions": [
        {"type": "DRUG", "name": "Placebo"},
        {"type": "OTHER", "name": "Normal saline"},
        {"type": "DRUG", "name": "Liraglutide"},
    ]}
    names = _extract_intervention_names(metadata)
    assert "Placebo" not in names
    assert "Normal saline" not in names
    assert "Liraglutide" in names
    print(f"  ✓ placebo/saline filtered, liraglutide kept (names={names})")


async def test_nih_reporter_advanced_text_search_is_the_filter():
    """Source check: must use advanced_text_search (the only criterion that
    actually filters; clinical_trial_ids silently no-ops on this API)."""
    src = (PKG_ROOT / "agents" / "research" / "nih_reporter_client.py").read_text()
    assert '"advanced_text_search"' in src or "'advanced_text_search'" in src, \
        "must use advanced_text_search criterion"
    # The bad criterion (clinical_trial_ids) silently no-ops; it must not
    # appear as a JSON key. The substring is allowed in the docstring,
    # so we look only for it in JSON-key context: a quoted form.
    assert '"clinical_trial_ids"' not in src and "'clinical_trial_ids'" not in src, \
        "clinical_trial_ids silently no-ops on RePORTER — never use it as a criterion"
    print("  ✓ advanced_text_search criterion used; clinical_trial_ids avoided")


async def test_nih_reporter_no_results_when_no_interventions():
    """If metadata has no DRUG/BIOLOGICAL interventions, agent returns
    empty result without making an API call (saves request budget)."""
    from agents.research.nih_reporter_client import NIHRePORTERClient
    client = NIHRePORTERClient()
    result = await client.research("NCT00000000", metadata={"interventions": []})
    assert result.citations == []
    assert "No interventions" in result.raw_data.get("note", "")
    print("  ✓ short-circuits when no interventions present")


async def main() -> int:
    print("NIH RePORTER live integration tests")
    print("-" * 60)
    tests = [
        test_nih_reporter_advanced_text_search_is_the_filter,
        test_nih_reporter_skips_placebo,
        test_nih_reporter_no_results_when_no_interventions,
        test_nih_reporter_obscure_term_no_results_doesnt_crash,
        test_nih_reporter_returns_citations_for_well_funded_drug,
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

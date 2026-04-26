#!/usr/bin/env python3
"""
Tests for v42.7.4 source-weighted keyword scan (2026-04-26).

Two-tier publication source treatment:
  publication-list (LLM-visible)  — all 5 pub agents (broad context)
  keyword scan (deterministic override) — peer-reviewed only (literature, openalex)

Job #88 (47-NCT cumulative test) showed:
  outcome -2.1pp (61.7% → 59.6%)
  RfF +7.6pp (83.3% → 90.9%)
when v42.7.2 expanded both branches to all 5 agents. Restricting the
keyword scan to high-quality sources should recover outcome without
losing RfF.
"""
from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))


def test_two_tier_pub_agent_sets_present():
    src = (PKG_ROOT / "agents" / "annotation" / "outcome.py").read_text()
    assert "_PUB_AGENTS = (" in src
    assert "_PUB_AGENTS_HIGH_QUALITY = (" in src, "high-quality tier missing"
    print("  ✓ both _PUB_AGENTS (broad) and _PUB_AGENTS_HIGH_QUALITY tiers defined")


def test_high_quality_set_is_subset():
    """The high-quality tier must be a subset of the broad tier."""
    import re
    src = (PKG_ROOT / "agents" / "annotation" / "outcome.py").read_text()
    m_broad = re.search(r"_PUB_AGENTS = \(([^)]*)\)", src)
    m_hq = re.search(r"_PUB_AGENTS_HIGH_QUALITY = \(([^)]*)\)", src)
    assert m_broad and m_hq
    broad = {a.strip().strip('"\'') for a in m_broad.group(1).split(",") if a.strip()}
    hq = {a.strip().strip('"\'') for a in m_hq.group(1).split(",") if a.strip()}
    assert hq.issubset(broad), f"hq {hq} not a subset of broad {broad}"
    # Specifically: hq should be {literature, openalex}
    assert "literature" in hq and "openalex" in hq
    # Specifically: hq should NOT include preprints/aggregators
    assert "biorxiv" not in hq
    assert "semantic_scholar" not in hq
    assert "crossref" not in hq
    print(f"  ✓ high-quality subset = {sorted(hq)}; preprints/aggregators excluded")


def test_publication_list_uses_broad_set():
    """The publication-list-build branch must still use the broad _PUB_AGENTS
    (all 5 sources) — LLM benefits from broader context."""
    src = (PKG_ROOT / "agents" / "annotation" / "outcome.py").read_text()
    # The publication-list IF statement should branch on broad _PUB_AGENTS.
    # Look for the specific pattern: the if-statement preceding the for-citation
    # loop that builds the pub dict.
    import re
    # Match the if-clause that's followed by the for-citation pub building.
    m = re.search(
        r'if result\.agent_name in (_PUB_AGENTS\w*):\s*\n'
        r'\s*for citation in getattr\(result, "citations", \[\]\):\s*\n'
        r'\s*pmid = ',
        src,
    )
    assert m, "couldn't locate publication-list if-clause"
    var = m.group(1)
    assert var == "_PUB_AGENTS", \
        f"publication-list should use broad _PUB_AGENTS, found {var}"
    print(f"  ✓ publication-list block uses broad {var} (5 sources)")


def test_keyword_scan_uses_hq_set():
    """The keyword-scan branch must use _PUB_AGENTS_HIGH_QUALITY."""
    src = (PKG_ROOT / "agents" / "annotation" / "outcome.py").read_text()
    keyword_idx = src.find('# --- v41: Scan ONLY')
    # Look in the rest of the file from the keyword scan onwards
    rest = src[keyword_idx:keyword_idx + 1500]
    assert "if result.agent_name in _PUB_AGENTS_HIGH_QUALITY:" in rest, \
        "keyword scan must use HIGH_QUALITY subset"
    print("  ✓ keyword-scan block uses _PUB_AGENTS_HIGH_QUALITY (literature + openalex)")


def main() -> int:
    print("v42.7.4 quality-tier keyword scan tests")
    print("-" * 60)
    tests = [
        test_two_tier_pub_agent_sets_present,
        test_high_quality_set_is_subset,
        test_publication_list_uses_broad_set,
        test_keyword_scan_uses_hq_set,
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

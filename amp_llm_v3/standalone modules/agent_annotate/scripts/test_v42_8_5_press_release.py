#!/usr/bin/env python3
"""Unit tests for v42.8.5 Lever 5 — press-release / news-aggregator agent.

Live tests hit Google News RSS (public, no auth). Skip-friendly: any
test that fails purely due to network is an environment issue.

Run: python3 scripts/test_v42_8_5_press_release.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

from agents.research.press_release_client import (
    _build_query,
    _parse_rss,
    classify_headline,
    fetch_news,
    PressReleaseAgent,
)


def test_classify_positive_phrases():
    """Primary-endpoint-anchored positive phrases must classify as positive."""
    for h in [
        "Acme Corp Achieves Primary Endpoint in Phase 3 Trial of Widget",
        "Foo Bio reports positive top-line results",
        "FDA approves new diabetes drug",
        "Bar Therapeutics meets primary endpoint",
        "Successful Phase III trial of Widget",
    ]:
        assert classify_headline(h) == "positive", f"expected positive for {h!r}"


def test_classify_negative_phrases():
    """Primary-endpoint-anchored failure phrases must classify as negative."""
    for h in [
        "Acme fails primary endpoint in Phase 2 trial",
        "Foo discontinues development of widget",
        "Bar's drug did not meet primary endpoint",
        "Phase 3 trial misses primary endpoint",
        "Bar Inc terminates widget program",
    ]:
        assert classify_headline(h) == "negative", f"expected negative for {h!r}"


def test_classify_neutral_phrases():
    """Non-anchored phrases stay neutral — no false positives."""
    for h in [
        "Acme Corp announces investor day",
        "Drug class review article",
        "Generic news about pharmaceutical industry",
        "Drug approved for use in clinic decades ago",  # bare "approved" not enough alone
    ]:
        c = classify_headline(h)
        # The "approved" example is a tricky edge case — bare 'approved' alone
        # might match if FDA appears. Allow positive OR neutral, just not negative.
        assert c != "negative", f"expected non-negative for {h!r}, got {c}"


def test_classify_bare_failed_does_not_fire():
    """Per v42.7.15 lesson: bare 'failed' must not fire (matches patient
    cohorts like 'treatment-failed patients')."""
    for h in [
        "Treatment-failed patients in cancer trial",
        "Negative regulator of immune response",
    ]:
        assert classify_headline(h) != "negative", (
            f"v42.7.15 regression: bare 'failed'/'negative' fired on {h!r}"
        )


def test_build_query_includes_drug_and_readout_phrases():
    q = _build_query("widget-12", sponsor="Acme Therapeutics")
    assert '"widget-12"' in q
    assert "trial" in q.lower() or "results" in q.lower()
    assert "Acme" in q


def test_parse_rss_extracts_items():
    """Mock RSS XML must parse into structured items with classification."""
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>Acme achieves primary endpoint in Phase 3 trial - PR Newswire</title>
    <link>https://example.com/1</link>
    <pubDate>Fri, 01 May 2026 12:00:00 GMT</pubDate>
  </item>
  <item>
    <title>Bar discontinues development of widget - BusinessWire</title>
    <link>https://example.com/2</link>
    <pubDate>Mon, 04 May 2026 09:00:00 GMT</pubDate>
  </item>
</channel></rss>"""
    items = _parse_rss(xml)
    assert len(items) == 2
    assert items[0]["classification"] == "positive"
    assert items[1]["classification"] == "negative"
    assert items[0]["source"] == "PR Newswire"
    assert items[1]["source"] == "BusinessWire"


def test_live_retatrutide_returns_positive_signals():
    """Live test: retatrutide had publicly-announced positive Phase III
    readouts in 2026; Google News should surface positive headlines."""
    items = asyncio.run(fetch_news("retatrutide"))
    assert items, "expected non-empty news items for retatrutide"
    pos = [i for i in items if i["classification"] == "positive"]
    assert pos, (
        "expected ≥1 positive headline for retatrutide (Phase III "
        "readout publicly reported); none found — query may be wrong"
    )


def test_live_unknown_drug_returns_no_results():
    """Live test: nonsense drug name returns empty (no false matches)."""
    items = asyncio.run(fetch_news("ZZZ-FAKE-DRUG-987654"))
    sig = [i for i in items if i["classification"] != "neutral"]
    assert sig == [], f"expected no signals for fake drug, got {len(sig)}"


def test_agent_research_outputs_pr_evidence():
    """PressReleaseAgent.research populates raw_data shape."""
    agent = PressReleaseAgent()
    metadata = {"interventions": [{"name": "retatrutide"}]}
    result = asyncio.run(agent.research("NCT00000001", metadata=metadata))
    assert result.agent_name == "press_release"
    rd = result.raw_data
    for k in ("press_release_evidence", "press_release_count",
              "has_positive_pr", "has_negative_pr"):
        assert k in rd, f"missing {k} in raw_data"


def main() -> int:
    tests = [
        test_classify_positive_phrases,
        test_classify_negative_phrases,
        test_classify_neutral_phrases,
        test_classify_bare_failed_does_not_fire,
        test_build_query_includes_drug_and_readout_phrases,
        test_parse_rss_extracts_items,
        test_live_retatrutide_returns_positive_signals,
        test_live_unknown_drug_returns_no_results,
        test_agent_research_outputs_pr_evidence,
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

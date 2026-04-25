#!/usr/bin/env python3
"""
Tests for v42.6.16 (2026-04-25).

Job #83 confusion matrix had 6 GT=positive trials predicted as Unknown.
5 of 6 were Phase 1 — the agent correctly applied rule 7 (Phase 1 needs
explicit primary-endpoint-met statement, not just safety+biomarker
language). v42.6.16 broadens the strong-efficacy phrase list with more
verb patterns, all requiring 'primary' as an anchor to keep noise low.
"""

from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

from agents.annotation.outcome import OutcomeAgent  # noqa: E402


def test_new_strong_efficacy_phrases_recognized():
    """All four new patterns count as strong efficacy."""
    assert OutcomeAgent._has_strong_efficacy(["the trial achieved primary endpoint"])
    assert OutcomeAgent._has_strong_efficacy(["achieved its primary endpoint"])
    assert OutcomeAgent._has_strong_efficacy(["primary outcome was met"])
    assert OutcomeAgent._has_strong_efficacy(["primary outcome achieved"])
    assert OutcomeAgent._has_strong_efficacy(["demonstrated efficacy in primary outcome"])
    assert OutcomeAgent._has_strong_efficacy(["demonstrated efficacy on primary endpoint"])
    assert OutcomeAgent._has_strong_efficacy(["significant improvement in the primary measure"])
    assert OutcomeAgent._has_strong_efficacy(["significantly improved the primary outcome"])
    print("  ✓ new strong-efficacy phrases recognized (primary-anchored)")


def test_new_phrases_still_require_primary_anchor():
    """Stripping 'primary' from the phrase makes it weak (no false flip on
    review-style 'demonstrated efficacy' generic language)."""
    assert not OutcomeAgent._has_strong_efficacy(["demonstrated efficacy"])
    assert not OutcomeAgent._has_strong_efficacy(["demonstrated efficacy in mice"])
    assert not OutcomeAgent._has_strong_efficacy(["significant improvement"])
    assert not OutcomeAgent._has_strong_efficacy(["achieved a response"])
    print("  ✓ same phrases without 'primary' anchor stay weak")


def test_existing_strong_signals_unchanged():
    """v42.6.11/14 list still works."""
    assert OutcomeAgent._has_strong_efficacy(["primary endpoint met"])
    assert OutcomeAgent._has_strong_efficacy(["p < 0.05"])
    assert OutcomeAgent._has_strong_efficacy(["FDA approved"])
    assert OutcomeAgent._has_strong_efficacy(["regulatory approval"])
    assert not OutcomeAgent._has_strong_efficacy(["clinical benefit"])
    assert not OutcomeAgent._has_strong_efficacy(["efficacy"])
    assert not OutcomeAgent._has_strong_efficacy(["approved"])  # bare approved still weak
    print("  ✓ v42.6.11/14 strong + weak classifications preserved")


def main() -> int:
    print("v42.6.16 primary-anchor efficacy tests")
    print("-" * 60)
    tests = [
        test_new_strong_efficacy_phrases_recognized,
        test_new_phrases_still_require_primary_anchor,
        test_existing_strong_signals_unchanged,
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

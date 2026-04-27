#!/usr/bin/env python3
"""
Tests for v42.7.15 — negative keyword tightening (2026-04-27).

The _NEGATIVE_KW list in agents/annotation/outcome.py used to include
bare "failed" and "negative". These tokens fire too easily on patient-
cohort descriptions and mechanistic terminology that have nothing to do
with trial outcome:

  bare "failed":
    "treatment-failed patients" — describes the patient population
    "previously failed standard therapy" — patient eligibility criterion
    "failed initial therapy" — same

  bare "negative":
    "negative control" — experimental design
    "negative regulator" — mechanistic biology
    "negative cohort" — placebo group label

When these tokens fire on trial-specific publications, they incorrectly
populate dossier["negative_keywords"], which can flip the outcome
override to Failed even when the trial actually succeeded.

v42.7.15 removes the bare tokens and adds outcome-specific replacements
("trial failed", "primary endpoint not met", "primary outcome not met",
"primary endpoint was not met").
"""
from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

OUTCOME_PATH = PKG_ROOT / "agents" / "annotation" / "outcome.py"


def _extract_negative_kw_list() -> list[str]:
    """Source-level extraction of the _NEGATIVE_KW tuple."""
    src = OUTCOME_PATH.read_text()
    import re
    m = re.search(r"_NEGATIVE_KW = \[\s*((?:[^]])*?)\s*\]", src, re.DOTALL)
    assert m, "_NEGATIVE_KW list not found"
    body = m.group(1)
    # Match any quoted string
    items = re.findall(r'"([^"]+)"', body)
    return items


def test_bare_failed_removed():
    """The bare 'failed' token must be removed from _NEGATIVE_KW.
    'failed to meet', 'failed primary', 'trial failed' are OK because
    they're outcome-specific phrases."""
    items = _extract_negative_kw_list()
    assert "failed" not in items, (
        "v42.7.15: bare 'failed' must NOT be in _NEGATIVE_KW — fires on "
        "'treatment-failed patients' / 'previously failed therapy' (cohort "
        "descriptions, not outcome signals)."
    )
    print("  ✓ bare 'failed' removed (still has 'failed to meet', 'failed primary', 'trial failed')")


def test_bare_negative_removed():
    """Bare 'negative' must be removed — fires on 'negative control' /
    'negative regulator' / 'negative cohort' (mechanistic terminology)."""
    items = _extract_negative_kw_list()
    assert "negative" not in items, (
        "v42.7.15: bare 'negative' must NOT be in _NEGATIVE_KW — fires "
        "on 'negative control' / 'negative regulator' (mechanistic terms)."
    )
    print("  ✓ bare 'negative' removed")


def test_outcome_specific_phrases_added():
    items = _extract_negative_kw_list()
    must_have = [
        "did not meet",
        "primary endpoint not met",
        "primary endpoint was not met",
        "primary outcome not met",
        "trial failed",
        "futility",
    ]
    for kw in must_have:
        assert kw in items, f"v42.7.15: outcome-specific phrase {kw!r} missing"
    print(f"  ✓ outcome-specific phrases present ({len(must_have)} checked)")


def test_failed_qualifiers_still_present():
    """Outcome-specific 'failed X' phrases stay (the discriminator)."""
    items = _extract_negative_kw_list()
    qualified = [
        "failed to meet",
        "failed to demonstrate",
        "failed primary",
        "trial failed",
    ]
    for kw in qualified:
        assert kw in items, f"v42.7.15: qualified {kw!r} missing"
    print("  ✓ qualified 'failed X' phrases retained")


def test_runtime_failed_cohort_no_longer_flips():
    """End-to-end-ish: build a stub dossier where pub text says
    "treatment-failed patients" — pre-v42.7.15 this would populate
    negative_keywords with 'failed'. Confirm the new list doesn't match."""
    items = _extract_negative_kw_list()
    sample_text = (
        "long-term follow-up of treatment-failed patients with refractory "
        "disease who previously failed standard therapy."
    )
    sample_lower = sample_text.lower()
    matched = [kw for kw in items if kw in sample_lower]
    assert matched == [], (
        f"v42.7.15: cohort-description text matched {matched!r} — those "
        f"keywords are still over-firing."
    )
    print("  ✓ patient-cohort text 'treatment-failed patients' no longer matches")


def test_runtime_negative_control_no_longer_flips():
    items = _extract_negative_kw_list()
    sample_text = (
        "the assay used PBS as a negative control. The drug acts as a "
        "negative regulator of cytokine production."
    ).lower()
    matched = [kw for kw in items if kw in sample_text]
    assert matched == [], (
        f"v42.7.15: 'negative control' / 'negative regulator' matched {matched!r}"
    )
    print("  ✓ 'negative control' / 'negative regulator' no longer match")


def test_runtime_real_failure_still_matches():
    """Sanity: real trial-failure phrases STILL match."""
    items = _extract_negative_kw_list()
    sample_text = (
        "the trial failed; the primary endpoint was not met. "
        "drug X showed lack of efficacy in the intent-to-treat population."
    ).lower()
    matched = [kw for kw in items if kw in sample_text]
    assert len(matched) >= 2, (
        f"v42.7.15: real trial-failure text should still match ≥2 keywords; "
        f"got {matched}"
    )
    print(f"  ✓ real trial-failure text still matches: {matched}")


def main() -> int:
    print("v42.7.15 negative keyword tightening tests")
    print("-" * 60)
    tests = [
        test_bare_failed_removed,
        test_bare_negative_removed,
        test_outcome_specific_phrases_added,
        test_failed_qualifiers_still_present,
        test_runtime_failed_cohort_no_longer_flips,
        test_runtime_negative_control_no_longer_flips,
        test_runtime_real_failure_still_matches,
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

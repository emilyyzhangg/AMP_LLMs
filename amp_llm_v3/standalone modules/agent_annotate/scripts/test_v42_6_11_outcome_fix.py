#!/usr/bin/env python3
"""
Tests for v42.6.11 outcome Pass 2 overcall fix (2026-04-24).

Job #79 analysis identified 9 of 11 Positive over-calls coming from
`_dossier_publication_override` + `skip_verification` firing on loose
efficacy keywords present in review-article titles. v42.6.11 narrows both
to require STRONG efficacy signals (primary endpoint met, p<0.05, approval,
explicit phase advancement).

Pure logic checks — no network, no LLM.

Usage:
    cd <agent_annotate_dir>
    python3 scripts/test_v42_6_11_outcome_fix.py
"""

from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

from agents.annotation.outcome import OutcomeAgent  # noqa: E402


def _base_dossier(**overrides) -> dict:
    """Default dossier skeleton. Override any field via kwargs."""
    d = {
        "registry_status": "COMPLETED",
        "has_results": False,
        "phase": "PHASE2",
        "primary_endpoints": [],
        "days_since_completion": 100,
        "why_stopped": "",
        "stale_status": False,
        "trial_specific_count": 0,
        "publication_count": 0,
        "publications": [],
        "positive_keywords": [],
        "negative_keywords": [],
        "efficacy_keywords": [],
        "safety_keywords": [],
        "drug_max_phase": None,
        "completion_date": "2026-01-15",
    }
    d.update(overrides)
    return d


def test_strong_efficacy_detector_positive_cases():
    """Strong efficacy keywords are recognized (updated v42.6.14: bare
    'approved' no longer qualifies — see test_v42_6_14_delivery_crash_and_
    approval_narrowing.py for the regulatory-qualified variants)."""
    assert OutcomeAgent._has_strong_efficacy(["primary endpoint met"])
    assert OutcomeAgent._has_strong_efficacy(["the trial met the primary endpoint"])
    assert OutcomeAgent._has_strong_efficacy(["p < 0.05 was observed"])
    assert OutcomeAgent._has_strong_efficacy(["p<0.05 on the primary endpoint"])
    assert OutcomeAgent._has_strong_efficacy(["statistically significant improvement"])
    # v42.6.14: require a regulatory qualifier on approval phrases
    assert OutcomeAgent._has_strong_efficacy(["FDA approved"])
    assert OutcomeAgent._has_strong_efficacy(["regulatory approval"])
    assert OutcomeAgent._has_strong_efficacy(["received approval from the agency"])
    print("  ✓ strong efficacy signals recognized (primary endpoint, p<0.05, qualified approval)")


def test_strong_efficacy_detector_negative_cases():
    """Loose efficacy words alone are NOT strong."""
    assert not OutcomeAgent._has_strong_efficacy([])
    assert not OutcomeAgent._has_strong_efficacy(["efficacy", "effective"])
    assert not OutcomeAgent._has_strong_efficacy(["clinical benefit", "improvement"])
    assert not OutcomeAgent._has_strong_efficacy(["objective response", "antitumor activity"])
    assert not OutcomeAgent._has_strong_efficacy(["results showed benefit"])
    assert not OutcomeAgent._has_strong_efficacy(["safe and effective"])  # 'effective' alone weak
    print("  ✓ loose efficacy/benefit keywords alone → NOT strong (no false flip)")


def test_override_does_not_fire_on_single_pub_weak_signals():
    """NCT04590872 pattern: 1 trial-specific pub, weak efficacy language → no override."""
    d = _base_dossier(
        registry_status="ACTIVE_NOT_RECRUITING",
        days_since_completion=689,
        stale_status=True,
        trial_specific_count=1,
        efficacy_keywords=["efficacy", "clinical benefit"],  # weak
        publication_count=1,
    )
    result = OutcomeAgent._dossier_publication_override(d, "Unknown")
    assert result is None, f"single pub + weak keywords must not override, got {result}"
    print("  ✓ single pub + weak efficacy → no flip (fix for NCT04590872-class over-calls)")


def test_override_does_not_fire_on_many_pubs_weak_signals():
    """Many reviews with weak efficacy language still must not flip Unknown → Positive."""
    d = _base_dossier(
        registry_status="COMPLETED",
        trial_specific_count=20,
        efficacy_keywords=["efficacy", "clinical benefit", "improved", "successful"],
        publication_count=25,
    )
    result = OutcomeAgent._dossier_publication_override(d, "Unknown")
    assert result is None, f"weak efficacy keywords alone must not override, got {result}"
    print("  ✓ many pubs + weak efficacy keywords → no flip")


def test_override_fires_with_strong_signals_and_multiple_pubs():
    """≥2 trial-specific pubs + strong efficacy → Positive (legitimate promotion)."""
    d = _base_dossier(
        registry_status="COMPLETED",
        trial_specific_count=3,
        efficacy_keywords=["primary endpoint met", "statistically significant"],
        publication_count=5,
    )
    result = OutcomeAgent._dossier_publication_override(d, "Unknown")
    assert result == "Positive", f"expected Positive, got {result}"
    print("  ✓ 3 pubs + primary endpoint met → Positive (legitimate flip preserved)")


def test_override_does_not_fire_on_single_pub_even_with_strong_signal():
    """≥2 trial-specific pubs required — single-pub cases stay Unknown."""
    d = _base_dossier(
        registry_status="COMPLETED",
        trial_specific_count=1,
        efficacy_keywords=["primary endpoint met"],
        publication_count=1,
    )
    result = OutcomeAgent._dossier_publication_override(d, "Unknown")
    assert result is None, f"singleton pub must not override even with strong signal, got {result}"
    print("  ✓ 1 pub + strong efficacy → no flip (≥2 pub floor respected)")


def test_stale_anr_respects_llm_unknown_without_strong_signal():
    """NCT04590872-style stale ANR: LLM said Unknown; weak evidence must NOT flip."""
    d = _base_dossier(
        registry_status="ACTIVE_NOT_RECRUITING",
        days_since_completion=689,
        stale_status=True,
        trial_specific_count=1,
        efficacy_keywords=["efficacy", "clinical activity"],
    )
    # current_value = "Active, not recruiting" — the LLM's call on stale ANR
    result = OutcomeAgent._dossier_publication_override(d, "Active, not recruiting")
    assert result is None, f"stale ANR with weak signal must not be promoted, got {result}"
    print("  ✓ stale ANR + weak evidence → respect LLM's judgment (no flip)")


def test_stale_anr_with_strong_efficacy_still_flips():
    """Stale ANR + strong efficacy → Positive (real positive trial just didn't update)."""
    d = _base_dossier(
        registry_status="ACTIVE_NOT_RECRUITING",
        days_since_completion=689,
        stale_status=True,
        trial_specific_count=3,
        efficacy_keywords=["primary endpoint met", "approved"],
    )
    result = OutcomeAgent._dossier_publication_override(d, "Active, not recruiting")
    assert result == "Positive", f"stale ANR + strong efficacy → Positive, got {result}"
    print("  ✓ stale ANR + strong efficacy → Positive (legitimate flip preserved)")


def test_hasresults_override_unchanged():
    """Structural hasResults=True signal is unchanged behavior."""
    d = _base_dossier(
        registry_status="COMPLETED",
        has_results=True,
        trial_specific_count=0,
        efficacy_keywords=[],
    )
    result = OutcomeAgent._dossier_publication_override(d, "Unknown")
    assert result == "Positive", f"hasResults=True → Positive, got {result}"
    print("  ✓ COMPLETED + hasResults=True → Positive (structural signal preserved)")


def test_negative_signals_still_override():
    """Strong adverse signals still flip to Failed (unchanged)."""
    d = _base_dossier(
        registry_status="COMPLETED",
        trial_specific_count=2,
        negative_keywords=["serious adverse event", "dose-limiting"],
        efficacy_keywords=["primary endpoint met"],  # even with efficacy, strong adverse wins
    )
    result = OutcomeAgent._dossier_publication_override(d, "Unknown")
    assert result == "Failed - completed trial", f"strong adverse must dominate, got {result}"
    print("  ✓ strong adverse signals → Failed (unchanged)")


def test_skip_verification_gate_mentions_strong_efficacy():
    """Verify the skip_verification code path also uses the strong-efficacy gate."""
    src = (PKG_ROOT / "agents" / "annotation" / "outcome.py").read_text()
    assert "_has_strong_efficacy" in src, "helper must exist"
    assert "v42.6.11 publication-anchored Positive (STRONG efficacy)" in src, \
        "skip_verification log message must reflect the narrowing"
    print("  ✓ skip_verification gate updated to strong-efficacy (source inspection)")


def test_prompt_rule3_tightened():
    """Prompt must mention primary-endpoint-met / p<0.05 / approval / phase advancement."""
    src = (PKG_ROOT / "agents" / "annotation" / "outcome.py").read_text()
    for required in [
        "PRIMARY ENDPOINT was met",
        "p-value < 0.05",
        "Regulatory approval",
        "Over-calling Positive is a more harmful error",
    ]:
        assert required in src, f"prompt missing required phrase: {required}"
    # Old loose language gone
    assert '"Positive" requires EFFICACY evidence from trial-specific publications:' not in src \
           or "clinical benefit demonstrated" not in src.split('"Positive" requires')[-1].split("\n")[1], \
           "old loose rule should be replaced"
    print("  ✓ DOSSIER_PROMPT rule 3 tightened with specific signals and guard-rails")


def main() -> int:
    print("v42.6.11 outcome over-call fix tests")
    print("-" * 60)
    tests = [
        test_strong_efficacy_detector_positive_cases,
        test_strong_efficacy_detector_negative_cases,
        test_override_does_not_fire_on_single_pub_weak_signals,
        test_override_does_not_fire_on_many_pubs_weak_signals,
        test_override_fires_with_strong_signals_and_multiple_pubs,
        test_override_does_not_fire_on_single_pub_even_with_strong_signal,
        test_stale_anr_respects_llm_unknown_without_strong_signal,
        test_stale_anr_with_strong_efficacy_still_flips,
        test_hasresults_override_unchanged,
        test_negative_signals_still_override,
        test_skip_verification_gate_mentions_strong_efficacy,
        test_prompt_rule3_tightened,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            print(f"  ✗ {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            import traceback
            print(f"  ✗ {t.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print("-" * 60)
    print(f"{'FAIL' if failed else 'OK'}: {len(tests) - failed}/{len(tests)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

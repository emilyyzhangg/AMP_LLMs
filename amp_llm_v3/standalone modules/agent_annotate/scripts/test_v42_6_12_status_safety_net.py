#!/usr/bin/env python3
"""
Tests for v42.6.12 registry-status safety net (2026-04-24).

Job #80 revealed that v42.6.11's tightened Positive-over-call prompt over-
corrected, producing "Unknown" for 11 of 13 GT="active" (Active, not
recruiting) trials. When CT.gov still reports ACTIVE_NOT_RECRUITING,
staleness alone is not justification to call the trial "Unknown" — GT
annotators use the CT.gov status label.

This module tests:
  - Prompt rule 1 updated to prefer Active over Unknown for stale ANR
  - New post-LLM safety net maps Unknown → canonical status label for
    ACTIVE_NOT_RECRUITING / RECRUITING / NOT_YET_RECRUITING / ENROLLING
  - _infer_from_dossier fallback: ANR always returns Active unless strong
    efficacy signals (no more stale → Unknown silently)
  - Previous gate behavior preserved:
     * Positive with strong efficacy still flips Unknown → Positive
     * hasResults override still wins for COMPLETED
     * Terminated safety net still fires

Pure logic checks — no network, no LLM.
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


def test_infer_fallback_anr_stale_returns_active_not_unknown():
    """Fallback: stale ANR with no strong efficacy → Active, not recruiting (not Unknown)."""
    d = _base_dossier(
        registry_status="ACTIVE_NOT_RECRUITING",
        stale_status=True,
        days_since_completion=689,
        efficacy_keywords=["efficacy", "clinical benefit"],  # weak
    )
    assert OutcomeAgent._infer_from_dossier(d) == "Active, not recruiting"
    print("  ✓ infer fallback: stale ANR + weak efficacy → Active, not recruiting")


def test_infer_fallback_anr_with_strong_efficacy_promotes_to_positive():
    """Fallback: ANR + STRONG efficacy (primary endpoint met) → Positive."""
    d = _base_dossier(
        registry_status="ACTIVE_NOT_RECRUITING",
        stale_status=True,
        days_since_completion=800,
        efficacy_keywords=["primary endpoint met", "statistically significant"],
    )
    assert OutcomeAgent._infer_from_dossier(d) == "Positive"
    print("  ✓ infer fallback: ANR + strong efficacy → Positive (preserved)")


def test_infer_fallback_terminated_unchanged():
    d = _base_dossier(registry_status="TERMINATED")
    assert OutcomeAgent._infer_from_dossier(d) == "Terminated"
    print("  ✓ infer fallback: TERMINATED → Terminated (unchanged)")


def test_infer_fallback_completed_with_results_positive():
    d = _base_dossier(registry_status="COMPLETED", has_results=True)
    assert OutcomeAgent._infer_from_dossier(d) == "Positive"
    print("  ✓ infer fallback: COMPLETED + hasResults → Positive (unchanged)")


def test_prompt_rule1_prefers_active_over_unknown_for_anr():
    """Prompt must no longer say stale ANR → Unknown."""
    src = (PKG_ROOT / "agents" / "annotation" / "outcome.py").read_text()
    # New wording must exist
    assert "CT.gov status is ACTIVE_NOT_RECRUITING → \"Active, not recruiting\" (default)" in src \
        or "ACTIVE_NOT_RECRUITING → \"Active, not recruiting\"" in src, \
        "prompt rule 1 must default ANR to Active"
    # Old wording must be gone
    assert "stale (>6 months past), publications are inconclusive" not in src, \
        "old stale-ANR-to-Unknown rule still present"
    print("  ✓ DOSSIER_PROMPT rule 1 updated — stale ANR defaults to Active")


def test_safety_net_source_present():
    """Post-LLM safety net mapping Unknown → canonical status must be wired."""
    src = (PKG_ROOT / "app" / "services" / "orchestrator.py").read_text()
    # Safety net lives inside outcome.py, not orchestrator — re-target:
    src = (PKG_ROOT / "agents" / "annotation" / "outcome.py").read_text()
    assert "v42.6.12 registry-status safety net" in src, \
        "v42.6.12 safety net comment missing"
    assert "_STATUS_TO_CANONICAL_OUTCOME" in src, "status-to-outcome map missing"
    # Map must contain ANR, RECRUITING, NOT_YET_RECRUITING, ENROLLING
    for key in ("ACTIVE_NOT_RECRUITING", "RECRUITING", "NOT_YET_RECRUITING", "ENROLLING_BY_INVITATION"):
        assert key in src, f"status map missing entry: {key}"
    print("  ✓ post-LLM safety net wired with all ongoing-trial statuses")


def test_previous_gates_unchanged():
    """Make sure the v42.6.11 strong-efficacy gates still work."""
    # Override fires on ≥2 pubs + strong efficacy → Positive
    d = _base_dossier(
        registry_status="COMPLETED",
        trial_specific_count=3,
        efficacy_keywords=["primary endpoint met"],
    )
    assert OutcomeAgent._dossier_publication_override(d, "Unknown") == "Positive"
    # Override does NOT fire on weak efficacy
    d2 = _base_dossier(
        registry_status="COMPLETED",
        trial_specific_count=5,
        efficacy_keywords=["efficacy", "clinical benefit"],
    )
    assert OutcomeAgent._dossier_publication_override(d2, "Unknown") is None
    # Strong adverse still flips to Failed
    d3 = _base_dossier(
        registry_status="COMPLETED",
        trial_specific_count=2,
        negative_keywords=["dose-limiting", "serious adverse event"],
        efficacy_keywords=["primary endpoint met"],
    )
    assert OutcomeAgent._dossier_publication_override(d3, "Unknown") == "Failed - completed trial"
    print("  ✓ v42.6.11 strong-efficacy gate + adverse-signal override preserved")


def main() -> int:
    print("v42.6.12 status safety net tests")
    print("-" * 60)
    tests = [
        test_infer_fallback_anr_stale_returns_active_not_unknown,
        test_infer_fallback_anr_with_strong_efficacy_promotes_to_positive,
        test_infer_fallback_terminated_unchanged,
        test_infer_fallback_completed_with_results_positive,
        test_prompt_rule1_prefers_active_over_unknown_for_anr,
        test_safety_net_source_present,
        test_previous_gates_unchanged,
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

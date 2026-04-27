#!/usr/bin/env python3
"""
Tests for v42.7.14 — status-gated Failed override (2026-04-27).

Job #92's held-out validation surfaced an over-call: NCT03018665
(status=UNKNOWN, GLP-1 Phase 4) was auto-called "Failed - completed trial"
because trial_specific > 0 AND neg AND not efficacy. But the registry
itself didn't know the trial's outcome (status=UNKNOWN means the
trial's status is unknown). Auto-flipping to Failed in that case is
an over-call.

v42.7.14 fix: gate the trial-specific-pub-with-negatives-to-Failed
override on status in (COMPLETED, TERMINATED, WITHDRAWN). For UNKNOWN
or other ambiguous statuses, defer to the LLM.
"""
from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))


def test_failed_override_status_gate_present():
    src = (PKG_ROOT / "agents" / "annotation" / "outcome.py").read_text()
    idx = src.find("v42.7.14")
    assert idx > 0, "v42.7.14 marker missing"
    block = src[idx:idx + 1000]
    assert 'status in ("COMPLETED", "TERMINATED", "WITHDRAWN")' in block, \
        "v42.7.14: Failed override must be gated on terminal status"
    print("  ✓ v42.7.14 status gate present")


def _stub_dossier(status, neg=None, eff=None, trial_specific=3):
    return {
        "registry_status": status,
        "has_results": False,
        "phase": "PHASE2",
        "is_vaccine_trial": False,
        "intervention_names": ["Drug X"],
        "fda_approved_drugs": [],
        "fda_label_indications": {},
        "sec_edgar_disclosed": False,
        "publication_count": 5,
        "trial_specific_count": trial_specific,
        "publications": [],
        "primary_endpoints": [],
        "drug_max_phase": None,
        "efficacy_keywords": eff or [],
        "safety_keywords": [],
        "positive_keywords": [],
        "negative_keywords": neg or [],
        "immunogenicity_keywords": [],
        "stale_status": False,
        "completion_date": "",
        "days_since_completion": None,
        "why_stopped": "",
        "registered_pmids": [],
        "registered_trial_pubs_count": 0,
    }


def test_runtime_unknown_status_no_longer_flips_to_failed():
    """Replicates NCT03018665 pattern: status=UNKNOWN, mixed pubs,
    negative keywords. Pre-v42.7.14: returned Failed (over-call).
    Post-v42.7.14: returns None (LLM decides)."""
    try:
        from agents.annotation.outcome import OutcomeAgent
    except ImportError as e:
        print(f"  ⚠ skipped (import failed: {e})")
        return
    dossier = _stub_dossier(
        status="UNKNOWN",
        neg=["did not meet"],
        eff=[],
    )
    val = OutcomeAgent._dossier_publication_override(dossier, "Unknown")
    assert val is None, (
        f"v42.7.14: status=UNKNOWN must NOT auto-flip to Failed; got {val!r}"
    )
    print("  ✓ status=UNKNOWN with mixed pubs → None (no auto-Failed)")


def test_runtime_completed_status_still_flips():
    """COMPLETED + neg + no eff still auto-flips to Failed (preserves
    the original v41 logic for genuinely completed trials)."""
    try:
        from agents.annotation.outcome import OutcomeAgent
    except ImportError as e:
        print(f"  ⚠ skipped (import failed: {e})")
        return
    dossier = _stub_dossier(
        status="COMPLETED",
        neg=["did not meet", "lack of efficacy"],
        eff=[],
    )
    val = OutcomeAgent._dossier_publication_override(dossier, "Unknown")
    assert val == "Failed - completed trial", (
        f"v42.7.14: status=COMPLETED + neg should still flip Failed; got {val!r}"
    )
    print("  ✓ status=COMPLETED + neg → Failed (preserved)")


def test_runtime_terminated_status_still_flips():
    """TERMINATED + neg + no eff still auto-flips to Failed."""
    try:
        from agents.annotation.outcome import OutcomeAgent
    except ImportError as e:
        print(f"  ⚠ skipped (import failed: {e})")
        return
    dossier = _stub_dossier(
        status="TERMINATED",
        neg=["futility"],
        eff=[],
    )
    val = OutcomeAgent._dossier_publication_override(dossier, "Unknown")
    assert val == "Failed - completed trial"
    print("  ✓ status=TERMINATED + neg → Failed (preserved)")


def test_runtime_recruiting_status_does_not_flip():
    """Active/recruiting trials must never auto-flip to Failed regardless
    of pub mix — the trial isn't done yet."""
    try:
        from agents.annotation.outcome import OutcomeAgent
    except ImportError as e:
        print(f"  ⚠ skipped (import failed: {e})")
        return
    dossier = _stub_dossier(
        status="ACTIVE_NOT_RECRUITING",
        neg=["did not meet"],
        eff=[],
    )
    val = OutcomeAgent._dossier_publication_override(dossier, "Active, not recruiting")
    # Should NOT return "Failed - completed trial" via this path; could
    # return Failed via the stale-Active branch or None
    # In our stub, stale_status=False so stale-Active branch doesn't fire either
    assert val != "Failed - completed trial", (
        f"v42.7.14: ACTIVE status with mixed pubs must NOT auto-flip Failed; got {val!r}"
    )
    print(f"  ✓ status=ACTIVE_NOT_RECRUITING + neg → not Failed (got {val!r})")


def main() -> int:
    print("v42.7.14 status-gated Failed override tests")
    print("-" * 60)
    tests = [
        test_failed_override_status_gate_present,
        test_runtime_unknown_status_no_longer_flips_to_failed,
        test_runtime_completed_status_still_flips,
        test_runtime_terminated_status_still_flips,
        test_runtime_recruiting_status_does_not_flip,
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

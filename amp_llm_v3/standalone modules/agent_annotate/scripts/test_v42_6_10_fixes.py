#!/usr/bin/env python3
"""
Tests for v42.6.10 fixes (2026-04-23, Job #78 recovery).

Fix 1: Narrowed peptide=False cascade. Previously zeroed every field;
       now only cascades sequence + classification.

Fix 2: Restored ANR Active guard for past-completion ANR trials with no
       publications, after v41b's removal swung too far.

Both tests are pure logic checks — no network, no LLM.

Usage:
    cd <agent_annotate_dir>
    python3 scripts/test_v42_6_10_fixes.py
"""

from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))


def test_anr_guard_no_pubs_past_completion():
    """ANR + past completion + no pubs + not stale → Active, not recruiting."""
    from agents.annotation.outcome import _dossier_deterministic

    dossier = {
        "registry_status": "ACTIVE_NOT_RECRUITING",
        "has_results": False,
        "phase": "PHASE2",
        "primary_endpoints": [],
        "days_since_completion": 120,      # past but not stale
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
        "completion_date": "2025-12-24",
    }
    result = _dossier_deterministic(dossier)
    assert result is not None, "ANR guard must fire when no pubs + not stale"
    assert result.value == "Active, not recruiting", f"got {result.value}"
    assert "ANR guard" in result.reasoning
    print("  ✓ ANR no-pubs past-completion → Active, not recruiting")


def test_anr_guard_does_not_fire_when_has_publications():
    """ANR + past completion + trial_specific pubs → fall through to LLM."""
    from agents.annotation.outcome import _dossier_deterministic

    dossier = {
        "registry_status": "ACTIVE_NOT_RECRUITING",
        "has_results": False,
        "phase": "PHASE2",
        "primary_endpoints": [],
        "days_since_completion": 120,
        "why_stopped": "",
        "stale_status": False,
        "trial_specific_count": 2,         # has pubs → must not short-circuit
        "publication_count": 3,
        "publications": [],
        "positive_keywords": [],
        "negative_keywords": [],
        "efficacy_keywords": [],
        "safety_keywords": [],
        "drug_max_phase": None,
        "completion_date": "2025-12-24",
    }
    result = _dossier_deterministic(dossier)
    assert result is None, f"expected fallthrough with pubs, got {result.value if result else None}"
    print("  ✓ ANR with publications → falls through (LLM decides)")


def test_anr_guard_does_not_fire_when_stale():
    """ANR + stale (>180 days past completion) → fall through, don't force Active."""
    from agents.annotation.outcome import _dossier_deterministic

    dossier = {
        "registry_status": "ACTIVE_NOT_RECRUITING",
        "has_results": False,
        "phase": "PHASE2",
        "primary_endpoints": [],
        "days_since_completion": 400,      # stale
        "why_stopped": "",
        "stale_status": True,
        "trial_specific_count": 0,
        "publication_count": 0,
        "publications": [],
        "positive_keywords": [],
        "negative_keywords": [],
        "efficacy_keywords": [],
        "safety_keywords": [],
        "drug_max_phase": None,
        "completion_date": "2024-11-15",
    }
    result = _dossier_deterministic(dossier)
    assert result is None, f"expected fallthrough when stale, got {result.value if result else None}"
    print("  ✓ ANR stale → falls through (no false Active call)")


def test_anr_guard_future_completion_unchanged():
    """Future completion still fires the original v41 guard."""
    from agents.annotation.outcome import _dossier_deterministic

    dossier = {
        "registry_status": "ACTIVE_NOT_RECRUITING",
        "has_results": False,
        "phase": "PHASE2",
        "primary_endpoints": [],
        "days_since_completion": -30,       # future
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
        "completion_date": "2026-05-23",
    }
    result = _dossier_deterministic(dossier)
    assert result is not None, "v41 future-completion guard must fire"
    assert result.value == "Active, not recruiting"
    assert "v41 Active guard" in result.reasoning
    print("  ✓ ANR future completion → v41 guard still fires")


def test_cascade_narrowed_to_sequence_and_classification():
    """Source inspection: peptide=False cascade must NOT enumerate ANNOTATION_AGENTS
    to zero every field."""
    import re
    orch_path = PKG_ROOT / "app" / "services" / "orchestrator.py"
    src = orch_path.read_text()

    # New cascade block keywords
    assert "[Peptide=False cascade: sequence is peptide-specific]" in src, \
        "missing narrowed sequence cascade reasoning"
    assert "[Peptide=False cascade: non-peptide → classification=Other" in src, \
        "missing narrowed classification cascade reasoning"

    # Old broad cascade must be gone
    assert "[Peptide=False: non-peptide trial, all fields N/A]" not in src, \
        "old broad cascade reasoning still present"
    assert "N/A-ing all other fields" not in src, "old cascade log message still present"

    # Step 2 must filter out already-filled fields
    assert "already_filled = {a.field_name for a in annotations}" in src, \
        "step2_fields must skip already-cascaded fields"

    print("  ✓ cascade block narrowed to sequence+classification; step 2 skips already-filled")


def main() -> int:
    print("v42.6.10 fix tests")
    print("-" * 60)
    tests = [
        test_anr_guard_no_pubs_past_completion,
        test_anr_guard_does_not_fire_when_has_publications,
        test_anr_guard_does_not_fire_when_stale,
        test_anr_guard_future_completion_unchanged,
        test_cascade_narrowed_to_sequence_and_classification,
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

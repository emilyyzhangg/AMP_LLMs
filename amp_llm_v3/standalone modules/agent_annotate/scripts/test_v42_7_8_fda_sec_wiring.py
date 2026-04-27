#!/usr/bin/env python3
"""
Tests for v42.7.8 FDA Drugs + SEC EDGAR → outcome dossier wiring (2026-04-27).

v42.7.0 added the SEC EDGAR + FDA Drugs research agents but the outcome
dossier never consumed their structured signals. The
fda_drugs_<intervention>_approved boolean is the strongest possible
Positive signal (regulator already approved the drug); SEC EDGAR
citation presence is informative context for the LLM.

This change extracts both into the dossier, surfaces them in the
LLM-visible formatted text, and adds a tightly bounded
FDA-approved-drug Positive override.
"""
from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

OUTCOME_PATH = PKG_ROOT / "agents" / "annotation" / "outcome.py"


def test_dossier_fields_added():
    src = OUTCOME_PATH.read_text()
    assert '"fda_approved_drugs": []' in src
    assert '"sec_edgar_disclosed": False' in src
    print("  ✓ dossier extended: fda_approved_drugs + sec_edgar_disclosed")


def test_fda_drugs_extraction_branch_present():
    src = OUTCOME_PATH.read_text()
    assert 'result.agent_name == "fda_drugs"' in src
    # Must scan raw_data for *_approved flags
    assert "_approved" in src and 'k.endswith("_approved")' in src
    print("  ✓ FDA Drugs raw_data extraction branch present")


def test_sec_edgar_extraction_branch_present():
    src = OUTCOME_PATH.read_text()
    assert 'result.agent_name == "sec_edgar"' in src
    assert 'sec_edgar_disclosed' in src
    print("  ✓ SEC EDGAR citation-presence extraction branch present")


def test_fda_approved_override_present_and_gated():
    src = OUTCOME_PATH.read_text()
    # Find the FDA-approved override block
    idx = src.find("FDA-approved drug override")
    assert idx > 0, "FDA-approved override comment marker missing"
    block = src[idx:idx + 1000]
    # Must require fda_approved_drugs non-empty
    assert 'dossier.get("fda_approved_drugs")' in block
    # Must NOT fire if there are negative signals
    assert "and not neg" in block
    # Must NOT re-flip an already-set Positive/Failed value
    assert 'current_value not in' in block
    assert 'return "Positive"' in block
    print("  ✓ FDA-approved override gated on (fda_approved_drugs AND no neg AND not already-set)")


def test_dossier_formatter_surfaces_fda_and_sec():
    src = OUTCOME_PATH.read_text()
    assert "FDA Approved (structured Drugs@FDA)" in src
    assert "SEC EDGAR" in src and "sponsor 10-K/10-Q/8-K filing" in src
    print("  ✓ _format_dossier_for_llm surfaces FDA Approved + SEC EDGAR")


def test_runtime_fda_approved_drug_returns_positive():
    """Stub a dossier with an FDA-approved drug and confirm override fires."""
    try:
        from agents.annotation.outcome import OutcomeAgent
    except ImportError as e:
        print(f"  ⚠ skipped (import failed: {e})")
        return
    dossier = {
        "registry_status": "COMPLETED",
        "has_results": False,
        "phase": "PHASE3",
        "is_vaccine_trial": False,
        "intervention_names": ["Enfuvirtide"],
        "fda_approved_drugs": ["enfuvirtide"],   # the v42.7.0 plumbing flag
        "sec_edgar_disclosed": True,
        "publication_count": 5,
        "trial_specific_count": 3,
        "publications": [],
        "primary_endpoints": [],
        "drug_max_phase": 4,
        "efficacy_keywords": [],
        "safety_keywords": [],
        "positive_keywords": [],
        "negative_keywords": [],
        "immunogenicity_keywords": [],
        "stale_status": False,
        "completion_date": "2003-06-01",
        "days_since_completion": 8000,
        "why_stopped": "",
    }
    val = OutcomeAgent._dossier_publication_override(dossier, "Unknown")
    assert val == "Positive", f"FDA-approved override → expected Positive, got {val!r}"
    print("  ✓ FDA-approved drug + Unknown LLM call → Positive override")


def test_runtime_fda_approved_with_negatives_returns_failed():
    """Edge case: drug is approved BUT publications report adverse signals
    (e.g. trial was terminated for safety despite drug eventually being
    approved on different basis). The negative-signal branch must dominate."""
    try:
        from agents.annotation.outcome import OutcomeAgent
    except ImportError as e:
        print(f"  ⚠ skipped (import failed: {e})")
        return
    dossier = {
        "registry_status": "TERMINATED",
        "has_results": False,
        "phase": "PHASE2",
        "is_vaccine_trial": False,
        "intervention_names": ["Some-drug"],
        "fda_approved_drugs": ["some-drug"],
        "sec_edgar_disclosed": False,
        "publication_count": 3,
        "trial_specific_count": 2,
        "publications": [],
        "primary_endpoints": [],
        "drug_max_phase": None,
        "efficacy_keywords": [],
        "safety_keywords": [],
        "positive_keywords": [],
        # Strong adverse — must dominate
        "negative_keywords": ["serious adverse event"],
        "immunogenicity_keywords": [],
        "stale_status": False,
        "completion_date": "",
        "days_since_completion": None,
        "why_stopped": "",
    }
    val = OutcomeAgent._dossier_publication_override(dossier, "Unknown")
    assert val == "Failed - completed trial", (
        f"adverse signals must dominate FDA-approved override; got {val!r}"
    )
    print("  ✓ FDA-approved + adverse signals → Failed (negatives dominate)")


def test_runtime_no_fda_signal_returns_unchanged():
    """Sanity: dossier with no FDA approval signal is unchanged."""
    try:
        from agents.annotation.outcome import OutcomeAgent
    except ImportError as e:
        print(f"  ⚠ skipped (import failed: {e})")
        return
    dossier = {
        "registry_status": "ACTIVE_NOT_RECRUITING",
        "has_results": False,
        "phase": "PHASE2",
        "is_vaccine_trial": False,
        "intervention_names": ["Some-experimental-drug"],
        "fda_approved_drugs": [],   # not approved
        "sec_edgar_disclosed": False,
        "publication_count": 1,
        "trial_specific_count": 0,
        "publications": [],
        "primary_endpoints": [],
        "drug_max_phase": None,
        "efficacy_keywords": [],
        "safety_keywords": [],
        "positive_keywords": [],
        "negative_keywords": [],
        "immunogenicity_keywords": [],
        "stale_status": False,
        "completion_date": "",
        "days_since_completion": None,
        "why_stopped": "",
    }
    val = OutcomeAgent._dossier_publication_override(dossier, "Unknown")
    # No override fires — should return None.
    assert val is None, f"no FDA signal should return None; got {val!r}"
    print("  ✓ no FDA signal → None (unchanged)")


def main() -> int:
    print("v42.7.8 FDA Drugs + SEC EDGAR outcome wiring tests")
    print("-" * 60)
    tests = [
        test_dossier_fields_added,
        test_fda_drugs_extraction_branch_present,
        test_sec_edgar_extraction_branch_present,
        test_fda_approved_override_present_and_gated,
        test_dossier_formatter_surfaces_fda_and_sec,
        test_runtime_fda_approved_drug_returns_positive,
        test_runtime_fda_approved_with_negatives_returns_failed,
        test_runtime_no_fda_signal_returns_unchanged,
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

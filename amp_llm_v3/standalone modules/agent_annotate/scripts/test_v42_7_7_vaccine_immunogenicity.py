#!/usr/bin/env python3
"""
Tests for v42.7.7 vaccine-immunogenicity Positive override (2026-04-27).

Job #83 confusion matrix showed Positive recall 6/13 = 46%, with most of
the 7 under-calls being vaccine / immunotherapy trials whose pubs reported
immunogenicity outcomes (induces immune response, T-cell response,
antibody titers) but didn't say "primary endpoint met" verbatim.

For Phase I vaccine/immunotherapy trials, immunogenicity IS the primary
endpoint by design — clinical efficacy is a Phase II/III question.

This change tightens the gate (only fires for vaccine_trial=True) so it
cannot recreate the v41-era over-calling that v42.6.11 fixed.

Source-only checks runnable without httpx/pydantic.
"""
from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

OUTCOME_PATH = PKG_ROOT / "agents" / "annotation" / "outcome.py"


def test_vaccine_dossier_fields_added():
    src = OUTCOME_PATH.read_text()
    assert '"is_vaccine_trial": False' in src, "is_vaccine_trial field missing from dossier"
    assert '"intervention_names"' in src, "intervention_names field missing"
    assert '"immunogenicity_keywords"' in src, "immunogenicity_keywords field missing"
    print("  ✓ dossier extended: is_vaccine_trial + intervention_names + immunogenicity_keywords")


def test_vaccine_name_tokens_present():
    src = OUTCOME_PATH.read_text()
    assert "_VACCINE_NAME_TOKENS" in src
    # Cover the standard variants (US/UK spellings, immunotherapy)
    for tok in ("vaccine", "vaccination", "immunotherapy", "immunisation", "immunization"):
        assert f'"{tok}"' in src, f"_VACCINE_NAME_TOKENS missing {tok!r}"
    print("  ✓ _VACCINE_NAME_TOKENS covers vaccine/vaccination/immunotherapy + UK spellings")


def test_immunogenicity_keywords_set_present():
    src = OUTCOME_PATH.read_text()
    assert "_IMMUNOGENICITY_KW = [" in src
    # Core variants observed in Job #83 under-calls
    must_have = [
        "induces immune response",
        "antibody response",
        "antibody titer",
        "t cell response",
        "seroconversion",
        "long-lasting immune",
    ]
    for kw in must_have:
        assert f'"{kw}' in src, f"_IMMUNOGENICITY_KW missing {kw!r}"
    print(f"  ✓ _IMMUNOGENICITY_KW includes {len(must_have)} core variants")


def test_intervention_extraction_uses_arms_module():
    """Source check: extraction reads from armsInterventionsModule.interventions[].name
    AND the briefTitle (some trials underspecify interventions but title says vaccine)."""
    src = OUTCOME_PATH.read_text()
    assert 'ai_module = proto.get("armsInterventionsModule"' in src
    assert 'identificationModule' in src and 'briefTitle' in src
    print("  ✓ vaccine detection uses both interventions[].name AND briefTitle")


def test_vaccine_immunogenicity_override_present_and_gated():
    """The override branch must:
      (a) gate on is_vaccine_trial (otherwise it would over-call)
      (b) require ≥2 trial-specific publications
      (c) require at least one immunogenicity keyword
      (d) require zero negative keywords"""
    src = OUTCOME_PATH.read_text()
    # The whole conjunction should be in one if-block
    assert 'dossier.get("is_vaccine_trial")' in src
    assert 'dossier.get("immunogenicity_keywords")' in src
    # Find the override block
    idx = src.find("vaccine-immunogenicity gate")
    assert idx > 0, "override comment marker missing"
    block = src[idx:idx + 1200]
    assert 'trial_specific >= 2' in block, "override must require ≥2 trial-specific pubs"
    assert 'and not neg' in block, "override must require zero negative signals"
    assert 'return "Positive"' in block
    print("  ✓ override gated on (is_vaccine_trial AND ≥2 trial-specific AND immunogenicity AND no negatives)")


def test_prompt_rule_7_has_vaccine_exception():
    src = OUTCOME_PATH.read_text()
    # Find Rule 7
    idx = src.find("7. Phase I:")
    assert idx > 0, "Rule 7 not found in DOSSIER_PROMPT"
    # Window enlarged in v42.7.17 — Rule 7 grew with the alternative
    # trial-title-pattern criterion.
    rule7 = src[idx:idx + 2200]
    assert "EXCEPTION" in rule7, "Rule 7 must include the vaccine EXCEPTION"
    assert "vaccine" in rule7.lower() or "immunotherapy" in rule7.lower()
    assert "immunogenicity" in rule7.lower()
    assert "primary-endpoint-met" in rule7.lower() or "primary endpoint" in rule7.lower()
    print("  ✓ DOSSIER_PROMPT Rule 7 has vaccine/immunotherapy exception")


def test_dossier_formatter_surfaces_vaccine_signals():
    """LLM must see is_vaccine_trial + immunogenicity_keywords or it can't
    apply Rule 7's exception."""
    src = OUTCOME_PATH.read_text()
    assert "Trial Type: VACCINE" in src, "vaccine trial flag not surfaced in formatted dossier"
    assert "Immunogenicity Signals" in src, "immunogenicity signals not surfaced in formatted dossier"
    print("  ✓ _format_dossier_for_llm surfaces Trial Type + Immunogenicity Signals")


def test_runtime_vaccine_trial_with_immunogenicity_returns_positive():
    """End-to-end-ish: build a stub dossier matching the Job #83 NCT03199872
    pattern (RhoC vaccine, COMPLETED, multiple pubs, immune-response language)
    and confirm the override returns Positive.

    v42.7.12 update: NCT03199872 has 1 CT.gov-registered PMID (33184050),
    so the v42.7.12 tightening still allows this override to fire.
    """
    try:
        from agents.annotation.outcome import OutcomeAgent
    except ImportError as e:
        print(f"  ⚠ skipped (import failed: {e})")
        return
    dossier = {
        "registry_status": "COMPLETED",
        "has_results": False,
        "phase": "PHASE1",
        "is_vaccine_trial": True,
        "intervention_names": ["RhoC peptide vaccine"],
        "publication_count": 5,
        "trial_specific_count": 3,
        "publications": [],
        "primary_endpoints": [],
        "drug_max_phase": None,
        "efficacy_keywords": [],
        "safety_keywords": [],
        "positive_keywords": [],
        "negative_keywords": [],
        "immunogenicity_keywords": ["induces long-lasting immune"],
        "stale_status": False,
        "completion_date": "2023-06-01",
        "days_since_completion": 700,
        "why_stopped": "",
        # v42.7.12 fields — NCT03199872 has 1 registered PMID
        "registered_pmids": ["33184050"],
        "registered_trial_pubs_count": 1,
        "fda_approved_drugs": [],
        "fda_label_indications": {},
        "sec_edgar_disclosed": False,
    }
    val = OutcomeAgent._dossier_publication_override(dossier, "Unknown")
    assert val == "Positive", f"vaccine + immuno → expected Positive, got {val!r}"
    print("  ✓ stub vaccine+immunogenicity override returns Positive")


def test_runtime_non_vaccine_immunogenicity_returns_none():
    """Sanity: a non-vaccine trial with immunogenicity language should NOT
    flip to Positive (over-call protection — was the v41 era bug)."""
    try:
        from agents.annotation.outcome import OutcomeAgent
    except ImportError as e:
        print(f"  ⚠ skipped (import failed: {e})")
        return
    dossier = {
        "registry_status": "COMPLETED",
        "has_results": False,
        "phase": "PHASE1",
        "is_vaccine_trial": False,  # NOT a vaccine
        "intervention_names": ["small-molecule kinase inhibitor"],
        "publication_count": 5,
        "trial_specific_count": 3,
        "publications": [],
        "primary_endpoints": [],
        "drug_max_phase": None,
        "efficacy_keywords": [],
        "safety_keywords": [],
        "positive_keywords": [],
        "negative_keywords": [],
        # Immunogenicity language present but irrelevant for non-vaccine
        "immunogenicity_keywords": ["induces immune response"],
        "stale_status": False,
        "completion_date": "",
        "days_since_completion": None,
        "why_stopped": "",
    }
    val = OutcomeAgent._dossier_publication_override(dossier, "Unknown")
    # No COMPLETED+hasResults override fires, no strong-efficacy keywords,
    # no negative signals — should be None (let LLM decide).
    assert val is None, f"non-vaccine + immuno should NOT flip; got {val!r}"
    print("  ✓ non-vaccine + immunogenicity returns None (no over-call)")


def test_runtime_vaccine_with_negative_signals_returns_none():
    """Sanity: vaccine + immunogenicity but ALSO negative signals — the
    failure signal must dominate."""
    try:
        from agents.annotation.outcome import OutcomeAgent
    except ImportError as e:
        print(f"  ⚠ skipped (import failed: {e})")
        return
    dossier = {
        "registry_status": "COMPLETED",
        "has_results": False,
        "phase": "PHASE2",
        "is_vaccine_trial": True,
        "intervention_names": ["cancer vaccine"],
        "publication_count": 4,
        "trial_specific_count": 2,
        "publications": [],
        "primary_endpoints": [],
        "drug_max_phase": None,
        "efficacy_keywords": [],
        "safety_keywords": [],
        "positive_keywords": [],
        "negative_keywords": ["did not meet"],  # primary endpoint failure
        "immunogenicity_keywords": ["antibody response"],
        "stale_status": False,
        "completion_date": "",
        "days_since_completion": None,
        "why_stopped": "",
    }
    val = OutcomeAgent._dossier_publication_override(dossier, "Unknown")
    # Should fall through to the trial_specific>0 + neg + no efficacy branch
    # which returns "Failed - completed trial".
    assert val == "Failed - completed trial", (
        f"vaccine + immuno + negative signals should still fail; got {val!r}"
    )
    print("  ✓ vaccine + immuno + negative → Failed (negatives dominate)")


def main() -> int:
    print("v42.7.7 vaccine-immunogenicity Positive override tests")
    print("-" * 60)
    tests = [
        test_vaccine_dossier_fields_added,
        test_vaccine_name_tokens_present,
        test_immunogenicity_keywords_set_present,
        test_intervention_extraction_uses_arms_module,
        test_vaccine_immunogenicity_override_present_and_gated,
        test_prompt_rule_7_has_vaccine_exception,
        test_dossier_formatter_surfaces_vaccine_signals,
        test_runtime_vaccine_trial_with_immunogenicity_returns_positive,
        test_runtime_non_vaccine_immunogenicity_returns_none,
        test_runtime_vaccine_with_negative_signals_returns_none,
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

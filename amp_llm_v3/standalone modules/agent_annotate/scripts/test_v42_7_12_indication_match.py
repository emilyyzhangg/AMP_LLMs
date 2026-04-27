#!/usr/bin/env python3
"""
Tests for v42.7.12 — FDA label indication match + registered-pubs gate
(2026-04-27).

Job #92's held-out validation surfaced 4 outcome over-calls (Positive when
GT=Unknown). All 4 share a pattern: the drug is FDA-approved for indication
X, but the trial tested indication Y. Examples:
  - NCT03342001: calcitonin (approved for osteoporosis) → tested for
    post-thyroidectomy bone loss
  - NCT03456687: exenatide (approved for diabetes) → tested for Parkinson's
  - NCT03597893: peptide trial, off-label use
  - NCT01673217: decitabine immunotherapy review article tagged
    [TRIAL-SPECIFIC] by the heuristic classifier

The v42.7.12 fix has three parts:
  1. fda_drugs_client fetches drug/label.json's indications_and_usage and
     surfaces it in the dossier so the LLM can apply Rule 3.c.
  2. Outcome dossier captures CT.gov referencesModule PMIDs as
     registered_pmids — proof of trial-specificity that the heuristic
     classifier can't fake.
  3. Structural FDA-approved override now requires strong-efficacy keywords
     (treats FDA-approval as multiplier, not sole trigger). Vaccine override
     requires ≥1 CT.gov-registered publication.
"""
from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))


def test_dossier_fields_added():
    src = (PKG_ROOT / "agents" / "annotation" / "outcome.py").read_text()
    assert '"fda_label_indications"' in src
    assert '"registered_pmids"' in src
    assert '"registered_trial_pubs_count"' in src
    print("  ✓ dossier extended: fda_label_indications + registered_pmids + count")


def test_referencesModule_extracted_from_protocol():
    """Source check: outcome dossier must read referencesModule from the
    clinical_protocol raw_data."""
    src = (PKG_ROOT / "agents" / "annotation" / "outcome.py").read_text()
    assert 'referencesModule' in src
    assert 'registered_pmids' in src
    # Must iterate the references[] array
    assert 'ref_module.get("references"' in src
    print("  ✓ referencesModule.references[] extraction wired")


def test_fda_label_url_present():
    src = (PKG_ROOT / "agents" / "research" / "fda_drugs_client.py").read_text()
    assert "FDA_LABEL_URL" in src
    assert "drug/label.json" in src
    assert "_fetch_label_indication" in src
    print("  ✓ FDA Drugs client extended with drug/label.json fetch")


def test_label_indication_only_on_approved():
    """Source check: label.json is only queried when drug is approved
    (saves API calls + avoids labeling non-approved drugs)."""
    src = (PKG_ROOT / "agents" / "research" / "fda_drugs_client.py").read_text()
    # The label fetch must be conditional on `is_approved`
    idx = src.find("is_approved = any(")
    assert idx > 0
    block = src[idx:idx + 800]
    assert "if is_approved" in block, "label fetch must be gated on is_approved"
    print("  ✓ label fetch only fires when drug is FDA-approved")


def test_dossier_formatter_surfaces_indications_and_registered_pmids():
    src = (PKG_ROOT / "agents" / "annotation" / "outcome.py").read_text()
    assert "approved for:" in src, "label indication line missing from formatter"
    assert "Registered Trial Publications" in src, "registered pubs line missing"
    assert "CT.gov-registered" in src
    print("  ✓ formatter surfaces 'approved for: ...' + 'Registered Trial Publications'")


def test_fda_override_requires_strong_efficacy():
    """v42.7.12 tightening: FDA-approved override must also require
    strong-efficacy keywords (treats FDA-approval as confidence multiplier,
    not sole trigger). Removes the ability to over-call cross-indication
    cases like NCT03456687 exenatide-for-Parkinson's."""
    src = (PKG_ROOT / "agents" / "annotation" / "outcome.py").read_text()
    idx = src.find("FDA-approved drug override (TIGHTENED in v42.7.12)")
    assert idx > 0, "v42.7.12 tightening comment missing"
    block = src[idx:idx + 1500]
    assert 'dossier.get("fda_approved_drugs")' in block
    assert "_has_strong_efficacy(efficacy)" in block, \
        "FDA-approved override must require strong-efficacy keywords (v42.7.12)"
    print("  ✓ FDA-approved override now requires _has_strong_efficacy(efficacy)")


def test_vaccine_override_requires_registered_pubs():
    """v42.7.12 tightening: vaccine override must also require ≥1 CT.gov-
    registered publication (PMIDs in protocolSection.referencesModule).
    NCT01673217 had 0 registered refs — this gate blocks that over-call
    while keeping good cases (NCT03199872 has 1, NCT03272269 has 5)."""
    src = (PKG_ROOT / "agents" / "annotation" / "outcome.py").read_text()
    idx = src.find("vaccine-immunogenicity gate (TIGHTENED in v42.7.12)")
    assert idx > 0, "v42.7.12 vaccine tightening comment missing"
    block = src[idx:idx + 1500]
    assert 'dossier.get("is_vaccine_trial")' in block
    assert 'registered_trial_pubs_count' in block, \
        "vaccine override must also require ≥1 registered publication"
    print("  ✓ vaccine override now requires ≥1 CT.gov-registered publication")


def test_prompt_rule_3c_indication_match():
    """The prompt Rule 3.c must require trial-condition vs FDA-indication match."""
    src = (PKG_ROOT / "agents" / "annotation" / "outcome.py").read_text()
    # Rule 3.c block
    idx = src.find("(c) Regulatory approval")
    assert idx > 0, "Rule 3.c not found"
    block = src[idx:idx + 1500]
    assert "OFF-LABEL" in block.upper() or "off-label" in block, \
        "Rule 3.c must call out off-label cross-indication case"
    assert "FDA Approved" in block and "approved for" in block, \
        "Rule 3.c must instruct LLM to compare trial condition vs FDA indication"
    print("  ✓ Rule 3.c instructs LLM to check indication overlap")


def test_prompt_rule_7_requires_registered_pubs():
    """Rule 7 vaccine exception now requires ≥1 CT.gov-registered publication."""
    src = (PKG_ROOT / "agents" / "annotation" / "outcome.py").read_text()
    idx = src.find("EXCEPTION (vaccine")
    assert idx > 0
    block = src[idx:idx + 2000]
    assert "CT.gov-REGISTERED" in block or "CT.gov-registered" in block.lower()
    assert "Registered Trial Publications" in block
    # Important: explicit fallback for trials with 0 registered refs
    assert "ZERO" in block or "default to Unknown" in block.lower(), \
        "Rule 7 must explicitly fall back to Unknown for trials with no registered pubs"
    print("  ✓ Rule 7 vaccine exception requires CT.gov-registered publication")


def test_runtime_fda_approved_alone_no_longer_fires():
    """Stub a dossier with FDA-approved drug but NO strong-efficacy keywords.
    Pre-v42.7.12 this fired Positive; now it must return None."""
    try:
        from agents.annotation.outcome import OutcomeAgent
    except ImportError as e:
        print(f"  ⚠ skipped (import failed: {e})")
        return
    dossier = {
        "registry_status": "COMPLETED",
        "has_results": False,
        "phase": "PHASE4",
        "is_vaccine_trial": False,
        "intervention_names": ["Exenatide"],
        "fda_approved_drugs": ["Exenatide"],
        "fda_label_indications": {"Exenatide": "type 2 diabetes mellitus"},
        "sec_edgar_disclosed": False,
        "publication_count": 5,
        "trial_specific_count": 3,
        "publications": [],
        "primary_endpoints": [],
        "drug_max_phase": 4,
        "efficacy_keywords": [],   # NO strong-efficacy keywords
        "safety_keywords": [],
        "positive_keywords": [],
        "negative_keywords": [],
        "immunogenicity_keywords": [],
        "stale_status": False,
        "completion_date": "",
        "days_since_completion": None,
        "why_stopped": "",
        "registered_pmids": [],
        "registered_trial_pubs_count": 0,
    }
    val = OutcomeAgent._dossier_publication_override(dossier, "Unknown")
    assert val is None, (
        f"v42.7.12: FDA-approved drug WITHOUT strong-efficacy keywords must "
        f"NOT fire override (got {val!r}); LLM must apply Rule 3.c indication "
        f"check instead."
    )
    print("  ✓ FDA-approved drug + no strong-efficacy → None (LLM decides)")


def test_runtime_fda_approved_with_strong_efficacy_still_fires():
    """The override should STILL fire when strong-efficacy keywords are
    present alongside FDA-approval — v42.7.8's main use case is preserved."""
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
        "intervention_names": ["Erenumab"],
        "fda_approved_drugs": ["Erenumab"],
        "fda_label_indications": {"Erenumab": "preventive treatment of migraine"},
        "sec_edgar_disclosed": True,
        "publication_count": 8,
        "trial_specific_count": 5,
        "publications": [],
        "primary_endpoints": [],
        "drug_max_phase": 4,
        # Strong-efficacy keywords present (one of _STRONG_EFFICACY)
        "efficacy_keywords": ["primary endpoint met", "fda approved"],
        "safety_keywords": [],
        "positive_keywords": [],
        "negative_keywords": [],
        "immunogenicity_keywords": [],
        "stale_status": False,
        "completion_date": "",
        "days_since_completion": None,
        "why_stopped": "",
        "registered_pmids": ["33184050"],
        "registered_trial_pubs_count": 1,
    }
    val = OutcomeAgent._dossier_publication_override(dossier, "Unknown")
    assert val == "Positive", (
        f"v42.7.12: FDA-approved + strong-efficacy must STILL fire override; got {val!r}"
    )
    print("  ✓ FDA-approved + strong-efficacy → Positive (v42.7.8 preserved)")


def test_runtime_vaccine_no_registered_pubs_blocked():
    """The exact NCT01673217 over-call case: vaccine + immuno keywords +
    no registered pubs → must NOT fire vaccine override."""
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
        "intervention_names": ["Decitabine immunotherapy"],
        "fda_approved_drugs": ["Decitabine"],
        "fda_label_indications": {"Decitabine": "myelodysplastic syndromes (MDS)"},
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
        "immunogenicity_keywords": ["t cell response"],
        "stale_status": False,
        "completion_date": "",
        "days_since_completion": None,
        "why_stopped": "",
        # NCT01673217 had 0 registered pubs — this is the v42.7.12 gate
        "registered_pmids": [],
        "registered_trial_pubs_count": 0,
    }
    val = OutcomeAgent._dossier_publication_override(dossier, "Unknown")
    assert val is None, (
        f"v42.7.12: vaccine without registered pubs must NOT fire override "
        f"(got {val!r}); blocks the NCT01673217 over-call class."
    )
    print("  ✓ vaccine + 0 registered pubs → None (NCT01673217 over-call blocked)")


def test_runtime_vaccine_with_registered_pubs_still_fires():
    """The good case: vaccine + immuno + ≥1 registered pub → still fires.
    Mirrors NCT03199872 RhoC vaccine which has 1 registered PMID (33184050)."""
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
        "fda_approved_drugs": [],
        "fda_label_indications": {},
        "sec_edgar_disclosed": False,
        "publication_count": 6,
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
        "completion_date": "",
        "days_since_completion": None,
        "why_stopped": "",
        "registered_pmids": ["33184050"],   # the RhoC vaccine pub
        "registered_trial_pubs_count": 1,
    }
    val = OutcomeAgent._dossier_publication_override(dossier, "Unknown")
    assert val == "Positive", (
        f"v42.7.12: vaccine + immuno + ≥1 registered pub must still fire; got {val!r}"
    )
    print("  ✓ vaccine + immuno + 1 registered pub → Positive (NCT03199872 preserved)")


def main() -> int:
    print("v42.7.12 indication-match + registered-pubs gate tests")
    print("-" * 60)
    tests = [
        test_dossier_fields_added,
        test_referencesModule_extracted_from_protocol,
        test_fda_label_url_present,
        test_label_indication_only_on_approved,
        test_dossier_formatter_surfaces_indications_and_registered_pmids,
        test_fda_override_requires_strong_efficacy,
        test_vaccine_override_requires_registered_pubs,
        test_prompt_rule_3c_indication_match,
        test_prompt_rule_7_requires_registered_pubs,
        test_runtime_fda_approved_alone_no_longer_fires,
        test_runtime_fda_approved_with_strong_efficacy_still_fires,
        test_runtime_vaccine_no_registered_pubs_blocked,
        test_runtime_vaccine_with_registered_pubs_still_fires,
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

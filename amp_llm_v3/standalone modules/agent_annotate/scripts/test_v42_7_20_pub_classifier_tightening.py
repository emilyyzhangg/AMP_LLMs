#!/usr/bin/env python3
"""Tests for v42.7.20 — _classify_publication tightening.

Cross-job analysis of Jobs #95/#96/#97/#98 showed `positive → unknown`
is the dominant outcome miss class (~9-12 misses per slice). Spot
inspection of misses (NCT01677676 FP-01.1 influenza vaccine, NCT05137314
PLG0206 antibacterial peptide, NCT05898763 TEIPP24 vaccine) revealed:

  - 7-9 publications each, NONE containing the trial's intervention name
    in the title;
  - All titles match _GENERAL field-review patterns (e.g. "Computational
    Approaches and Challenges to Developing Universal Influenza
    Vaccines", "Antibiotics in the clinical pipeline");
  - The current v41b classifier defaults to `trial_specific` when no
    review signal matches, leading the LLM to see many [TRIAL-SPECIFIC]
    tags and discount them all (correctly identifying that the heuristic
    is wrong).

v42.7.20 flips the default: require an EXPLICIT trial-design signal
(NCT match, "phase X", "randomized", "first-in-human", "dose-escalation",
"primary endpoint", etc.) for `trial_specific`. Otherwise default to
`general`. This makes [TRIAL-SPECIFIC] tags reliable so the LLM can
trust them when applying Rule 7 condition (ii).

Risk: if a real trial publication's title lacks any explicit signal
(rare but possible), it gets tagged `general`. We accept this trade-off
because the over-tagging pattern is causing systematic confusion in the
LLM (Job #98 showed 13/20 pos→unk misses where the LLM cited "the
[TRIAL-SPECIFIC] tag is heuristic" as reasoning).

Per memory `feedback_no_cheat_sheets.md`: no drug-name-specific logic.
The fix is a structural change to the default classification rule.
"""
from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))


def test_v42_7_20_marker_present():
    src = (PKG_ROOT / "agents" / "annotation" / "outcome.py").read_text()
    assert "v42.7.20" in src, "v42.7.20 marker missing in outcome.py"
    print("  ✓ v42.7.20 marker present in outcome.py")


def test_classifier_default_flipped_to_general():
    """The classifier must default to `general` when no trial signal
    matches AND no explicit general signal matches. v41b's "default to
    trial_specific" wording must be replaced — over-tagging caused Job
    #98's 13 pos→unk misses."""
    from agents.annotation.outcome import _classify_publication

    # Generic title with NO trial signals → must be general (not trial_specific)
    result = _classify_publication(
        "Computational Approaches and Challenges to Developing Universal Influenza Vaccines",
        "NCT01677676",
    )
    assert result == "general", (
        f"v42.7.20 trip-wire: generic field-review title without explicit "
        f"trial signals must be tagged 'general' (got {result!r}). The "
        f"v41b default-to-trial_specific rule was the over-tagging root "
        f"cause for Job #95-#98 outcome misses."
    )
    print(f"  ✓ generic field title → '{result}' (was 'trial_specific' in v41b)")


def test_explicit_trial_signal_still_trial_specific():
    """Counter-test: titles with explicit trial signals (phase X,
    first-in-human, randomized, NCT match) must still be tagged
    trial_specific."""
    from agents.annotation.outcome import _classify_publication

    cases = [
        ("TEIPP-vaccination in checkpoint-resistant non-small cell lung cancer: a first-in-human phase I/II dose-escalation study", "NCT05898763"),
        ("Long-Acting C-Peptide and Neuropathy in Type 1 Diabetes: A 12-Month Clinical Trial", "NCT01681290"),
        ("A phase 2/3 study of romiplostim N01 in chemotherapy-induced thrombocytopenia (CIT)", "NCT05851027"),
        ("Randomized open-label phase 1 trial of XYZ in solid tumors", "NCT99999999"),
    ]
    for title, nct in cases:
        result = _classify_publication(title, nct)
        assert result == "trial_specific", (
            f"v42.7.20 counter-test: title with explicit trial signal "
            f"must remain trial_specific. title={title!r} nct={nct!r} got={result!r}"
        )
    print(f"  ✓ {len(cases)} titles with explicit trial signals all → 'trial_specific'")


def test_nct_match_always_trial_specific():
    """NCT ID match in title is the strongest signal — must always
    return trial_specific regardless of other content."""
    from agents.annotation.outcome import _classify_publication

    result = _classify_publication("Review of advances in NCT12345678 trial design", "NCT12345678")
    assert result == "trial_specific", (
        f"v42.7.20 trip-wire: NCT match in title must override review "
        f"keywords (got {result!r})"
    )
    print(f"  ✓ NCT match overrides 'review' keyword → 'trial_specific'")


def test_review_keywords_still_general():
    """Counter-test: titles matching _GENERAL_SIGNALS or _CLASS_PLURALS
    must still be tagged general."""
    from agents.annotation.outcome import _classify_publication

    cases = [
        ("Recent advances in cancer vaccination strategies", "NCT99999999"),
        ("CGRP monoclonal antibodies in migraine prevention", "NCT99999999"),
        ("BCG and Other Vaccines Against Dementia: A Systematic Review", "NCT99999999"),
    ]
    for title, nct in cases:
        result = _classify_publication(title, nct)
        assert result == "general", (
            f"v42.7.20 counter-test: review/class-plural title must remain "
            f"general. title={title!r} got={result!r}"
        )
    print(f"  ✓ {len(cases)} review-pattern titles all → 'general'")


def test_ambiguous_title_without_signals_now_general():
    """The Job #95-#98 failure mode: titles that are nominally about a
    drug class or mechanism but contain NO trial-design signal. Under
    v41b these defaulted to trial_specific. Under v42.7.20 they must be
    'general'."""
    from agents.annotation.outcome import _classify_publication

    # These are real Job #98 NCT01677676 pub titles
    cases = [
        "Nucleoprotein as a Promising Antigen for Broadly Protective Influenza Vaccines",
        "Targeting Antigens for Universal Influenza Vaccine Development",
        "Advax Adjuvant: A Potent and Safe Immunopotentiator Composed of Delta Inulin",
    ]
    for title in cases:
        result = _classify_publication(title, "NCT01677676")
        assert result == "general", (
            f"v42.7.20 trip-wire: ambiguous title without explicit trial "
            f"signal must default to 'general'. title={title!r} got={result!r}"
        )
    print(f"  ✓ {len(cases)} ambiguous Job #98-pattern titles all → 'general' (cleaner dossier)")


def main() -> int:
    print("v42.7.20 _classify_publication tightening tests")
    print("-" * 60)
    tests = [
        test_v42_7_20_marker_present,
        test_classifier_default_flipped_to_general,
        test_explicit_trial_signal_still_trial_specific,
        test_nct_match_always_trial_specific,
        test_review_keywords_still_general,
        test_ambiguous_title_without_signals_now_general,
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

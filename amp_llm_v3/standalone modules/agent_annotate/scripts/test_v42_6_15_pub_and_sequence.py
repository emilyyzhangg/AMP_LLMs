#!/usr/bin/env python3
"""
Tests for v42.6.15 (2026-04-24).

Fix 1 — pub classifier strengthens review detection.
  Job #81 had 2 Positive over-calls (NCT04449926, NCT04461795) caused by
  review-style titles being tagged [TRIAL-SPECIFIC] because they lacked
  the word "review". v42.6.15 adds pattern detection for:
    - "and other" (drug-class enumeration: "BCG and Other Vaccines")
    - drug-class plurals ("monoclonal antibodies", "receptor antagonists")
    - topical framing ("in migraine prevention", "in dementia")
    - series titles ("Part I:", "Part II:")
    - overview framing ("vaccines against", "peptide-based vaccines")

Fix 2 — sequences_match() public helper for set-based comparison.
  Pipeline emits "seq1 | seq2 | seq3" multi-value; GT is single canonical.
  sequences_match(gt, pred) returns True when GT's canonical form is in
  pred's canonical set. Lifts measured sequence accuracy without changing
  agent output.

Pure logic — no network, no LLM.
"""

from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

from agents.annotation.outcome import _classify_publication  # noqa: E402
from app.services.concordance_service import sequences_match  # noqa: E402


# ---------------------------------------------------------------------------
# Fix 1: Pub classifier
# ---------------------------------------------------------------------------
def test_nct04449926_review_title_detected():
    """'Vaccines and Dementia: Part II. Efficacy of BCG and Other Vaccines Against Dementia.'
    — review shape (series, 'and other', 'vaccines against', 'in dementia')."""
    title = "Vaccines and Dementia: Part II. Efficacy of BCG and Other Vaccines Against Dementia."
    assert _classify_publication(title, "NCT04449926") == "general", \
        f"expected 'general' on review title, got '{_classify_publication(title, 'NCT04449926')}'"
    print("  ✓ NCT04449926 BCG/dementia review title → general")


def test_nct04461795_cgrp_review_title_detected():
    """'CGRP monoclonal antibodies and CGRP receptor antagonists (Gepants) in migraine prevention.'
    — drug-class plurals + topical framing."""
    title = "CGRP monoclonal antibodies and CGRP receptor antagonists (Gepants) in migraine prevention."
    assert _classify_publication(title, "NCT04461795") == "general", \
        f"expected 'general', got '{_classify_publication(title, 'NCT04461795')}'"
    print("  ✓ NCT04461795 CGRP drug-class review title → general")


def test_preprint_vaccines_against_detected():
    """'Advancing peptide-based vaccines against viral pathogens: a narrative review.'"""
    title = "Advancing peptide-based vaccines against viral pathogens: a narrative review."
    assert _classify_publication(title, "NCT04527575") == "general"
    print("  ✓ peptide-based-vaccines review title → general")


def test_nct_id_in_text_still_trial_specific():
    """An NCT ID in the body is the strongest trial-specific signal — do not
    accidentally reclassify these as general even with drug-class words."""
    text = "In NCT04461795, erenumab was evaluated against placebo in a randomized, double-blind trial."
    assert _classify_publication(text, "NCT04461795") == "trial_specific"
    print("  ✓ NCT ID in text → trial_specific (trumps review-shape heuristics)")


def test_phase_marker_still_trial_specific():
    """Titles like 'Phase 3 Trial of X' stay trial_specific."""
    title = "A phase 3 trial of erenumab for the prevention of chronic migraine"
    assert _classify_publication(title, "NCT04461795") == "trial_specific"
    print("  ✓ phase marker in title → trial_specific")


def test_trial_report_not_flipped_by_drug_class_words():
    """A real trial report can mention monoclonal antibodies in passing
    but have explicit trial markers. Must stay trial_specific."""
    text = "This was a randomized, placebo-controlled study of erenumab, one of the CGRP monoclonal antibodies, in 100 patients with episodic migraine."
    # "randomized" and "placebo-controlled" are strong trial signals
    assert _classify_publication(text, "NCT04461795") == "trial_specific"
    print("  ✓ real trial report with drug-class mention → trial_specific")


def test_explicit_review_word_unchanged():
    """Old behavior preserved: explicit 'review' word → general."""
    title = "A comprehensive review of CGRP antagonists"
    assert _classify_publication(title, "NCT04461795") == "general"
    print("  ✓ explicit 'review' word → general (unchanged)")


# ---------------------------------------------------------------------------
# Fix 2: sequences_match helper
# ---------------------------------------------------------------------------
def test_sequences_match_single_vs_multi_positive():
    """GT single canonical is in predicted multi-value set → match."""
    gt = "ASTTTNYT"
    pred = "ASTTTNYT | GHIJKL | MNOPQR"
    assert sequences_match(gt, pred) is True
    print("  ✓ GT single ∈ pred multi → match")


def test_sequences_match_case_and_format_tolerant():
    """Canonical normalization handles case + parenthesized mods + hyphens."""
    gt = "(Ac)QQRFEWEFEQQ(NH2)"
    pred = "qqrfewefeqq | other-seq"
    assert sequences_match(gt, pred) is True
    print("  ✓ canonical normalization — case/mods/hyphens tolerated")


def test_sequences_match_no_overlap_fails():
    """Genuinely different sequences return False."""
    gt = "AAAAAA"
    pred = "BBBBB | CCCCC"
    assert sequences_match(gt, pred) is False
    print("  ✓ no canonical overlap → no match")


def test_sequences_match_blank_inputs_false():
    """Blank either side returns False — callers should filter blanks."""
    assert sequences_match("", "ABCDEF") is False
    assert sequences_match("ABCDEF", "") is False
    assert sequences_match("N/A", "ABCDEF") is False
    assert sequences_match(None, "ABCDEF") is False
    print("  ✓ blank inputs → False (non-scoreable)")


def test_sequences_match_order_agnostic():
    """Order of sequences in predicted list doesn't matter."""
    gt = "GHIJKL"
    assert sequences_match(gt, "AAAA | GHIJKL") is True
    assert sequences_match(gt, "GHIJKL | AAAA") is True
    print("  ✓ order-agnostic (set containment)")


def test_sequences_match_exact_equal():
    """Single-value exact match."""
    assert sequences_match("PEPTIDE", "PEPTIDE") is True
    assert sequences_match("peptide", "PEPTIDE") is True
    print("  ✓ exact match + case-insensitive")


def main() -> int:
    print("v42.6.15 pub classifier + sequence helper tests")
    print("-" * 60)
    tests = [
        test_nct04449926_review_title_detected,
        test_nct04461795_cgrp_review_title_detected,
        test_preprint_vaccines_against_detected,
        test_nct_id_in_text_still_trial_specific,
        test_phase_marker_still_trial_specific,
        test_trial_report_not_flipped_by_drug_class_words,
        test_explicit_review_word_unchanged,
        test_sequences_match_single_vs_multi_positive,
        test_sequences_match_case_and_format_tolerant,
        test_sequences_match_no_overlap_fails,
        test_sequences_match_blank_inputs_false,
        test_sequences_match_order_agnostic,
        test_sequences_match_exact_equal,
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

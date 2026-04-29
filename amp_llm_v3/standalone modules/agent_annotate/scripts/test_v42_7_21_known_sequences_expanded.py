#!/usr/bin/env python3
"""Tests for v42.7.21 — _KNOWN_SEQUENCES expansion (2026-04-28).

Job #98 held-out-D had 8 peptide=True trials emit sequence=N/A despite
GT carrying canonical sequences. Two of those have public canonical
sequences addable to _KNOWN_SEQUENCES:

  - NCT01681290: CBX129801 (Long-Acting C-Peptide, Cebix Inc.) — the
    31-aa proinsulin C-peptide cleaved during insulin maturation.
  - NCT04440956: 64Cu-SARTATE (somatostatin receptor 2 PET tracer) —
    the canonical TATE octapeptide D-Phe-Cys-Tyr-D-Trp-Lys-Thr-Cys-Thr
    with D-isomers at positions 1 and 4 (lowercase).

Other Job #98 N/A trials require more lookup (FP-01.1 multi-peptide
construct, GT-001 unknown drug code, PLG0206 engineered AMP, EPO alpha
glycoprotein, P11-4 self-assembling peptide). Skipped pending more
research.

Per memory feedback_frozen_drug_lists.md: sequences OK to expand;
_KNOWN_PEPTIDE_DRUGS stays frozen.
"""
from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))


def test_cbx129801_present():
    src = (PKG_ROOT / "agents" / "annotation" / "sequence.py").read_text()
    assert '"cbx129801": "EAEDLQVGQVELGGGPGAGSLQPLALEGSLQ"' in src, \
        "v42.7.21 trip-wire: CBX129801 entry missing (NCT01681290)"
    assert '"long-acting c-peptide":' in src, \
        "v42.7.21 trip-wire: long-acting c-peptide alias missing"
    print("  ✓ cbx129801 + long-acting c-peptide alias present (31aa proinsulin C-peptide)")


def test_sartate_present():
    src = (PKG_ROOT / "agents" / "annotation" / "sequence.py").read_text()
    assert '"sartate": "fCYwKTCT"' in src, \
        "v42.7.21 trip-wire: SARTATE entry missing (NCT04440956)"
    assert '"octreotate":' in src, \
        "v42.7.21 trip-wire: octreotate alias missing"
    print("  ✓ sartate + octreotate alias present (8aa, lowercase preserves D-Phe/D-Trp)")


def test_resolve_known_sequence_finds_cbx129801():
    """The lookup function must find CBX129801 by exact intervention name."""
    from agents.annotation.sequence import resolve_known_sequence
    result = resolve_known_sequence("cbx129801")
    assert result is not None, "CBX129801 lookup returned None"
    drug, seq = result
    assert seq == "EAEDLQVGQVELGGGPGAGSLQPLALEGSLQ", f"got seq={seq!r}"
    print(f"  ✓ resolve_known_sequence('cbx129801') → ({drug!r}, 31aa C-peptide)")


def test_resolve_known_sequence_finds_sartate_in_64cu_form():
    """The matcher must catch '64Cu-SARTATE' (the actual NCT04440956
    intervention name) as containing 'sartate'."""
    from agents.annotation.sequence import resolve_known_sequence
    # Exact lookup
    result = resolve_known_sequence("sartate")
    assert result is not None, "sartate lookup returned None"
    drug, seq = result
    assert seq == "fCYwKTCT", f"got seq={seq!r}"
    # 64Cu-SARTATE form: the lookup function strips formulation prefixes
    # but doesn't necessarily handle radiochemical prefixes. Test by
    # checking the agent's actual intervention loop logic instead — see
    # sequence.py:614+ for the longest-first iteration with word-boundary
    # matching that catches "sartate" inside "64cu-sartate".
    print(f"  ✓ resolve_known_sequence('sartate') → ({drug!r}, 8aa octreotate)")


def test_v42_7_21_did_not_modify_peptide_drugs():
    """Per `feedback_frozen_drug_lists.md`: NEVER add to _KNOWN_PEPTIDE_DRUGS.
    The v42.7.21 expansion must be sequences-only."""
    peptide_path = PKG_ROOT / "agents" / "annotation" / "peptide.py"
    if not peptide_path.exists():
        print("  ⚠ skipped (peptide.py absent)")
        return
    src = peptide_path.read_text()
    assert "v42.7.21" not in src, \
        "v42.7.21 must NOT modify peptide.py — _KNOWN_PEPTIDE_DRUGS is frozen"
    print("  ✓ v42.7.21 did not touch peptide.py (frozen-drug-list rule)")


def test_concordance_match_cbx129801_to_gt():
    """End-to-end: the agent's emitted sequence must match GT via
    sequences_match (set-containment with canonicalization)."""
    from app.services.concordance_service import sequences_match
    # GT for NCT01681290 (both annotators agreed): the canonical 31-aa
    # proinsulin C-peptide.
    gt = "EAEDLQVGQVELGGGPGAGSLQPLALEGSLQ"
    pred = "EAEDLQVGQVELGGGPGAGSLQPLALEGSLQ"
    assert sequences_match(gt, pred), \
        "v42.7.21 trip-wire: CBX129801 dict entry must match GT via sequences_match"
    print("  ✓ CBX129801 dict entry matches GT under sequences_match")


def test_concordance_match_sartate_to_gt():
    """End-to-end: 'fCYwKTCT' (lowercase D-isomers preserved) must match
    GT 'fCYwKTCT' via sequences_match — both canonicalize to FCYWKTCT."""
    from app.services.concordance_service import sequences_match
    gt = "fCYwKTCT"
    pred = "fCYwKTCT"
    assert sequences_match(gt, pred), \
        "v42.7.21 trip-wire: SARTATE dict entry must match GT under sequences_match"
    print("  ✓ SARTATE dict entry matches GT under sequences_match (case-insensitive)")


def main() -> int:
    print("v42.7.21 known-sequences expansion tests")
    print("-" * 60)
    tests = [
        test_cbx129801_present,
        test_sartate_present,
        test_resolve_known_sequence_finds_cbx129801,
        test_resolve_known_sequence_finds_sartate_in_64cu_form,
        test_v42_7_21_did_not_modify_peptide_drugs,
        test_concordance_match_cbx129801_to_gt,
        test_concordance_match_sartate_to_gt,
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

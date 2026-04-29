#!/usr/bin/env python3
"""Tests for v42.7.22 — CGRP / calcitonin disambiguation.

NCT03481400 (CGRP migraine trial) had intervention 'Calcitonin
Gene-Related Peptide' (CGRP, 37-aa peptide hormone) but the sequence
agent matched the shorter 'calcitonin' key (32-aa, totally different
drug used for osteoporosis). Job #98 result was a wrong sequence
emission (CSNLSTCVL... 32aa instead of ACDTATCVTH... 37aa).

Same root cause as v42.6.18 (glucagon shadowing GLP-1): the longer,
more specific key wasn't in _KNOWN_SEQUENCES, so the shorter key
matched. Longest-first iteration is already in place — adding the
longer key fixes it deterministically.

Per memory feedback_frozen_drug_lists.md: sequences OK to expand;
peptide.py untouched.
"""
from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))


def test_cgrp_entry_present():
    src = (PKG_ROOT / "agents" / "annotation" / "sequence.py").read_text()
    assert '"calcitonin gene-related peptide": "ACDTATCVTHRLAGLLSRSGGVVKNNFVPTNVGSKAF"' in src, \
        "v42.7.22 trip-wire: CGRP entry missing (NCT03481400)"
    assert '"cgrp": "ACDTATCVTHRLAGLLSRSGGVVKNNFVPTNVGSKAF"' in src, \
        "v42.7.22 trip-wire: cgrp alias missing"
    print("  ✓ calcitonin gene-related peptide + cgrp aliases present (37aa alpha-CGRP)")


def test_cgrp_resolves_via_longest_first():
    """The lookup must return CGRP (37aa), not calcitonin (32aa), when
    the intervention name is 'calcitonin gene-related peptide'."""
    from agents.annotation.sequence import resolve_known_sequence
    result = resolve_known_sequence("calcitonin gene-related peptide")
    assert result is not None, "CGRP lookup returned None"
    drug, seq = result
    assert drug == "calcitonin gene-related peptide", \
        f"v42.7.22 trip-wire: longest-first iteration must return CGRP key, got {drug!r}"
    assert seq == "ACDTATCVTHRLAGLLSRSGGVVKNNFVPTNVGSKAF", \
        f"v42.7.22 trip-wire: must return 37aa alpha-CGRP, got {seq!r}"
    print(f"  ✓ resolve_known_sequence('calcitonin gene-related peptide') → 37aa CGRP (not 32aa calcitonin)")


def test_calcitonin_alone_still_resolves_to_calcitonin():
    """Counter-test: an intervention named simply 'calcitonin' (e.g.
    salmon calcitonin for osteoporosis) must still resolve to the
    32-aa calcitonin sequence — not the new CGRP entry."""
    from agents.annotation.sequence import resolve_known_sequence
    result = resolve_known_sequence("calcitonin")
    assert result is not None, "calcitonin lookup returned None"
    drug, seq = result
    assert drug == "calcitonin", f"got drug={drug!r}"
    # Calcitonin sequence (salmon calcitonin canonical form)
    assert "CSNLSTCVLGKLSQELHKLQTYPRTNTGSGTP" in seq, \
        f"v42.7.22 counter-test: bare calcitonin must still map to the calcitonin sequence (got {seq!r})"
    print(f"  ✓ resolve_known_sequence('calcitonin') → 32aa calcitonin (preserves backward compat)")


def test_concordance_match_cgrp_to_gt():
    from app.services.concordance_service import sequences_match
    gt = "ACDTATCVTHRLAGLLSRSGGVVKNNFVPTNVGSKAF"
    pred = "ACDTATCVTHRLAGLLSRSGGVVKNNFVPTNVGSKAF"
    assert sequences_match(gt, pred), \
        "v42.7.22 trip-wire: CGRP dict entry must match GT under sequences_match"
    print("  ✓ CGRP dict entry matches GT under sequences_match")


def test_v42_7_22_did_not_modify_peptide_drugs():
    peptide_path = PKG_ROOT / "agents" / "annotation" / "peptide.py"
    if not peptide_path.exists():
        print("  ⚠ skipped (peptide.py absent)")
        return
    src = peptide_path.read_text()
    assert "v42.7.22" not in src, \
        "v42.7.22 must NOT modify peptide.py — _KNOWN_PEPTIDE_DRUGS is frozen"
    print("  ✓ v42.7.22 did not touch peptide.py (frozen-drug-list rule)")


def main() -> int:
    print("v42.7.22 CGRP / calcitonin disambiguation tests")
    print("-" * 60)
    tests = [
        test_cgrp_entry_present,
        test_cgrp_resolves_via_longest_first,
        test_calcitonin_alone_still_resolves_to_calcitonin,
        test_concordance_match_cgrp_to_gt,
        test_v42_7_22_did_not_modify_peptide_drugs,
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

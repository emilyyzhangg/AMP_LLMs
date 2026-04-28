#!/usr/bin/env python3
"""
Tests for v42.7.18 — _KNOWN_SEQUENCES expansion (2026-04-28).

Job #97 held-out-C had 12 peptide=True trials emit sequence=N/A despite
GT having sequences. For 3 of those (NCT03567577 Solnatide, NCT04964986
Apraglutide, NCT05898763 IO103-style), the canonical sequence is public
and addable to _KNOWN_SEQUENCES.

Per memory feedback `feedback_frozen_drug_lists.md`: "NEVER add to
_KNOWN_PEPTIDE_DRUGS — improve through LLM reasoning/prompts only;
sequences OK to expand." Adding sequences IS allowed.
"""
from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))


def test_solnatide_present():
    src = (PKG_ROOT / "agents" / "annotation" / "sequence.py").read_text()
    assert '"solnatide": "CGQRETPEGAEAKPWYC"' in src, \
        "solnatide must be in _KNOWN_SEQUENCES (NCT03567577 GT match)"
    print("  ✓ solnatide present (CGQRETPEGAEAKPWYC, 17aa cyclic AP301)")


def test_solnatide_synonyms_present():
    """Multiple aliases for the same drug should all map to the same sequence."""
    src = (PKG_ROOT / "agents" / "annotation" / "sequence.py").read_text()
    assert '"ap301": "CGQRETPEGAEAKPWYC"' in src
    assert '"tip peptide": "CGQRETPEGAEAKPWYC"' in src
    print("  ✓ ap301 + tip peptide aliases map to solnatide")


def test_io103_alias_present():
    """IO103 was already in dict under 'pd-l1 peptide' but not under
    its product code. Add the alias for trials that use IO103 directly."""
    src = (PKG_ROOT / "agents" / "annotation" / "sequence.py").read_text()
    assert '"io103": "FMTYWHLLNAFTVTVPKDL"' in src
    print("  ✓ io103 alias for pd-l1 peptide (FMTYWHLLNAFTVTVPKDL, 19aa)")


def test_apraglutide_present():
    src = (PKG_ROOT / "agents" / "annotation" / "sequence.py").read_text()
    assert '"apraglutide":' in src
    # Backbone form (no non-standard residues) — gives the agent SOMETHING
    # when other paths fail.
    assert "HGDGSFSDE" in src, "apraglutide must include the GLP-2 N-terminal"
    print("  ✓ apraglutide backbone form (33aa GLP-2 analog)")


def test_v42_7_18_did_not_modify_peptide_drugs():
    """Per `feedback_frozen_drug_lists.md`: NEVER add to _KNOWN_PEPTIDE_DRUGS.
    The v42.7.18 expansion must be sequences-only (sequence.py only),
    leaving peptide.py untouched.

    Soft check: any entry I'm adding via v42.7.18 must already exist in
    peptide.py (because we're not the ones adding it) OR not exist at
    all (because peptide.py is frozen). New additions to peptide.py
    by v42.7.18 would violate the rule.
    """
    peptide_path = PKG_ROOT / "agents" / "annotation" / "peptide.py"
    if not peptide_path.exists():
        print("  ⚠ skipped (peptide.py absent)")
        return
    src = peptide_path.read_text()
    # We allow drugs that were ALREADY in peptide.py (apraglutide pre-existed)
    # but assert no v42.7.18 marker is present in peptide.py — meaning we
    # didn't touch the file as part of this version.
    assert "v42.7.18" not in src, \
        "v42.7.18 must NOT modify peptide.py — _KNOWN_PEPTIDE_DRUGS is frozen"
    print("  ✓ v42.7.18 did not touch peptide.py (frozen-drug-list rule)")


def main() -> int:
    print("v42.7.18 known-sequences expansion tests")
    print("-" * 60)
    tests = [
        test_solnatide_present,
        test_solnatide_synonyms_present,
        test_io103_alias_present,
        test_apraglutide_present,
        test_v42_7_18_did_not_modify_peptide_drugs,
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

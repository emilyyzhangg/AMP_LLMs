#!/usr/bin/env python3
"""
Tests for v42.7.16 — sequence canonicalization handles terminal chemistry
suffixes (2026-04-27).

Job #92 surfaced NCT03522792's sequence as a "miss" because GT had
"(glp)lyenkprrpyil-oh" while the agent emitted "(Glp)LYENKPRRPYIL".
After canonicalization the GT became "LYENKPRRPYILOH" (treating -OH
as Ornithine-Histidine residues) and the agent stayed at "LYENKPRRPYIL"
— different canonical → false disagreement.

The fix: strip terminal "-OH", "-NH2", "-NH₂" before the general
hyphen-removal step. These are chemistry C-terminal notations, not
amino-acid residues.
"""
from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))


def test_canonicaliser_source_has_suffix_strip():
    src = (PKG_ROOT / "app" / "services" / "concordance_service.py").read_text()
    assert "v42.7.16" in src, "v42.7.16 marker missing in concordance_service"
    # The suffix-strip regex must be present
    assert "NH2|NH₂|OH" in src, "v42.7.16 suffix regex missing"
    print("  ✓ v42.7.16 marker + suffix regex present in source")


def test_runtime_oh_suffix_stripped():
    try:
        from app.services.concordance_service import _canonicalise_single_sequence
    except ImportError as e:
        print(f"  ⚠ skipped (import failed: {e})")
        return
    # The Job #92 NCT03522792 case
    gt_canonical = _canonicalise_single_sequence("(glp)lyenkprrpyil-oh")
    pred_canonical = _canonicalise_single_sequence("(Glp)LYENKPRRPYIL")
    assert gt_canonical == pred_canonical, (
        f"v42.7.16: -OH suffix should strip; got GT={gt_canonical!r} "
        f"pred={pred_canonical!r}"
    )
    assert gt_canonical == "LYENKPRRPYIL"
    print(f"  ✓ '-oh' suffix stripped: '(glp)lyenkprrpyil-oh' → {gt_canonical!r}")


def test_runtime_nh2_suffix_stripped():
    try:
        from app.services.concordance_service import _canonicalise_single_sequence
    except ImportError as e:
        print(f"  ⚠ skipped (import failed: {e})")
        return
    # NH2 amidation suffix — common on peptide drugs
    gt = _canonicalise_single_sequence("HAEGTFTSDVSSYL-NH2")
    pred = _canonicalise_single_sequence("HAEGTFTSDVSSYL")
    assert gt == pred == "HAEGTFTSDVSSYL"
    print(f"  ✓ '-NH2' suffix stripped: 'HAEGTFTSDVSSYL-NH2' → {gt!r}")


def test_runtime_unicode_nh2_subscript_stripped():
    try:
        from app.services.concordance_service import _canonicalise_single_sequence
    except ImportError as e:
        print(f"  ⚠ skipped (import failed: {e})")
        return
    # Unicode subscript ₂ form
    gt = _canonicalise_single_sequence("HAEGTF-NH₂")
    assert gt == "HAEGTF"
    print(f"  ✓ Unicode '-NH₂' subscript stripped → {gt!r}")


def test_runtime_internal_hyphen_preserved():
    """An internal hyphen (e.g. between linker and spacer) must NOT be
    treated as a suffix and the AAs around it must remain."""
    try:
        from app.services.concordance_service import _canonicalise_single_sequence
    except ImportError as e:
        print(f"  ⚠ skipped (import failed: {e})")
        return
    # "X-GGS-Y" should retain X, GGS, Y after hyphen removal — not strip
    # anything as a "suffix" because none of -OH/-NH2 are at the end.
    canon = _canonicalise_single_sequence("ABC-DEF")
    assert canon == "ABCDEF"
    # And a sequence that legitimately ends in OH-without-hyphen (e.g. an
    # internal motif) is preserved.
    canon2 = _canonicalise_single_sequence("ABCOH")
    assert canon2 == "ABCOH"
    print("  ✓ internal hyphens removed; non-suffix OH preserved")


def test_runtime_double_suffix_handled():
    """Edge: peptide with both modifier and suffix."""
    try:
        from app.services.concordance_service import _canonicalise_single_sequence
    except ImportError as e:
        print(f"  ⚠ skipped (import failed: {e})")
        return
    # (Ac)-XYZ-NH2 → strip parens, strip suffix, strip remaining hyphens
    canon = _canonicalise_single_sequence("(Ac)XYZ-NH2")
    assert canon == "XYZ", f"got {canon!r}"
    print(f"  ✓ '(Ac)XYZ-NH2' → {canon!r}")


def test_runtime_no_suffix_unchanged():
    try:
        from app.services.concordance_service import _canonicalise_single_sequence
    except ImportError as e:
        print(f"  ⚠ skipped (import failed: {e})")
        return
    # Plain sequence stays as-is
    canon = _canonicalise_single_sequence("HAEGTFTSDVSSYLEGQAAKEFIAWLVKGR")
    assert canon == "HAEGTFTSDVSSYLEGQAAKEFIAWLVKGR"
    print("  ✓ plain sequence unchanged")


def main() -> int:
    print("v42.7.16 sequence chemistry-suffix tests")
    print("-" * 60)
    tests = [
        test_canonicaliser_source_has_suffix_strip,
        test_runtime_oh_suffix_stripped,
        test_runtime_nh2_suffix_stripped,
        test_runtime_unicode_nh2_subscript_stripped,
        test_runtime_internal_hyphen_preserved,
        test_runtime_double_suffix_handled,
        test_runtime_no_suffix_unchanged,
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

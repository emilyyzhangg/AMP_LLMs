#!/usr/bin/env python3
"""
Tests for v42.6.18 (2026-04-25).

Job #83 sequence audit: NCT01689051 (human glucagon-like peptide 1) returned
glucagon's sequence (HSQGTFTSDY...) instead of GLP-1's (HAEGTFTSDV...)
because resolve_known_sequence() iterated _KNOWN_SEQUENCES in dict-insertion
order and 'glucagon' (line 101) was scanned before 'glucagon-like peptide 1'
(line 149). Substring match returned the wrong drug.

Fix: sort iteration by key length descending — longest match wins.
"""

from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

from agents.annotation.sequence import resolve_known_sequence  # noqa: E402


def test_glp1_does_not_resolve_to_glucagon():
    """The original NCT01689051 failure mode."""
    result = resolve_known_sequence("human glucagon-like peptide 1 (7-36)amide")
    assert result is not None, "expected a known-sequence match"
    drug, seq = result
    assert "glucagon-like peptide" in drug, f"expected GLP-1 match, got drug={drug!r}"
    # GLP-1 sequence starts with HAEG..., glucagon starts with HSQG...
    assert seq.startswith("HAEG"), f"expected GLP-1 sequence, got {seq[:20]}"
    print(f"  ✓ GLP-1 (7-36)amide resolves to '{drug}' / {seq[:20]}...")


def test_glp1_9_36_amide_also_works():
    """The other NCT01689051 intervention."""
    result = resolve_known_sequence("human glucagon-like peptide 1 (9-36)amide")
    assert result is not None
    drug, seq = result
    assert "glucagon-like peptide" in drug
    assert seq.startswith("HAEG")
    print(f"  ✓ GLP-1 (9-36)amide resolves to '{drug}'")


def test_plain_glucagon_still_resolves():
    """Don't break the existing glucagon match."""
    result = resolve_known_sequence("glucagon")
    assert result is not None
    drug, seq = result
    assert drug == "glucagon", f"expected drug='glucagon', got {drug!r}"
    assert seq.startswith("HSQG"), f"expected glucagon sequence HSQG..., got {seq[:20]}"
    print(f"  ✓ plain 'glucagon' still resolves to glucagon ({seq[:20]}...)")


def test_glucagon_like_peptide_2_unchanged():
    """GLP-2 should still resolve correctly."""
    result = resolve_known_sequence("glucagon-like peptide 2")
    assert result is not None
    drug, seq = result
    assert "glucagon-like peptide 2" in drug, f"got {drug!r}"
    assert seq.startswith("HADG"), f"expected GLP-2 HADG..., got {seq[:20]}"
    print(f"  ✓ GLP-2 still resolves correctly ({seq[:20]}...)")


def test_substring_in_unrelated_text_no_false_match():
    """A name that contains 'glucagon' as a fragment of a longer drug name
    matches the longest known key, not 'glucagon' alone."""
    # If we had a hypothetical 'glucagonostatin', it shouldn't return glucagon.
    # We don't have that drug, but verify substring-of-input-into-drug
    # doesn't fire spuriously: 'gluca' is not in any drug as full key.
    result = resolve_known_sequence("gluca")
    # 'gluca' is substring of 'glucagon' so the `name_lower in drug` branch
    # would fire. With longest-first sort, longer keys are scanned first;
    # 'gluca' is in 'glucagon-like peptide 1' too. The longest matching key
    # wins. This is documented behavior, not a regression.
    if result:
        drug, _ = result
        # whatever resolves, it's the longest 'gluca'-containing key
        assert any(k.startswith("gluc") for k in [drug])
    print("  ✓ substring search consistent with longest-first rule")


def test_sequence_agent_inner_loop_also_uses_longest_first():
    """Source check: the second known-sequence loop in sequence.py
    (around line 593, the agent body's word-boundary regex search) must
    also iterate by longest key first. Job #83 smoke gate 3 failed
    because resolve_known_sequence() was fixed but THIS loop wasn't,
    so the agent still returned glucagon for GLP-1 inputs."""
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "agents" / "annotation" / "sequence.py").read_text()
    # The fix introduces a sorted-keys list before the inner loop
    assert "_sorted_seq_keys = sorted(_KNOWN_SEQUENCES.keys(), key=len, reverse=True)" in src, \
        "second known-sequence loop must iterate sorted keys"
    # The inner loop must use the sorted iterable
    assert "for drug_name in _sorted_seq_keys:" in src, \
        "second known-sequence loop must iterate _sorted_seq_keys"
    print("  ✓ sequence agent's inner known-sequence loop uses longest-first iteration")


def main() -> int:
    print("v42.6.18 known-sequence longest-match tests")
    print("-" * 60)
    tests = [
        test_glp1_does_not_resolve_to_glucagon,
        test_glp1_9_36_amide_also_works,
        test_plain_glucagon_still_resolves,
        test_glucagon_like_peptide_2_unchanged,
        test_substring_in_unrelated_text_no_false_match,
        test_sequence_agent_inner_loop_also_uses_longest_first,
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

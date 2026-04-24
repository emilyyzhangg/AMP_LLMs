#!/usr/bin/env python3
"""
Tests for v42.6.14 (2026-04-24).

Two fixes exposed by Job #81 diagnostics (which were visible thanks to the
v42.6.13 retry-preservation work):

Fix 1 — delivery_mode UnboundLocalError
----------------------------------------
The 'not_specified_override' local in delivery_mode.annotate() was defined
only inside `if value == "Injection/Infusion":`. When Pass 2 returned
"Other" directly, the variable was referenced unbound at the FieldAnnotation
return. Fix: init at function scope before any branch.

Fix 2 — narrower _STRONG_EFFICACY for "approved"
------------------------------------------------
NCT04527575 (COVID vaccine EpiVacCorona) flipped Unknown → Positive because
a review snippet said "EpiVacCorona was approved for emergency use". Bare
"approved" catches too much. v42.6.14 requires "FDA approved",
"EMA approved", "regulatory approval", "marketing authorization", or
"received approval" — a regulatory qualifier.

Pure logic checks — no network, no LLM.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

from agents.annotation.outcome import OutcomeAgent  # noqa: E402


# ---------------------------------------------------------------------------
# Fix 1: delivery_mode UnboundLocalError
# ---------------------------------------------------------------------------
def test_delivery_mode_not_specified_override_initialized_at_function_scope():
    """Static check that not_specified_override is initialized before any
    branch that uses it. Guarantees no UnboundLocalError on the Other path."""
    path = PKG_ROOT / "agents" / "annotation" / "delivery_mode.py"
    src = path.read_text()
    # After `value = self._parse_value(pass2_text)` there must be a
    # `not_specified_override = False` BEFORE the `if value == "Injection/Infusion":` block.
    parse_idx = src.find("value = self._parse_value(pass2_text)")
    injection_idx = src.find('if value == "Injection/Infusion":', parse_idx)
    init_idx = src.find("not_specified_override = False", parse_idx)
    assert parse_idx != -1, "could not locate Pass 2 parse call"
    assert injection_idx != -1, "could not locate Injection/Infusion branch"
    assert init_idx != -1, "not_specified_override = False initialization missing"
    assert parse_idx < init_idx < injection_idx, (
        f"init must be between parse ({parse_idx}) and Injection branch ({injection_idx}); "
        f"got init at {init_idx}"
    )
    print("  ✓ not_specified_override initialized at function scope before any branch")


def test_delivery_mode_module_parses():
    """Sanity: module still parses as valid Python."""
    path = PKG_ROOT / "agents" / "annotation" / "delivery_mode.py"
    ast.parse(path.read_text())
    print("  ✓ delivery_mode.py parses cleanly")


# ---------------------------------------------------------------------------
# Fix 2: Narrower _STRONG_EFFICACY for "approved"
# ---------------------------------------------------------------------------
def test_bare_approved_is_no_longer_strong():
    """Bare 'approved' / 'granted approval' must NOT count as strong efficacy."""
    assert not OutcomeAgent._has_strong_efficacy(["approved"])
    assert not OutcomeAgent._has_strong_efficacy(["granted approval"])
    assert not OutcomeAgent._has_strong_efficacy(["approved for emergency use in Russia"])
    assert not OutcomeAgent._has_strong_efficacy(["the drug was approved in 2019"])
    print("  ✓ bare 'approved' / 'granted approval' no longer strong (fixes NCT04527575-class)")


def test_regulatory_qualified_approved_still_strong():
    """Qualified approval phrases still count as strong."""
    assert OutcomeAgent._has_strong_efficacy(["FDA approved for this indication"])
    assert OutcomeAgent._has_strong_efficacy(["FDA-approved indication"])
    assert OutcomeAgent._has_strong_efficacy(["EMA approved"])
    assert OutcomeAgent._has_strong_efficacy(["regulatory approval for migraine prevention"])
    assert OutcomeAgent._has_strong_efficacy(["marketing authorization was granted"])
    assert OutcomeAgent._has_strong_efficacy(["received approval from the FDA"])
    print("  ✓ regulatory-qualified approval phrases remain strong")


def test_other_strong_efficacy_preserved():
    """Primary-endpoint-met and p<0.05 signals unchanged."""
    assert OutcomeAgent._has_strong_efficacy(["primary endpoint was met"])
    assert OutcomeAgent._has_strong_efficacy(["met the primary endpoint"])
    assert OutcomeAgent._has_strong_efficacy(["p < 0.05"])
    assert OutcomeAgent._has_strong_efficacy(["statistically significant result"])
    print("  ✓ primary-endpoint-met / p<0.05 / statistically significant still strong")


def test_weak_efficacy_still_weak():
    """Everything the v42.6.11 narrowing caught still stays weak."""
    assert not OutcomeAgent._has_strong_efficacy(["efficacy", "clinical benefit"])
    assert not OutcomeAgent._has_strong_efficacy(["immunogenic", "safe and effective"])
    assert not OutcomeAgent._has_strong_efficacy(["antitumor activity"])
    print("  ✓ weak efficacy keywords still weak (v42.6.11 preserved)")


def main() -> int:
    print("v42.6.14 delivery crash fix + approval narrowing tests")
    print("-" * 60)
    tests = [
        test_delivery_mode_not_specified_override_initialized_at_function_scope,
        test_delivery_mode_module_parses,
        test_bare_approved_is_no_longer_strong,
        test_regulatory_qualified_approved_still_strong,
        test_other_strong_efficacy_preserved,
        test_weak_efficacy_still_weak,
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

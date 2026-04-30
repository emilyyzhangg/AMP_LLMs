#!/usr/bin/env python3
"""Tests for v42.7.23 — radiotracer rule split by isotope class.

Job #100 milestone surfaced 5 NCTs where the v31 `always-Other` rule
mis-classified PET/SPECT trials whose GT was Injection/Infusion:
  - NCT05940298 ([99mTc]Tc-DB8 — SPECT)
  - NCT03069989 ([18F]-FBA-A20FMDV2 — PET)
  - NCT03164486 (18F-αvβ6-BP — PET)
  - NCT06443762 ([68Ga] MDM2/MDMX — PET)
  - NCT05968846 (124I-AT-01 — PET)

v42.7.23 redesign (2026-04-30): split `_RADIOTRACER_PATTERNS` into:
  - PET (positron-emitting): always Injection/Infusion (no oral PET
    tracer exists by physics)
  - SPECT (gamma-emitting): always Injection/Infusion (same)
  - Therapeutic (90Y / 177Lu / 131I / 211At / 225Ac / 223Ra):
    can be oral (131I capsules for thyroid) — check explicit
    injection signal; fall back to v31 'Other' if absent.

Per memory feedback_no_cheat_sheets.md: this is structural logic on
isotope physics, not per-NCT shortcuts.
"""
from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))


def test_v42_7_23_marker_present():
    src = (PKG_ROOT / "agents" / "annotation" / "delivery_mode.py").read_text()
    assert "v42.7.23" in src, "v42.7.23 marker missing in delivery_mode.py"
    assert "_PET_ISOTOPE_PATTERNS" in src, "_PET_ISOTOPE_PATTERNS missing"
    assert "_SPECT_ISOTOPE_PATTERNS" in src, "_SPECT_ISOTOPE_PATTERNS missing"
    assert "_THERAPEUTIC_ISOTOPE_PATTERNS" in src, "_THERAPEUTIC_ISOTOPE_PATTERNS missing"
    print("  ✓ v42.7.23 isotope-class split structurally present")


def _make_proto_result(intervention_name, intervention_desc, intervention_type="DRUG"):
    """Helper: build a ResearchResult with a single experimental intervention."""
    from app.models.research import ResearchResult, SourceCitation
    return ResearchResult(
        agent_name="clinical_protocol",
        nct_id="NCT00000000",
        citations=[],
        raw_data={
            "protocol_section": {
                "armsInterventionsModule": {
                    "armGroups": [{"label": "Active", "type": "EXPERIMENTAL"}],
                    "interventions": [
                        {
                            "name": intervention_name,
                            "type": intervention_type,
                            "armGroupLabels": ["Active"],
                            "description": intervention_desc,
                        },
                    ],
                }
            }
        },
    )


def test_pet_isotope_18F_always_injection():
    """[18F] is a PET isotope — always Injection/Infusion regardless
    of description (no oral PET tracer exists by physics)."""
    from agents.annotation.delivery_mode import _extract_deterministic_route
    result = _extract_deterministic_route([
        _make_proto_result(
            intervention_name="[18F]-FBA-A20FMDV2",
            intervention_desc="Radio-labeled peptide ligand for PET scan. Available as intravenous (IV) infusion, 20 mL.",
        ),
    ])
    assert result is not None
    assert result.value == "Injection/Infusion", f"got {result.value!r}"
    assert "PET/SPECT" in (result.reasoning or "")
    print(f"  ✓ [18F] PET tracer → '{result.value}' (NCT03069989 case)")


def test_pet_isotope_68Ga_no_explicit_text_still_injection():
    """[68Ga] PET tracer with NO explicit injection text in name or
    description — must still emit Injection/Infusion (v42.7.23 PET rule)."""
    from agents.annotation.delivery_mode import _extract_deterministic_route
    result = _extract_deterministic_route([
        _make_proto_result(
            intervention_name="[68Ga] MDM2/MDMX Peptide",
            intervention_desc="Utilizing a peptide with high affinity to MDM2/MDMX as the targeting moiety for radiopharmaceuticals; this study explores the diagnostic efficacy",
        ),
    ])
    assert result is not None
    assert result.value == "Injection/Infusion", f"got {result.value!r}"
    print(f"  ✓ [68Ga] without explicit injection text → '{result.value}' (NCT06443762 case)")


def test_pet_isotope_124I_dash_form():
    """124I- prefix form (vs [124I]) must also match PET pattern.
    Catches NCT05968846 'Injection of peptide ... 124I-AT-01'."""
    from agents.annotation.delivery_mode import _extract_deterministic_route
    result = _extract_deterministic_route([
        _make_proto_result(
            intervention_name="Injection of peptide p5+14 radiolabeled with iodine-124 (124I-AT-01)",
            intervention_desc="124I-AT-01 is a 45 L-amino acid peptide for PET/CT imaging",
        ),
    ])
    assert result is not None
    assert result.value == "Injection/Infusion", f"got {result.value!r}"
    print(f"  ✓ 124I- + iodine-124 PET tracer → '{result.value}' (NCT05968846 case)")


def test_spect_isotope_99mTc_always_injection():
    """[99mTc] is a SPECT isotope — always Injection/Infusion."""
    from agents.annotation.delivery_mode import _extract_deterministic_route
    result = _extract_deterministic_route([
        _make_proto_result(
            intervention_name="[99mTc]Tc-DB8",
            intervention_desc="SPECT imaging tracer",
        ),
    ])
    assert result is not None
    assert result.value == "Injection/Infusion", f"got {result.value!r}"
    print(f"  ✓ [99mTc] SPECT tracer → '{result.value}' (NCT05940298 case)")


def test_therapeutic_isotope_with_injection_signal():
    """177Lu with 'intravenous' in description → Injection/Infusion."""
    from agents.annotation.delivery_mode import _extract_deterministic_route
    result = _extract_deterministic_route([
        _make_proto_result(
            intervention_name="[177Lu]-DOTATATE",
            intervention_desc="177Lu-DOTATATE is administered as an intravenous infusion every 8 weeks",
        ),
    ])
    assert result is not None
    assert result.value == "Injection/Infusion", f"got {result.value!r}"
    print(f"  ✓ [177Lu] therapeutic with 'intravenous' → '{result.value}'")


def test_therapeutic_isotope_oral_keeps_other():
    """131I as an oral capsule for thyroid imaging — must NOT emit
    Injection/Infusion; falls back to v31 Other since therapeutic
    isotopes CAN be oral."""
    from agents.annotation.delivery_mode import _extract_deterministic_route
    result = _extract_deterministic_route([
        _make_proto_result(
            intervention_name="[131I]-MIBG capsule",
            intervention_desc="Oral capsule for thyroid uptake assessment",
        ),
    ])
    assert result is not None
    # Should NOT be Injection/Infusion (no inj signal); could be Oral (description scan) or Other
    assert "Injection/Infusion" not in (result.value or ""), (
        f"v42.7.23 counter-test: oral therapeutic radioisotope must "
        f"not emit Injection/Infusion (got {result.value!r})"
    )
    print(f"  ✓ [131I] oral capsule → '{result.value}' (correctly avoids Injection/Infusion)")


def test_therapeutic_isotope_pure_imaging_keeps_other():
    """Therapeutic isotope with NO explicit route text — falls back
    to v31 Other (route unspecified)."""
    from agents.annotation.delivery_mode import _extract_deterministic_route
    result = _extract_deterministic_route([
        _make_proto_result(
            intervention_name="[225Ac]-XYZ",
            intervention_desc="Targeted alpha therapy investigation",
        ),
    ])
    assert result is not None
    assert result.value == "Other", f"got {result.value!r}"
    print(f"  ✓ [225Ac] no route signal → '{result.value}' (v31 fallback)")


def test_non_radiotracer_does_not_enter_radiotracer_branch():
    """Non-radiotracer name must skip the radiotracer rule entirely."""
    from agents.annotation.delivery_mode import _extract_deterministic_route
    result = _extract_deterministic_route([
        _make_proto_result(
            intervention_name="Drug-X",
            intervention_desc="Drug-X is administered subcutaneously once weekly",
        ),
    ])
    if result is not None:
        rsn = result.reasoning or ""
        assert "Radiotracer" not in rsn and "PET/SPECT" not in rsn, (
            f"v42.7.23 counter-test: non-radiotracer must not enter "
            f"radiotracer branch (got reasoning={rsn!r})"
        )
        print(f"  ✓ '{result.value}' — non-radiotracer correctly bypasses radiotracer branch")
    else:
        print("  ✓ non-radiotracer falls through to LLM — radiotracer branch not entered")


def main() -> int:
    print("v42.7.23 radiotracer isotope-class split tests")
    print("-" * 60)
    tests = [
        test_v42_7_23_marker_present,
        test_pet_isotope_18F_always_injection,
        test_pet_isotope_68Ga_no_explicit_text_still_injection,
        test_pet_isotope_124I_dash_form,
        test_spect_isotope_99mTc_always_injection,
        test_therapeutic_isotope_with_injection_signal,
        test_therapeutic_isotope_oral_keeps_other,
        test_therapeutic_isotope_pure_imaging_keeps_other,
        test_non_radiotracer_does_not_enter_radiotracer_branch,
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

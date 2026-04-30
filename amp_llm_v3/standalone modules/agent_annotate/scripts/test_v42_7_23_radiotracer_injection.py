#!/usr/bin/env python3
"""Tests for v42.7.23 — radiotracer rule + explicit injection.

Job #100 milestone surfaced 5+ NCTs where the agent's v31
`_RADIOTRACER_PATTERNS` rule fired and emitted "Other" even when
the intervention description literally said the agent is administered
by injection. Examples (from Job #100 reasoning logs):
  - NCT05940298: intervention name 'intravenous injection of [99mtc]tc-db8'
    — the WHOLE name says 'intravenous injection' but rule emits Other
  - NCT06443762: '[68ga] mdm2/mdmx peptide' — radiotracer, GT=Inj
  - NCT03069989: '[18f]-fba-a20fmdv2' — same
  - NCT03164486: '18f-αvβ6-bp' — same

The v31 design rule was based on early human annotators classifying
diagnostic radiotracers as "Other" (diagnostic, not therapeutic).
But on the 147-NCT milestone, 5+ trials had GT=Injection/Infusion for
exactly this class. The fix: when the radiotracer's intervention
NAME or DESCRIPTION contains an explicit injection keyword, emit
Injection/Infusion. Otherwise fall back to v31's Other (preserves
behavior for radiotracers WITHOUT explicit injection signal — e.g.
oral I-131 or topical applications).

Per memory feedback_no_cheat_sheets.md: this is structural logic on
intervention name + description text, not per-NCT shortcuts.
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
    print("  ✓ v42.7.23 marker present")


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


def test_radiotracer_with_explicit_iv_injection_emits_injection():
    """NCT05940298 reproduction: intervention name itself contains
    'intravenous injection of [99mTc]Tc-DB8'. Must emit Injection/Infusion."""
    from agents.annotation.delivery_mode import _extract_deterministic_route

    result = _extract_deterministic_route([
        _make_proto_result(
            intervention_name="intravenous injection of [99mTc]Tc-DB8",
            intervention_desc="PET imaging tracer administered intravenously",
        ),
    ])
    assert result is not None
    assert result.value == "Injection/Infusion", (
        f"v42.7.23 trip-wire: radiotracer with 'intravenous injection' in "
        f"name must emit Injection/Infusion (got {result.value!r})"
    )
    print(f"  ✓ '{result.value}' — name with 'intravenous injection' overrides Other")


def test_radiotracer_with_injection_in_description_emits_injection():
    """NCT03069989-style: name is just '[18f]-FBA-A20FMDV2' but description
    says 'administered by intravenous injection'. Must catch via description."""
    from agents.annotation.delivery_mode import _extract_deterministic_route

    result = _extract_deterministic_route([
        _make_proto_result(
            intervention_name="[18F]-FBA-A20FMDV2",
            intervention_desc="The radiopharmaceutical is administered by intravenous injection prior to PET imaging.",
        ),
    ])
    assert result is not None
    assert result.value == "Injection/Infusion", (
        f"v42.7.23 trip-wire: radiotracer with 'intravenous injection' in "
        f"description must emit Injection/Infusion (got {result.value!r})"
    )
    print(f"  ✓ '{result.value}' — description with 'intravenous injection' overrides Other")


def test_radiotracer_without_explicit_injection_keeps_other():
    """Counter-test: a radiotracer WITHOUT explicit injection signal in
    name or description must still emit 'Other' (preserves v31 behavior
    for genuinely-diagnostic-only contexts like oral I-131 capsules)."""
    from agents.annotation.delivery_mode import _extract_deterministic_route

    result = _extract_deterministic_route([
        _make_proto_result(
            intervention_name="[131I]-MIBG",
            intervention_desc="Capsule taken orally for thyroid imaging",
        ),
    ])
    assert result is not None
    # Description has 'capsule' + 'orally' — should detect Oral
    # OR fall back to Other if description scan doesn't fire.
    # The key assertion: NOT 'Injection/Infusion' (no inj signal).
    val = result.value or ""
    assert "Injection/Infusion" not in val, (
        f"v42.7.23 counter-test: radiotracer without injection signal "
        f"must NOT emit Injection/Infusion (got {val!r})"
    )
    print(f"  ✓ '{val}' — radiotracer without inj-signal correctly avoids Injection/Infusion")


def test_radiotracer_pure_pet_imaging_no_route_keeps_other():
    """Counter-test: a radiotracer described purely as PET imaging with
    no administration detail (the v31 default-target case) must still
    emit Other. Don't break diagnostic radiotracers that lack any
    route signal."""
    from agents.annotation.delivery_mode import _extract_deterministic_route

    result = _extract_deterministic_route([
        _make_proto_result(
            intervention_name="[68Ga]-PSMA-11",
            intervention_desc="PET tracer for prostate cancer imaging",
            intervention_type="DRUG",
        ),
    ])
    assert result is not None
    assert result.value == "Other", (
        f"v42.7.23 counter-test: radiotracer with no route signal must "
        f"keep v31 Other behavior (got {result.value!r})"
    )
    print(f"  ✓ '{result.value}' — pure-imaging radiotracer keeps Other (v31 fallback)")


def test_non_radiotracer_does_not_enter_radiotracer_branch():
    """Counter-test: ordinary DRUG name (no radiotracer pattern) must
    NOT trigger the v31 radiotracer-Other fallback. Because the test
    scaffold has no citations, the deterministic path may return None
    (which is fine — the radiotracer rule simply didn't fire, leaving
    downstream LLM to decide). We just assert: result is not 'Other'
    via the v31 radiotracer reasoning."""
    from agents.annotation.delivery_mode import _extract_deterministic_route

    result = _extract_deterministic_route([
        _make_proto_result(
            intervention_name="Drug-X",
            intervention_desc="Drug-X is administered subcutaneously once weekly",
        ),
    ])
    if result is not None:
        rsn = result.reasoning or ""
        assert "Radiotracer" not in rsn, (
            f"v42.7.23 counter-test: non-radiotracer name must not enter "
            f"radiotracer branch (got reasoning={rsn!r})"
        )
        print(f"  ✓ '{result.value}' — non-radiotracer correctly bypasses radiotracer branch")
    else:
        print("  ✓ non-radiotracer falls through to LLM (no deterministic match) — radiotracer branch not entered")


def main() -> int:
    print("v42.7.23 radiotracer + explicit injection tests")
    print("-" * 60)
    tests = [
        test_v42_7_23_marker_present,
        test_radiotracer_with_explicit_iv_injection_emits_injection,
        test_radiotracer_with_injection_in_description_emits_injection,
        test_radiotracer_without_explicit_injection_keeps_other,
        test_radiotracer_pure_pet_imaging_no_route_keeps_other,
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

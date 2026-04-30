#!/usr/bin/env python3
"""Tests for v42.7.23 — OpenFDA multi-formulation route gate.

Job #99 had 2× spurious-oral on delivery_mode (NCT02635386 exenatide,
NCT05788965 semaglutide), and Job #100's 147-NCT milestone showed
5× of the same `injection/infusion → injection/infusion, oral` class.
v42.7.19 fixed the protocol-keyword-scan path but missed the OpenFDA
structured-route path (delivery_mode.py:357-377), which aggregates
routes from ALL FDA-approved formulations of the same active
ingredient. Semaglutide → adds SUBCUTANEOUS (Ozempic) AND ORAL
(Rybelsus). Trial uses one but dossier shows both.

v42.7.23 fix: when the protocol's intervention description explicitly
states a route ("subcutaneous injection", "oral tablet", etc.),
restrict OpenFDA results to that set — skipping spurious formulations.

Per memory feedback_no_cheat_sheets.md: this is structural logic on
intervention_descs (already collected), not per-NCT shortcuts.
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


def test_protocol_routes_explicit_built():
    """The fix must compute a `protocol_routes_explicit` set from
    intervention_descs before the OpenFDA loop, populated by route
    keywords in the description text."""
    src = (PKG_ROOT / "agents" / "annotation" / "delivery_mode.py").read_text()
    idx = src.find("v42.7.23")
    block = src[idx:idx + 2500]
    assert "protocol_routes_explicit" in block, \
        "v42.7.23 trip-wire: must build protocol_routes_explicit set"
    print("  ✓ protocol_routes_explicit set built from intervention_descs")


def _make_proto_result(citations, interventions, arm_groups, openfda_results=None):
    """Helper to build a ResearchResult with optional openfda_results raw_data."""
    from app.models.research import ResearchResult, SourceCitation
    real_citations = [
        SourceCitation(source_name=c["source_name"], snippet=c["snippet"])
        for c in citations
    ]
    raw_data = {
        "protocol_section": {
            "armsInterventionsModule": {
                "armGroups": arm_groups,
                "interventions": interventions,
            }
        }
    }
    if openfda_results is not None:
        raw_data["openfda_results"] = openfda_results
    return ResearchResult(
        agent_name="clinical_protocol",
        nct_id="NCT00000000",
        citations=real_citations,
        raw_data=raw_data,
    )


def test_semaglutide_sc_trial_skips_rybelsus_oral():
    """NCT05788965 reproduction: semaglutide subcutaneous trial.
    OpenFDA returns Ozempic (SC) AND Rybelsus (Oral) — both with
    generic_name=semaglutide. Protocol explicitly says 'subcutaneous
    injection'. v42.7.23 must skip the ORAL route from Rybelsus."""
    from agents.annotation.delivery_mode import _extract_deterministic_route

    proto_result = _make_proto_result(
        citations=[
            {
                "source_name": "clinicaltrials_gov",
                "snippet": "Arm: Semaglutide 1 mg once weekly subcutaneous injection",
            },
        ],
        interventions=[
            {
                "name": "Semaglutide",
                "type": "DRUG",
                "armGroupLabels": ["Active"],
                "description": "Semaglutide 1 mg once weekly subcutaneous injection",
            },
        ],
        arm_groups=[{"label": "Active", "type": "EXPERIMENTAL"}],
        openfda_results=[
            {
                "openfda": {
                    "generic_name": ["semaglutide"],
                    "brand_name": ["OZEMPIC"],
                    "route": ["SUBCUTANEOUS"],
                }
            },
            {
                "openfda": {
                    "generic_name": ["semaglutide"],
                    "brand_name": ["RYBELSUS"],
                    "route": ["ORAL"],
                }
            },
        ],
    )
    result = _extract_deterministic_route([proto_result])
    assert result is not None, "expected deterministic result"
    assert "Oral" not in (result.value or ""), (
        f"v42.7.23 trip-wire: Rybelsus ORAL route must be skipped when "
        f"protocol explicitly says subcutaneous. Got: {result.value!r}"
    )
    assert "Injection/Infusion" in (result.value or ""), (
        f"v42.7.23: Ozempic SC route must still fire. Got: {result.value!r}"
    )
    print(f"  ✓ semaglutide SC trial → {result.value!r} (Rybelsus oral correctly skipped)")


def test_truly_multi_route_drug_keeps_both():
    """Counter-test: when protocol mentions BOTH routes (rare, but
    legitimate), both should appear. We achieve this by NOT activating
    the gate when protocol_routes_explicit has >1 route."""
    from agents.annotation.delivery_mode import _extract_deterministic_route

    proto_result = _make_proto_result(
        citations=[
            {
                "source_name": "clinicaltrials_gov",
                "snippet": "Drug-X via subcutaneous injection on day 1; subsequent oral tablet",
            },
        ],
        interventions=[
            {
                "name": "Drug-X",
                "type": "DRUG",
                "armGroupLabels": ["Active"],
                "description": "Drug-X subcutaneous injection day 1; oral tablet days 2-7",
            },
        ],
        arm_groups=[{"label": "Active", "type": "EXPERIMENTAL"}],
        openfda_results=[
            {
                "openfda": {
                    "generic_name": ["drug-x"],
                    "route": ["SUBCUTANEOUS", "ORAL"],
                }
            },
        ],
    )
    result = _extract_deterministic_route([proto_result])
    assert result is not None
    val = result.value or ""
    assert "Injection/Infusion" in val and "Oral" in val, (
        f"v42.7.23 counter-test: truly multi-route drug must keep both. "
        f"Got: {val!r}"
    )
    print(f"  ✓ multi-route drug (proto mentions SC+Oral) → {val!r}")


def test_no_explicit_protocol_route_keeps_current_behavior():
    """Counter-test: when the protocol description doesn't mention any
    route, the OpenFDA path falls back to current behavior (add all
    OpenFDA routes). Don't break unspecified-route trials."""
    from agents.annotation.delivery_mode import _extract_deterministic_route

    proto_result = _make_proto_result(
        citations=[
            {
                "source_name": "clinicaltrials_gov",
                "snippet": "Drug-Z, an investigational therapy",
            },
        ],
        interventions=[
            {
                "name": "Drug-Z",
                "type": "DRUG",
                "armGroupLabels": ["Active"],
                "description": "Drug-Z, an investigational therapy",  # no route
            },
        ],
        arm_groups=[{"label": "Active", "type": "EXPERIMENTAL"}],
        openfda_results=[
            {
                "openfda": {
                    "generic_name": ["drug-z"],
                    "route": ["SUBCUTANEOUS"],
                }
            },
        ],
    )
    result = _extract_deterministic_route([proto_result])
    assert result is not None
    assert "Injection/Infusion" in (result.value or ""), (
        f"v42.7.23 counter-test: when protocol omits route, OpenFDA "
        f"path should still add SC. Got: {result.value!r}"
    )
    print(f"  ✓ no-explicit-route case → {result.value!r} (OpenFDA fallback intact)")


def main() -> int:
    print("v42.7.23 OpenFDA multi-formulation route-gate tests")
    print("-" * 60)
    tests = [
        test_v42_7_23_marker_present,
        test_protocol_routes_explicit_built,
        test_semaglutide_sc_trial_skips_rybelsus_oral,
        test_truly_multi_route_drug_keeps_both,
        test_no_explicit_protocol_route_keeps_current_behavior,
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

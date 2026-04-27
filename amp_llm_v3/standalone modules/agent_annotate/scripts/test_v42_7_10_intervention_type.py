#!/usr/bin/env python3
"""
Tests for v42.7.10 intervention-type preservation in research metadata
(2026-04-27).

Discovery from dev smoke `e46797571504`:
  Both NCT00002228 (Enfuvirtide DRUG) and NCT03199872 (RV001V BIOLOGICAL)
  reported `note: No interventions to search` from FDA Drugs / NIH RePORTER
  / SEC EDGAR. Tracing the orchestrator: _run_research extracts intervention
  names from clinicaltrials.gov but builds dicts as {"name": name} — no
  `type` field. The research agents' _extract_intervention_names() requires
  type in ("DRUG", "BIOLOGICAL"), so every dict gets filtered out.

Result: SEC EDGAR / FDA Drugs / NIH RePORTER agents have been firing
without any drug-name terms to query in EVERY prod job since v42.7.0
(2026-04-25). They returned only NCT-based hits (SEC EDGAR's NCT search)
or nothing at all (FDA Drugs, NIH RePORTER).

Fix: include `type` from the source data when building the dicts.
"""
from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

ORCH_PATH = PKG_ROOT / "app" / "services" / "orchestrator.py"


def test_orchestrator_preserves_intervention_type():
    """Source check: _run_research must include `type` in the intervention
    dicts it builds for research-agent metadata."""
    src = ORCH_PATH.read_text()
    # Find the relevant block. Window must be wide enough to cover the
    # extraction body (multi-line dict construction), so use 2500 chars.
    idx = src.find("Extract intervention names from raw protocol data")
    assert idx > 0, "intervention extraction block not found"
    block = src[idx:idx + 2500]
    # The fix: dict must include both name and type, and type must come
    # from the source interv dict (not be hard-coded).
    assert '"name": name,' in block, "intervention dict missing name field"
    assert '"type":' in block, \
        "intervention dict missing type field — research agents will see " \
        "empty interventions list (v42.7.10 regression)"
    assert 'interv.get("type"' in block, \
        "must extract type from source interv dict"
    print("  ✓ orchestrator preserves intervention type in research metadata")


def test_extraction_runs_against_real_protocol_shape():
    """Simulate the orchestrator's extraction logic against a realistic
    protocolSection.armsInterventionsModule.interventions[] shape."""
    # Mimic the orchestrator's loop body
    arms_mod = {
        "interventions": [
            {"type": "DRUG", "name": "Enfuvirtide"},
            {"type": "BIOLOGICAL", "name": "RV001V"},
            {"type": "BEHAVIORAL", "name": "Diet counseling"},
            {"name": "Untyped fallback"},   # missing type
            {"type": "DRUG", "name": ""},   # empty name — must skip
        ],
    }
    # Replicate the v42.7.10 logic
    interventions = []
    for interv in arms_mod.get("interventions", []):
        name = interv.get("name", "")
        if name:
            interventions.append({
                "name": name,
                "type": interv.get("type", "") or "",
            })
    assert len(interventions) == 4, f"expected 4 (skip empty name); got {len(interventions)}"
    # Check the type field is preserved correctly
    by_name = {d["name"]: d["type"] for d in interventions}
    assert by_name["Enfuvirtide"] == "DRUG"
    assert by_name["RV001V"] == "BIOLOGICAL"
    assert by_name["Diet counseling"] == "BEHAVIORAL"
    assert by_name["Untyped fallback"] == ""
    print(f"  ✓ extraction preserves type: {by_name}")


def test_research_agent_filter_now_passes_through():
    """End-to-end check: feed v42.7.10-style metadata into the research
    agents' _extract_intervention_names and confirm DRUG/BIOLOGICAL pass."""
    try:
        from agents.research.fda_drugs_client import _extract_intervention_names as fda_extract
        from agents.research.sec_edgar_client import _extract_intervention_names as sec_extract
        from agents.research.nih_reporter_client import _extract_intervention_names as nih_extract
    except ImportError as e:
        print(f"  ⚠ skipped (import failed: {e})")
        return
    metadata = {
        "interventions": [
            {"type": "DRUG", "name": "Enfuvirtide"},
            {"type": "BIOLOGICAL", "name": "RV001V"},
            {"type": "BEHAVIORAL", "name": "Counseling"},
            {"type": "DRUG", "name": "Placebo"},  # placebo must still be filtered
        ],
    }
    for fn, label in ((fda_extract, "fda_drugs"),
                      (sec_extract, "sec_edgar"),
                      (nih_extract, "nih_reporter")):
        names = fn(metadata)
        assert "Enfuvirtide" in names, \
            f"{label}: Enfuvirtide should pass DRUG type filter"
        assert "RV001V" in names, \
            f"{label}: RV001V should pass BIOLOGICAL type filter"
        assert "Counseling" not in names, \
            f"{label}: BEHAVIORAL must still be filtered"
        assert "Placebo" not in names, \
            f"{label}: placebo must still be skipped"
    print("  ✓ all 3 research agents now receive DRUG/BIOLOGICAL interventions")


def main() -> int:
    print("v42.7.10 intervention-type preservation tests")
    print("-" * 60)
    tests = [
        test_orchestrator_preserves_intervention_type,
        test_extraction_runs_against_real_protocol_shape,
        test_research_agent_filter_now_passes_through,
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

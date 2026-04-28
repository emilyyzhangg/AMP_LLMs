#!/usr/bin/env python3
"""Tests for v42.7.19 — delivery_mode ambiguous-keyword relevance gate.

Job #92/#95/#96/#97 surfaced 6 distinct NCTs (across 4 held-out slices)
where the deterministic delivery collector emitted "Injection/Infusion,
Oral" when GT was single-route "Injection/Infusion". Root cause: the
protocol-keyword scan added "Oral" because of "tablet"/"capsule"
appearances in citations that DID NOT describe the experimental arm —
typically FDA Drugs returns for similarly-named approved drugs that
have an oral formulation (INQOVI for decitabine, TEMOZOLOMIDE for
peptide-vaccine trials, Metformin for biologics), or OpenAlex
publications about tangentially-related topics.

The OpenFDA path (lines 343-356) already has an intervention-name
relevance gate. The protocol-keyword scan (lines 386-403) does not.
v42.7.19 adds that gate for the small set of ambiguous keywords
(tablet, capsule) where false-positive risk is highest.

Per memory `feedback_no_cheat_sheets.md`: this is logic improvement,
not a per-NCT shortcut. The fix is gated on a property of the citation
(does it mention any experimental intervention name?), not on specific
drug names.
"""
from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))


def test_v42_7_19_marker_present():
    src = (PKG_ROOT / "agents" / "annotation" / "delivery_mode.py").read_text()
    assert "v42.7.19" in src, "v42.7.19 marker missing in delivery_mode.py"
    print("  ✓ v42.7.19 marker present in delivery_mode.py")


def test_ambiguous_keyword_relevance_gate_exists():
    """The protocol-keyword scan must skip ambiguous keywords (tablet/
    capsule) when the citation snippet doesn't mention any experimental
    intervention name. The gate must be inside the existing scan loop,
    not a separate function call."""
    src = (PKG_ROOT / "agents" / "annotation" / "delivery_mode.py").read_text()
    # Look for the new sentinel comment
    assert "ambiguous-keyword relevance gate" in src.lower() or \
           "v42.7.19" in src, \
           "v42.7.19 trip-wire: relevance-gate sentinel comment missing"
    # The gate must check intervention_names against snippet_lower
    # AND only fire on _AMBIGUOUS_KEYWORDS members. Use a generous window
    # since the explanatory comment + the gate logic span ~30 lines.
    idx = src.find("v42.7.19")
    block = src[idx:idx + 2500]
    assert "_AMBIGUOUS_KEYWORDS" in block, \
        "v42.7.19 trip-wire: relevance gate must reference _AMBIGUOUS_KEYWORDS"
    assert "intervention_names" in block, \
        "v42.7.19 trip-wire: relevance gate must check intervention_names"
    # Pin the specific structural pattern: a check `keyword in
    # _AMBIGUOUS_KEYWORDS and not citation_mentions_experimental` (or a
    # functionally identical short-circuit using the same identifiers).
    assert "citation_mentions_experimental" in block, \
        "v42.7.19 trip-wire: gate uses citation_mentions_experimental flag"
    print("  ✓ ambiguous-keyword relevance gate references _AMBIGUOUS_KEYWORDS + intervention_names + citation_mentions_experimental")


def _make_proto_result(citations, interventions, arm_groups):
    """Helper to build a ResearchResult with real pydantic citation models.

    delivery_mode.py reads `getattr(citation, "section_name", "")` for
    the title-citation check; an empty string is the production default
    (no real research client sets section_name on the citation model).
    """
    from app.models.research import ResearchResult, SourceCitation

    real_citations = [
        SourceCitation(source_name=c["source_name"], snippet=c["snippet"])
        for c in citations
    ]
    return ResearchResult(
        agent_name="clinical_protocol",
        nct_id="NCT00000000",
        citations=real_citations,
        raw_data={
            "protocol_section": {
                "armsInterventionsModule": {
                    "armGroups": arm_groups,
                    "interventions": interventions,
                }
            }
        },
    )


def test_extract_deterministic_route_filters_unrelated_capsule_citation():
    """Synthetic test: a placebo-only citation that mentions 'capsules'
    must NOT add Oral when the experimental intervention name doesn't
    appear in the snippet.
    """
    from agents.annotation.delivery_mode import _extract_deterministic_route

    # Reproduces NCT01704781 (Job #97): the experimental arm is Vacc-4X
    # intradermal; placebo-comparator citation mentions "capsules" but
    # not the experimental intervention name. Only the ambiguous keyword
    # "capsule" should match here — no longer-form Oral keywords
    # ("oral tablet", "oral capsule", etc.) are present, so the relevance
    # gate must catch it.
    proto_result = _make_proto_result(
        citations=[
            {
                "source_name": "clinicaltrials_gov",
                "snippet": "Vacc-4X is administered intradermally as a peptide HIV immunotherapy.",
            },
            {
                "source_name": "clinicaltrials_gov",
                "snippet": "Lenalidomide placebo - Capsules are identical to the active capsules used.",
            },
        ],
        interventions=[
            {
                "name": "Vacc-4X",
                "type": "BIOLOGICAL",
                "armGroupLabels": ["Active"],
                "description": "Vacc-4X is administered intradermally.",
            },
        ],
        arm_groups=[
            {"label": "Active", "type": "EXPERIMENTAL"},
        ],
    )
    result = _extract_deterministic_route([proto_result])
    assert result is not None, "expected a deterministic result"
    assert "Oral" not in (result.value or ""), (
        f"v42.7.19 trip-wire: 'Oral' must not be added from a placebo "
        f"citation that mentions 'capsule' but not the experimental "
        f"intervention (Vacc-4X). Got value={result.value!r}"
    )
    print(f"  ✓ placebo-only capsule citation correctly does NOT add Oral; got value={result.value!r}")


def test_extract_deterministic_route_keeps_legitimate_oral():
    """Counter-test: when an experimental intervention name DOES appear
    in a citation that mentions 'oral', the Oral route must still be
    added. This guards against the gate being too aggressive."""
    from agents.annotation.delivery_mode import _extract_deterministic_route

    proto_result = _make_proto_result(
        citations=[
            {
                "source_name": "clinicaltrials_gov",
                "snippet": "Drug-X is administered as an oral tablet, taken twice daily.",
                "section_name": "armsInterventionsModule",
            },
        ],
        interventions=[
            {
                "name": "Drug-X",
                "type": "DRUG",
                "armGroupLabels": ["Active"],
                "description": "Oral tablet.",
            },
        ],
        arm_groups=[
            {"label": "Active", "type": "EXPERIMENTAL"},
        ],
    )
    result = _extract_deterministic_route([proto_result])
    assert result is not None
    assert "Oral" in (result.value or ""), (
        f"v42.7.19 counter-test: legitimate Oral route must still be "
        f"added when experimental intervention name appears in citation. "
        f"Got value={result.value!r}"
    )
    print(f"  ✓ legitimate Oral route preserved; got value={result.value!r}")


def test_non_ambiguous_keywords_unaffected():
    """Counter-test: non-ambiguous keywords (subcutaneous, intravenous)
    must NOT be subject to the new relevance gate — those keywords are
    specific enough that any citation mentioning them is signal."""
    src = (PKG_ROOT / "agents" / "annotation" / "delivery_mode.py").read_text()
    # Verify the gate only fires when keyword is in _AMBIGUOUS_KEYWORDS.
    # We look for the literal pattern: "in _AMBIGUOUS_KEYWORDS" near the
    # v42.7.19 block.
    idx = src.find("v42.7.19")
    block = src[idx:idx + 1500]
    assert "in _AMBIGUOUS_KEYWORDS" in block, \
        "v42.7.19: gate must restrict to _AMBIGUOUS_KEYWORDS members only"
    print("  ✓ relevance gate restricted to _AMBIGUOUS_KEYWORDS members (subcutaneous/intravenous unaffected)")


def main() -> int:
    print("v42.7.19 delivery_mode ambiguous-keyword relevance tests")
    print("-" * 60)
    tests = [
        test_v42_7_19_marker_present,
        test_ambiguous_keyword_relevance_gate_exists,
        test_extract_deterministic_route_filters_unrelated_capsule_citation,
        test_extract_deterministic_route_keeps_legitimate_oral,
        test_non_ambiguous_keywords_unaffected,
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

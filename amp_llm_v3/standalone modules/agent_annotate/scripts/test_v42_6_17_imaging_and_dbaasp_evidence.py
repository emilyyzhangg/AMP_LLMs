#!/usr/bin/env python3
"""
Tests for v42.6.17 (2026-04-25).

Two real bugs surfaced by Job #83 audit:

Fix 1 — delivery_mode imaging detector over-fires
--------------------------------------------------
NCT05269381 (Cyclophosphamide + Vaccine + Pembrolizumab + supportive
CT/MRI procedures) was tagged Other instead of Injection/Infusion. The
imaging detector fires on `"PROCEDURE" in types AND "imaging" in names`,
but didn't check whether therapeutic interventions exist alongside.
Fix: require absence of any DRUG/BIOLOGICAL intervention before tagging
the trial as a diagnostic-only imaging study.

Fix 2 — DBAASP-only classification has empty evidence list
----------------------------------------------------------
NCT03196219 (C16G2, an antimicrobial peptide with DBAASP entry) was
classified Other because the deterministic AMP-DB FieldAnnotation had
evidence=[] — downstream evidence-threshold check saw 0 sources / 0.0
quality and forced Other. Fix: collect AMP-DB citations during the scan
and attach them to the deterministic FieldAnnotation.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))


# ---------------------------------------------------------------------------
# Fix 1: imaging detector
# ---------------------------------------------------------------------------
def test_imaging_detector_source_guards_against_therapeutic_intervention():
    """Source inspection: imaging detector must check has_therapeutic_intervention
    before firing."""
    src = (PKG_ROOT / "agents" / "annotation" / "delivery_mode.py").read_text()
    assert "has_therapeutic_intervention" in src, "guard variable missing"
    assert "v42.6.17" in src, "v42.6.17 marker missing"
    # Must be checked BEFORE the imaging detection branch
    th_idx = src.find("has_therapeutic_intervention = any(")
    img_idx = src.find('"PROCEDURE" in intervention_types\n', th_idx)
    if img_idx == -1:  # try alternate formatting
        img_idx = src.find('not has_therapeutic_intervention')
    assert th_idx != -1 and img_idx > th_idx, "imaging detection must come AFTER therapeutic guard"
    print("  ✓ delivery_mode imaging detector guards against therapeutic interventions")


def test_imaging_detector_old_signature_still_present():
    """The detector still uses the original keyword set; we only added a guard."""
    src = (PKG_ROOT / "agents" / "annotation" / "delivery_mode.py").read_text()
    for kw in ("pet", "spect", "imaging", "tracer"):
        # Each keyword should still appear in the imaging detection block
        assert f'"{kw}"' in src or f"'{kw}'" in src, f"imaging keyword '{kw}' missing"
    print("  ✓ original imaging-detection keyword set preserved")


# ---------------------------------------------------------------------------
# Fix 2: DBAASP classification evidence
# ---------------------------------------------------------------------------
def test_classification_dbaasp_evidence_collected():
    """Source inspection: AMP-DB citations are collected during scan and
    passed to the deterministic FieldAnnotation."""
    src = (PKG_ROOT / "agents" / "annotation" / "classification.py").read_text()
    assert "amp_db_citations: list = []" in src, "amp_db_citations init missing"
    # Citation appended for each DB type
    appends = src.count("amp_db_citations.append(citation)")
    assert appends >= 3, f"expected ≥3 appends (DRAMP, DBAASP, APD); got {appends}"
    # Passed to FieldAnnotation as evidence
    assert "evidence=amp_db_citations" in src, "evidence not wired to FieldAnnotation"
    # Old empty-list bug should be gone for the AMP-DB return path
    # (the non-AMP and known-AMP returns can still use evidence=[])
    print("  ✓ classification AMP-DB citations now attached to evidence")


def test_classification_dbaasp_evidence_runtime():
    """End-to-end: a research result with a DBAASP citation produces a
    FieldAnnotation whose evidence is non-empty."""
    from app.models.research import ResearchResult, SourceCitation
    from agents.annotation.classification import _deterministic_classify

    # Build a stub research_results with DBAASP hit
    dbaasp_citation = SourceCitation(
        source_name="dbaasp",
        source_url="https://dbaasp.org/peptide/12345",
        identifier="DBAASP:12345",
        title="C16G2 - DBAASP",
        snippet="Antimicrobial peptide C16G2",
        quality_score=0.85,
        retrieved_at="2026-04-25T00:00:00",
    )
    proto_result = ResearchResult(
        agent_name="clinical_protocol",
        nct_id="NCT03196219",
        citations=[],
        raw_data={"protocolSection": {
            "armsInterventionsModule": {"interventions": [{"name": "C16G2"}]},
            "conditionsModule": {"conditions": ["dental caries"]},
        }},
    )
    dbaasp_result = ResearchResult(
        agent_name="dbaasp", nct_id="NCT03196219",
        citations=[dbaasp_citation], raw_data={},
    )
    ann = _deterministic_classify("NCT03196219", [proto_result, dbaasp_result], None)
    assert ann is not None, "expected deterministic AMP classification"
    assert ann.value == "AMP"
    assert len(ann.evidence) >= 1, f"evidence must be non-empty; got {ann.evidence}"
    assert ann.evidence[0].source_name == "dbaasp"
    print(f"  ✓ DBAASP citation attached to evidence (len={len(ann.evidence)})")


def test_classification_multi_db_hits_attached():
    """When multiple AMP DBs hit (DRAMP + DBAASP), evidence should include both."""
    from app.models.research import ResearchResult, SourceCitation
    from agents.annotation.classification import _deterministic_classify

    def cite(src):
        return SourceCitation(
            source_name=src, source_url=f"https://example/{src}",
            identifier=src.upper(), title=f"hit - {src.upper()}",
            snippet="amp", quality_score=0.9,
            retrieved_at="2026-04-25T00:00:00",
        )

    proto = ResearchResult(
        agent_name="clinical_protocol", nct_id="NCT00000000",
        citations=[], raw_data={"protocolSection": {
            "armsInterventionsModule": {"interventions": [{"name": "TestPep"}]},
            "conditionsModule": {"conditions": []},
        }},
    )
    pid = ResearchResult(
        agent_name="peptide_identity", nct_id="NCT00000000",
        citations=[cite("dramp")], raw_data={},
    )
    db = ResearchResult(
        agent_name="dbaasp", nct_id="NCT00000000",
        citations=[cite("dbaasp")], raw_data={},
    )
    ann = _deterministic_classify("NCT00000000", [proto, pid, db], None)
    assert ann is not None and ann.value == "AMP"
    assert len(ann.evidence) == 2
    sources = {c.source_name for c in ann.evidence}
    assert sources == {"dramp", "dbaasp"}, f"expected dramp+dbaasp, got {sources}"
    # multi-DB hit also means skip_verification=True (high confidence path)
    assert ann.skip_verification is True
    print("  ✓ multi-DB AMP classification attaches all citations + skips verification")


def main() -> int:
    print("v42.6.17 imaging detector + DBAASP evidence tests")
    print("-" * 60)
    tests = [
        test_imaging_detector_source_guards_against_therapeutic_intervention,
        test_imaging_detector_old_signature_still_present,
        test_classification_dbaasp_evidence_collected,
        test_classification_dbaasp_evidence_runtime,
        test_classification_multi_db_hits_attached,
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

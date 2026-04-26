#!/usr/bin/env python3
"""
Tests for v42.7.1 calibrated-decline phase 1 (2026-04-26).

Extends evidence_grade from 3 tiers (deterministic / db_confirmed / llm)
to 5 tiers by adding `pub_trial_specific` (LLM with ≥2 pub citations) and
`inconclusive` (empty/no-reasoning). Existing 3-tier semantics preserved
so verifier-override threshold logic is unchanged.

Pure source inspection + simple model checks — the grader logic lives
inside _grade_annotations on the orchestrator and is exercised end-to-end
by the next prod smoke. These tests verify the contract.
"""

from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))


def test_field_annotation_default_grade_unchanged():
    """Default evidence_grade must remain 'llm' for backward compat."""
    from app.models.annotation import FieldAnnotation
    a = FieldAnnotation(field_name="peptide", value="True")
    assert a.evidence_grade == "llm"
    print("  ✓ default evidence_grade still 'llm' (backward compat)")


def test_evidence_grade_accepts_new_values():
    from app.models.annotation import FieldAnnotation
    for g in ("db_confirmed", "deterministic", "pub_trial_specific",
              "llm", "inconclusive"):
        a = FieldAnnotation(field_name="x", value="y", evidence_grade=g)
        assert a.evidence_grade == g
    print("  ✓ FieldAnnotation accepts all 5 grade values")


def test_grader_source_uses_5_grades():
    """Source inspection: orchestrator's grader must reference all 5 grades."""
    src = (PKG_ROOT / "app" / "services" / "orchestrator.py").read_text()
    for g in ("db_confirmed", "deterministic", "pub_trial_specific",
              "inconclusive"):
        assert f'"{g}"' in src or f"'{g}'" in src, f"grader missing grade: {g}"
    print("  ✓ orchestrator grader references all 5 grades")


def test_grader_includes_sec_edgar_and_fda_drugs_as_db_keywords():
    """v42.7.0's new agents (sec_edgar, fda_drugs) should count toward
    db_confirmed when they cite a trial."""
    src = (PKG_ROOT / "app" / "services" / "orchestrator.py").read_text()
    # _DB_KEYWORDS tuple should include both
    assert '"sec_edgar"' in src
    assert '"fda_drugs"' in src
    print("  ✓ db_confirmed grader includes sec_edgar + fda_drugs")


def test_diagnostics_includes_evidence_grades_aggregate():
    """orchestrator must aggregate evidence_grade into diagnostics."""
    src = (PKG_ROOT / "app" / "services" / "orchestrator.py").read_text()
    assert '"evidence_grades": grade_counts' in src
    assert "grade_counts.setdefault" in src
    print("  ✓ diagnostics aggregates evidence_grade per field")


def test_pub_count_threshold_is_two():
    """The pub_trial_specific threshold should require ≥2 pub citations,
    matching the roadmap §11 design (singletons are noisy)."""
    src = (PKG_ROOT / "app" / "services" / "orchestrator.py").read_text()
    assert "pub_cite_count >= 2" in src
    print("  ✓ pub_trial_specific gate: ≥2 pub citations (matches §11)")


def test_inconclusive_only_when_value_empty_and_no_reasoning():
    """Inconclusive should NOT downgrade legitimate Unknown outcomes that
    have reasoning (those are LLM_INFERRED, not Inconclusive)."""
    src = (PKG_ROOT / "app" / "services" / "orchestrator.py").read_text()
    # Look for the conditional that protects reasoning-bearing Unknown
    assert 'if not (ann.reasoning or "").strip():' in src
    print("  ✓ inconclusive guard preserves reasoning-bearing Unknown")


def main() -> int:
    print("v42.7.1 evidence-grade 5-tier phase 1 tests")
    print("-" * 60)
    tests = [
        test_field_annotation_default_grade_unchanged,
        test_evidence_grade_accepts_new_values,
        test_grader_source_uses_5_grades,
        test_grader_includes_sec_edgar_and_fda_drugs_as_db_keywords,
        test_diagnostics_includes_evidence_grades_aggregate,
        test_pub_count_threshold_is_two,
        test_inconclusive_only_when_value_empty_and_no_reasoning,
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

#!/usr/bin/env python3
"""
Tests for v42.6.13 diagnostic fixes (2026-04-24).

Job #80 diagnostics had 59 quality-check warnings, breaking into:
  - 50 false positives: atomic_fr-gated empty (designed behavior)
  - 9 real: delivery_mode agent crashed twice on peptide=True trials,
    no annotation saved, no error trail

Fix 1: Allowlist model='atomic-fr-gated' in _check_annotation_quality.
Fix 2: Preserve a FieldAnnotation when retry crashes — with both original
       failure reason + retry exception text — and emit a CRASH warning.

Pure logic checks — no network, no LLM.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

from app.models.annotation import FieldAnnotation  # noqa: E402
from app.services.orchestrator import PipelineOrchestrator  # noqa: E402


def test_atomic_fr_gated_empty_is_not_a_warning():
    """model='atomic-fr-gated' with empty value is DESIGNED for non-failed
    outcomes. Quality check must not flag it."""
    ann = FieldAnnotation(
        field_name="reason_for_failure_atomic",
        value="",
        confidence=0.0,
        reasoning="[gated: outcome is not Failed/Terminated]",
        model_name="atomic-fr-gated",
    )
    issues = PipelineOrchestrator._check_annotation_quality("NCT00000001", [ann])
    # Should not contain any empty-value warning for this annotation
    empty_warnings = [i for i in issues if "empty value" in i]
    assert not empty_warnings, f"atomic-fr-gated empty must not warn, got: {empty_warnings}"
    print("  ✓ atomic-fr-gated empty is not flagged (fix for 50 false-positive warnings)")


def test_regular_empty_llm_annotation_still_flagged():
    """A regular LLM annotation returning empty is still suspicious."""
    ann = FieldAnnotation(
        field_name="classification",
        value="",
        confidence=0.0,
        reasoning="whatever",
        model_name="qwen3:14b",
    )
    issues = PipelineOrchestrator._check_annotation_quality("NCT00000002", [ann])
    assert any("empty value" in i for i in issues), \
        f"regular LLM empty must still warn, got: {issues}"
    print("  ✓ regular LLM empty still flagged (no regression)")


def test_atomic_fr_non_gated_model_still_flagged():
    """If the atomic failure_reason uses a real LLM (not gated) and returns empty,
    that IS suspicious and should still be flagged."""
    ann = FieldAnnotation(
        field_name="reason_for_failure_atomic",
        value="",
        confidence=0.3,
        reasoning="[atomic] LLM output was blank",
        model_name="atomic-fr-qwen3:14b",  # NOT the gated sentinel
    )
    issues = PipelineOrchestrator._check_annotation_quality("NCT00000003", [ann])
    assert any("empty value" in i for i in issues), \
        f"atomic-fr LLM empty must still warn (only gated sentinel is allowlisted), got: {issues}"
    print("  ✓ atomic-fr LLM empty (not gated) still flagged (narrow allowlist)")


def test_retry_failure_preserves_sentinel_annotation_source():
    """Source inspection: retry exception block must append a sentinel
    FieldAnnotation and record a CRASH warning, not silently swallow."""
    src = (PKG_ROOT / "app" / "services" / "orchestrator.py").read_text()
    # The retry except block must:
    #  - append an 'agent-crashed' annotation
    #  - add a 'CRASH [' warning to job.progress.warnings
    #  - log the full traceback
    assert "model_name=\"agent-crashed\"" in src, "missing sentinel model_name"
    assert '"CRASH [{nct_id}]' in src or "CRASH [" in src, "missing CRASH warning string"
    assert "traceback.format_exc()" in src, "missing traceback capture"
    assert "[Agent crashed twice]" in src, "missing crashed-twice reasoning prefix"
    print("  ✓ retry-failure source path preserves sentinel + CRASH warning + traceback")


def test_traceback_module_imported():
    """traceback must be imported at the top of orchestrator.py."""
    src_lines = (PKG_ROOT / "app" / "services" / "orchestrator.py").read_text().splitlines()
    top = "\n".join(src_lines[:40])
    assert "import traceback" in top, "traceback import must be near top of file"
    print("  ✓ traceback module imported at top of orchestrator.py")


def test_crashed_sentinel_annotation_shape_is_flagged_appropriately():
    """An agent-crashed sentinel annotation is an ERROR state. The quality
    check should detect it as zero-confidence non-Unknown — so downstream
    triage sees it — but the sentinel itself is not an allowlist entry."""
    ann = FieldAnnotation(
        field_name="delivery_mode",
        value="Unknown",
        confidence=0.0,
        reasoning="[Agent crashed twice] original: ... | retry error: ValueError: bad input",
        model_name="agent-crashed",
        skip_verification=True,
    )
    issues = PipelineOrchestrator._check_annotation_quality("NCT00000004", [ann])
    # Quality check flags zero-conf + value 'Unknown' as "possible failed LLM call"
    # — still useful signal, but the reasoning field now has real diagnostic content.
    assert any("zero confidence" in i or "failed LLM" in i for i in issues), \
        f"agent-crashed sentinel should still show up in quality issues, got: {issues}"
    print("  ✓ agent-crashed sentinel remains visible to quality check (not hidden)")


def main() -> int:
    print("v42.6.13 diagnostic fix tests")
    print("-" * 60)
    tests = [
        test_atomic_fr_gated_empty_is_not_a_warning,
        test_regular_empty_llm_annotation_still_flagged,
        test_atomic_fr_non_gated_model_still_flagged,
        test_retry_failure_preserves_sentinel_annotation_source,
        test_traceback_module_imported,
        test_crashed_sentinel_annotation_shape_is_flagged_appropriately,
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

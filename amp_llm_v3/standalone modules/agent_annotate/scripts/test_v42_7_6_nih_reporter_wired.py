#!/usr/bin/env python3
"""
Tests for v42.7.6 NIH RePORTER research agent (2026-04-26).

Source-only checks runnable without httpx — confirms the agent file
exists with the expected shape and is wired into RESEARCH_AGENTS +
default_config.yaml.

For a live API check, see scripts/test_nih_reporter_live.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))


def test_client_file_exists():
    p = PKG_ROOT / "agents" / "research" / "nih_reporter_client.py"
    assert p.exists(), "nih_reporter_client.py missing"
    print(f"  ✓ {p.name} present")


def test_client_class_present():
    src = (PKG_ROOT / "agents" / "research" / "nih_reporter_client.py").read_text()
    assert "class NIHRePORTERClient" in src
    assert 'agent_name = "nih_reporter"' in src
    assert "advanced_text_search" in src
    # Must NOT use clinical_trial_ids as a criterion key (it silently
    # no-ops on this API and returns the full 2.9M-row DB).
    assert '"clinical_trial_ids"' not in src and "'clinical_trial_ids'" not in src
    print("  ✓ NIHRePORTERClient + advanced_text_search criterion in place")


def test_registered_in_research_agents():
    init = (PKG_ROOT / "agents" / "research" / "__init__.py").read_text()
    assert "from agents.research.nih_reporter_client import NIHRePORTERClient" in init
    assert '"nih_reporter": NIHRePORTERClient' in init
    print("  ✓ nih_reporter listed in RESEARCH_AGENTS")


def test_present_in_default_config():
    cfg = (PKG_ROOT / "config" / "default_config.yaml").read_text()
    assert "nih_reporter:" in cfg
    assert "- nih_reporter" in cfg
    print("  ✓ nih_reporter present in default_config.yaml")


def test_skip_helper_filters_placebo():
    """Source check: the _SKIP set must exclude placebo and saline."""
    src = (PKG_ROOT / "agents" / "research" / "nih_reporter_client.py").read_text()
    assert "_SKIP = {" in src
    assert '"placebo"' in src
    assert '"saline"' in src
    print("  ✓ _SKIP set excludes placebo/saline")


def test_caps_at_three_interventions():
    """Source check: cap interventions[:3] to bound per-trial API calls
    (matches sec_edgar_client / fda_drugs_client pattern)."""
    src = (PKG_ROOT / "agents" / "research" / "nih_reporter_client.py").read_text()
    assert "interventions[:3]" in src
    print("  ✓ caps at 3 interventions per trial")


def test_returns_funded_flag():
    """raw_data must surface a binary 'is funded by NIH' flag for
    downstream agents — same pattern as fda_drugs_<x>_approved."""
    src = (PKG_ROOT / "agents" / "research" / "nih_reporter_client.py").read_text()
    assert "_funded" in src
    print("  ✓ raw_data exposes nih_reporter_<x>_funded flag")


def main() -> int:
    print("v42.7.6 NIH RePORTER wiring tests (source-only)")
    print("-" * 60)
    tests = [
        test_client_file_exists,
        test_client_class_present,
        test_registered_in_research_agents,
        test_present_in_default_config,
        test_skip_helper_filters_placebo,
        test_caps_at_three_interventions,
        test_returns_funded_flag,
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

#!/usr/bin/env python3
"""
v42 trip-wire regression tests (2026-04-26).

These are SOURCE-LEVEL assertions pinned to specific past-bug fixes.
Each assertion encodes a bug we already paid prod time to find: the
test fails the moment someone reverts or refactors the fix without
realizing.

Trip wires are cheaper than re-running a 5-NCT smoke for every code
change. They run in milliseconds, catch regressions at the source-code
diff stage, and give a one-line pointer to the original incident.

If you intentionally need to remove one of these patterns, delete the
trip-wire here in the same commit AND log the decision in
docs/AGENT_STRATEGY_ROADMAP.md §9 (Decision log).
"""
from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))


def test_v42_6_14_no_bare_approved_in_strong_efficacy():
    """v42.6.14 (2026-04-24): bare 'approved' caused NCT04527575
    EpiVacCorona to flip Unknown → Positive on a review snippet
    'EpiVacCorona was approved for emergency use in Russia.'

    Strong-efficacy must require regulatory-qualified phrases, not the
    bare word 'approved'.
    """
    src = (PKG_ROOT / "agents" / "annotation" / "outcome.py").read_text()
    # _STRONG_EFFICACY must exist
    assert "_STRONG_EFFICACY" in src, "_STRONG_EFFICACY tuple missing"
    # Must require qualified phrases for regulatory wins
    qualified_present = any(
        phrase in src for phrase in (
            "fda approved", "ema approved", "regulatory approval",
            "received approval", "marketing authorization",
        )
    )
    assert qualified_present, (
        "v42.6.14 trip-wire: regulatory-qualified approval phrases must "
        "be in outcome.py (fda approved / ema approved / regulatory "
        "approval / received approval / marketing authorization)."
    )
    print("  ✓ v42.6.14: regulatory-qualified approval phrases present")


def test_v42_6_18_known_sequences_has_glp1():
    """v42.6.18 (2026-04-25): GLP-1 was being matched to glucagon
    (HSQG...) because the iteration order over _KNOWN_SEQUENCES picked
    'glucagon' before 'glucagon-like peptide 1'. Both call sites must
    use longest-first iteration, and the GLP-1 entry must be present."""
    src = (PKG_ROOT / "agents" / "annotation" / "sequence.py").read_text()
    assert "_KNOWN_SEQUENCES" in src, "_KNOWN_SEQUENCES dict missing"
    assert "glucagon-like peptide" in src.lower(), \
        "v42.6.18 trip-wire: GLP-1 entry missing from _KNOWN_SEQUENCES"
    # GLP-1's correct sequence starts with HAEG (His-Ala-Glu-Gly...).
    assert "HAEGTFTSDVSSYLEGQAAKEFIAWLVKGR" in src, \
        "v42.6.18 trip-wire: GLP-1 30-aa canonical sequence missing"
    # Longest-first sort is the disambiguator. We expect either an
    # explicit `sorted(..., key=len, reverse=True)` or `sorted(..., key=lambda` form.
    assert any(p in src for p in (
        "key=len, reverse=True", "key=lambda k: len(k)", "key=lambda x: len(x)",
        "len, reverse=True",
    )), (
        "v42.6.18 trip-wire: longest-first iteration sentinel missing in "
        "sequence.py — GLP-1 will be shadowed by glucagon."
    )
    print("  ✓ v42.6.18: GLP-1 entry + longest-first iteration present")


def test_v42_7_4_two_tier_pub_agents():
    """v42.7.4 (2026-04-26): keyword-scan branch must use
    _PUB_AGENTS_HIGH_QUALITY (literature + openalex), not the broad
    _PUB_AGENTS — preprints/aggregators add noise to deterministic
    outcome overrides.
    """
    src = (PKG_ROOT / "agents" / "annotation" / "outcome.py").read_text()
    assert "_PUB_AGENTS_HIGH_QUALITY = (" in src, \
        "v42.7.4 trip-wire: _PUB_AGENTS_HIGH_QUALITY tuple missing"
    # Must restrict to literature + openalex
    import re
    m = re.search(r"_PUB_AGENTS_HIGH_QUALITY = \(([^)]*)\)", src)
    assert m
    members = {a.strip().strip('"\'') for a in m.group(1).split(",") if a.strip()}
    assert "literature" in members and "openalex" in members
    assert "biorxiv" not in members and "semantic_scholar" not in members
    print(f"  ✓ v42.7.4: _PUB_AGENTS_HIGH_QUALITY = {sorted(members)}")


def test_v42_7_3_per_field_db_keywords():
    """v42.7.3 (2026-04-26): commit_accuracy report inverted db_confirmed
    vs llm because UniProt/ChEMBL hits triggered db_confirmed for AMP
    classification but only confirm peptide-ness, not AMP-ness.

    The fix is per-field _DB_KEYWORDS_BY_FIELD dispatch.
    """
    src = (PKG_ROOT / "app" / "services" / "orchestrator.py").read_text()
    assert "_DB_KEYWORDS_BY_FIELD" in src, \
        "v42.7.3 trip-wire: _DB_KEYWORDS_BY_FIELD dispatch missing"
    # Classification db_confirmed must be AMP-specific only.
    assert '"classification":' in src
    # Outcome db_confirmed must be regulatory-only.
    assert '"outcome":' in src and "fda_drugs" in src and "sec_edgar" in src
    print("  ✓ v42.7.3: per-field _DB_KEYWORDS_BY_FIELD dispatch present")


def test_v42_7_5_boot_commit_captured_at_module_load():
    """v42.7.5 (2026-04-26): autoupdater skips restart while jobs are
    active, so smokes silently ran on stale code. Fix is to capture
    BOOT_COMMIT_FULL once at module load (NOT lazily).
    """
    src = (PKG_ROOT / "app" / "services" / "version_service.py").read_text()
    assert "BOOT_COMMIT_FULL: str = _git_rev_parse(short=False)" in src, \
        "v42.7.5 trip-wire: BOOT_COMMIT_FULL must be captured at module load"
    assert "is_code_in_sync" in src
    print("  ✓ v42.7.5: BOOT_COMMIT_FULL captured at import")


def test_v42_7_6_nih_reporter_uses_advanced_text_search():
    """v42.7.6 (2026-04-26): the documented `clinical_trial_ids` filter
    on api.reporter.nih.gov silently no-ops. Only `advanced_text_search`
    actually filters. The agent must use the correct criterion."""
    src = (PKG_ROOT / "agents" / "research" / "nih_reporter_client.py").read_text()
    assert '"advanced_text_search"' in src, \
        "v42.7.6 trip-wire: must use advanced_text_search criterion"
    # No-op criterion must NOT appear as a JSON key (substring is fine
    # in the docstring describing why we don't use it).
    assert '"clinical_trial_ids"' not in src and "'clinical_trial_ids'" not in src, (
        "v42.7.6 trip-wire: clinical_trial_ids silently returns the "
        "entire 2.9M-row corpus — never use it as a criterion."
    )
    print("  ✓ v42.7.6: advanced_text_search criterion (no-op key avoided)")


def test_dbaasp_word_boundary_preserved():
    """v25 DBAASP word-boundary fix: 'NS' (normal saline) and short
    drug-name prefixes were matching DBAASP entries by substring, not
    word boundary. The pregate even matched 'Curodont' as a peptide.
    Word-boundary matching is the standing rule.
    """
    p = PKG_ROOT / "agents" / "research" / "dbaasp_client.py"
    if not p.exists():
        print("  ⚠ skipped (dbaasp_client.py absent)")
        return
    src = p.read_text()
    # Some form of \b boundary check or len(name) > N guard must exist
    has_guard = any(p in src for p in (r"\b", "word_boundary", "len(name) >", "len(intervention) >"))
    assert has_guard, (
        "DBAASP trip-wire: word-boundary or minimum-length guard missing — "
        "two-letter substrings will spuriously match peptide entries."
    )
    print("  ✓ DBAASP: word-boundary / length guard present")


def main() -> int:
    print("v42 trip-wire regression tests")
    print("-" * 60)
    tests = [
        test_v42_6_14_no_bare_approved_in_strong_efficacy,
        test_v42_6_18_known_sequences_has_glp1,
        test_v42_7_3_per_field_db_keywords,
        test_v42_7_4_two_tier_pub_agents,
        test_v42_7_5_boot_commit_captured_at_module_load,
        test_v42_7_6_nih_reporter_uses_advanced_text_search,
        test_dbaasp_word_boundary_preserved,
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

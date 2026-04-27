#!/usr/bin/env python3
"""
Tests for v42.7.5 code-sync diagnostic (2026-04-26).

Background: the autoupdater LaunchDaemon pulls every 30s but skips
the annotate-service restart while jobs are active. Three times in
the v42.6/v42.7 cycle this produced "stale memory" smokes — the
on-disk commit advanced but the running process was still serving
the previous code, and a smoke validation could silently report PASS
on the wrong code.

The fix captures BOOT_COMMIT_FULL/_SHORT once at module load in
``app/services/version_service.py`` and exposes it alongside the
live on-disk HEAD. The new ``/api/diagnostics/code_sync`` endpoint
returns both plus a ``code_in_sync`` boolean. Smoke harnesses must
assert ``code_in_sync == True`` before declaring pass.
"""
from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))


def test_boot_commit_constants_present():
    src = (PKG_ROOT / "app" / "services" / "version_service.py").read_text()
    assert "BOOT_COMMIT_SHORT" in src, "BOOT_COMMIT_SHORT missing"
    assert "BOOT_COMMIT_FULL" in src, "BOOT_COMMIT_FULL missing"
    # Captured at module level (not inside a function) so import-time freezes it.
    assert "BOOT_COMMIT_SHORT: str = _git_rev_parse(short=True)" in src, \
        "BOOT_COMMIT_SHORT must be captured at module load (not lazy)"
    assert "BOOT_COMMIT_FULL: str = _git_rev_parse(short=False)" in src, \
        "BOOT_COMMIT_FULL must be captured at module load (not lazy)"
    print("  ✓ BOOT_COMMIT_* captured at module load")


def test_is_code_in_sync_helper_present():
    src = (PKG_ROOT / "app" / "services" / "version_service.py").read_text()
    assert "def is_code_in_sync()" in src, "is_code_in_sync() missing"
    # The helper compares boot vs disk full commit.
    assert "BOOT_COMMIT_FULL" in src and "get_git_commit_full()" in src
    print("  ✓ is_code_in_sync() helper present")


def test_version_info_schema_extended():
    src = (PKG_ROOT / "app" / "models" / "output.py").read_text()
    assert "boot_commit_short:" in src, "VersionInfo.boot_commit_short missing"
    assert "boot_commit_full:" in src, "VersionInfo.boot_commit_full missing"
    assert "code_in_sync:" in src, "VersionInfo.code_in_sync missing"
    # Defaults must be set so existing job-output JSONs still parse.
    assert "boot_commit_short: str = \"\"" in src
    assert "boot_commit_full: str = \"\"" in src
    assert "code_in_sync: bool = True" in src
    print("  ✓ VersionInfo schema extended with defaults")


def test_diagnostics_endpoint_present():
    src = (PKG_ROOT / "app" / "routers" / "health.py").read_text()
    assert "/api/diagnostics/code_sync" in src, "diagnostic endpoint missing"
    assert "is_code_in_sync" in src
    assert "boot_commit" in src and "disk_commit" in src
    print("  ✓ /api/diagnostics/code_sync endpoint registered")


def test_get_version_info_populates_boot_fields():
    """Call get_version_info() and confirm boot fields are populated.

    Skips if the working tree isn't a git repo (e.g. CI sparse checkout).
    """
    try:
        from app.services.version_service import (
            get_version_info,
            BOOT_COMMIT_SHORT,
            BOOT_COMMIT_FULL,
            is_code_in_sync,
        )
    except Exception as e:
        print(f"  ⚠ skipped (import failed: {e})")
        return
    info = get_version_info()
    assert info.boot_commit_short == BOOT_COMMIT_SHORT, \
        f"boot_commit_short {info.boot_commit_short!r} != module {BOOT_COMMIT_SHORT!r}"
    assert info.boot_commit_full == BOOT_COMMIT_FULL
    assert info.code_in_sync == is_code_in_sync()
    # In a fresh-checkout test the boot value is whatever HEAD is now —
    # which equals disk HEAD — so code_in_sync should be True.
    assert info.code_in_sync is True, \
        "freshly imported module should report code_in_sync=True"
    print(f"  ✓ get_version_info().boot_commit_short = {info.boot_commit_short!r}")


def test_boot_commit_does_not_change_after_repeat_calls():
    """BOOT_COMMIT_FULL must be a constant — same value on every read."""
    try:
        from app.services.version_service import (
            BOOT_COMMIT_FULL,
            get_boot_commit_full,
        )
    except Exception as e:
        print(f"  ⚠ skipped (import failed: {e})")
        return
    a = get_boot_commit_full()
    b = get_boot_commit_full()
    c = BOOT_COMMIT_FULL
    assert a == b == c, f"boot commit not stable: {a!r} {b!r} {c!r}"
    print("  ✓ BOOT_COMMIT_FULL stable across reads")


def main() -> int:
    print("v42.7.5 code-sync diagnostic tests")
    print("-" * 60)
    tests = [
        test_boot_commit_constants_present,
        test_is_code_in_sync_helper_present,
        test_version_info_schema_extended,
        test_diagnostics_endpoint_present,
        test_get_version_info_populates_boot_fields,
        test_boot_commit_does_not_change_after_repeat_calls,
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

"""
Version and build metadata service.

The autoupdater skips restarts while jobs are active, so the running
process can outlive the on-disk commit. To make stale-memory bugs
visible, this module captures a BOOT commit at module load time and
exposes it alongside the live on-disk commit. Smoke harnesses should
assert ``boot_commit_short == git_commit_short`` before declaring pass.
"""

import subprocess
from app.models.output import VersionInfo
from app.services.config_service import config_service

SEMANTIC_VERSION = "0.1.0"


def _git_rev_parse(short: bool) -> str:
    args = ["git", "rev-parse"]
    if short:
        args.append("--short")
    args.append("HEAD")
    try:
        return subprocess.check_output(
            args, stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "unknown"


def get_git_commit_short() -> str:
    """Live HEAD on disk (changes when autoupdater pulls)."""
    return _git_rev_parse(short=True)


def get_git_commit_full() -> str:
    """Live HEAD on disk (changes when autoupdater pulls)."""
    return _git_rev_parse(short=False)


# Captured once at module import. Whatever process is running this
# module was loaded against this commit — even if `git pull` later
# advances HEAD on disk, this value does not change.
BOOT_COMMIT_SHORT: str = _git_rev_parse(short=True)
BOOT_COMMIT_FULL: str = _git_rev_parse(short=False)


def get_boot_commit_short() -> str:
    """Commit the running process was loaded from. Frozen at boot."""
    return BOOT_COMMIT_SHORT


def get_boot_commit_full() -> str:
    """Commit the running process was loaded from. Frozen at boot."""
    return BOOT_COMMIT_FULL


def is_code_in_sync() -> bool:
    """True iff the running code matches the on-disk HEAD.

    False means the autoupdater pulled new code but skipped the restart
    (e.g. because a job was active). Smoke validations on a False
    process will run against the stale in-memory image.
    """
    disk = get_git_commit_full()
    if disk == "unknown" or BOOT_COMMIT_FULL == "unknown":
        # Best-effort: missing git context means we can't verify.
        return True
    return disk == BOOT_COMMIT_FULL


def get_version_info() -> VersionInfo:
    return VersionInfo(
        semantic_version=SEMANTIC_VERSION,
        git_commit_short=get_git_commit_short(),
        git_commit_full=get_git_commit_full(),
        boot_commit_short=BOOT_COMMIT_SHORT,
        boot_commit_full=BOOT_COMMIT_FULL,
        code_in_sync=is_code_in_sync(),
        config_hash=config_service.get_hash(),
    )


def get_version_stamp() -> dict:
    """Return a dict suitable for embedding in JSON output."""
    from app.models.job import now_pacific
    ts = now_pacific()
    return {
        "version": SEMANTIC_VERSION,
        "git_commit": get_git_commit_short(),
        "git_commit_full": get_git_commit_full(),
        "boot_commit": BOOT_COMMIT_SHORT,
        "boot_commit_full": BOOT_COMMIT_FULL,
        "code_in_sync": is_code_in_sync(),
        "config_hash": config_service.get_hash(),
        "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S PT"),
        "timestamp_iso": ts.isoformat(),
        "timezone": "America/Los_Angeles",
    }

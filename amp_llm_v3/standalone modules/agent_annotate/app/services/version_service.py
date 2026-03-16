"""
Version and build metadata service.
"""

import subprocess
from app.models.output import VersionInfo
from app.services.config_service import config_service

SEMANTIC_VERSION = "0.1.0"


def get_git_commit_short() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "unknown"


def get_git_commit_full() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "unknown"


def get_version_info() -> VersionInfo:
    return VersionInfo(
        semantic_version=SEMANTIC_VERSION,
        git_commit_short=get_git_commit_short(),
        git_commit_full=get_git_commit_full(),
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
        "config_hash": config_service.get_hash(),
        "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S PT"),
        "timestamp_iso": ts.isoformat(),
        "timezone": "America/Los_Angeles",
    }

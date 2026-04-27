"""
Health and readiness endpoints.
"""

from fastapi import APIRouter
from app.services.ollama_client import ollama_client
from app.services.orchestrator import orchestrator
from app.services.version_service import (
    SEMANTIC_VERSION,
    get_version_info,
    get_boot_commit_short,
    get_boot_commit_full,
    get_git_commit_short,
    get_git_commit_full,
    is_code_in_sync,
)

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health():
    """Basic liveness check — used by auto-update script."""
    return {"status": "ok", "version": SEMANTIC_VERSION}


@router.get("/api/health/ready")
async def readiness():
    """Deep readiness check — verifies Ollama and reports active jobs."""
    ollama_ok = await ollama_client.health_check()
    version = get_version_info()
    return {
        "status": "ready" if ollama_ok else "degraded",
        "ollama": "connected" if ollama_ok else "unreachable",
        "active_jobs": orchestrator.active_count(),
        "version": version.model_dump(),
    }


@router.get("/api/jobs/active")
async def active_jobs():
    """Active job count — auto-update script checks this before restarting."""
    return {"active": orchestrator.active_count()}


@router.get("/api/diagnostics/code_sync")
async def code_sync():
    """Code-sync diagnostic — boot vs on-disk commit.

    Smoke harnesses should fetch this and assert ``code_in_sync == True``
    before declaring a smoke pass. False means the autoupdater pulled
    new code but skipped the restart (active job at the time), so the
    running process is on stale in-memory code despite the on-disk
    HEAD having advanced.
    """
    return {
        "boot_commit_short": get_boot_commit_short(),
        "boot_commit_full": get_boot_commit_full(),
        "disk_commit_short": get_git_commit_short(),
        "disk_commit_full": get_git_commit_full(),
        "code_in_sync": is_code_in_sync(),
        "active_jobs": orchestrator.active_count(),
    }

"""
Health and readiness endpoints.
"""

from fastapi import APIRouter
from app.services.ollama_client import ollama_client
from app.services.orchestrator import orchestrator
from app.services.version_service import get_version_info, SEMANTIC_VERSION

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

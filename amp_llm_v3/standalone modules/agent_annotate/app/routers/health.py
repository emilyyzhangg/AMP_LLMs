"""
Health and readiness endpoints.
"""

from fastapi import APIRouter
from app.services.ollama_client import ollama_client
from app.services.version_service import get_version_info, SEMANTIC_VERSION

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health():
    """Basic liveness check."""
    return {"status": "ok", "version": SEMANTIC_VERSION}


@router.get("/api/health/ready")
async def readiness():
    """Deep readiness check - verifies Ollama connectivity."""
    ollama_ok = await ollama_client.health_check()
    version = get_version_info()
    return {
        "status": "ready" if ollama_ok else "degraded",
        "ollama": "connected" if ollama_ok else "unreachable",
        "version": version.model_dump(),
    }

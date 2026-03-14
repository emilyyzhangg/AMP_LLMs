"""
Settings / configuration endpoints.
"""

from fastapi import APIRouter

from app.services.config_service import config_service

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
async def get_settings():
    """Return the current pipeline configuration."""
    cfg = config_service.get()
    return cfg.model_dump()


@router.put("")
async def update_settings(overrides: dict):
    """Apply runtime overrides to the pipeline configuration.

    Accepts a partial config dict; only the provided keys are merged.
    Changes persist in memory until the service restarts.
    """
    cfg = config_service.update(overrides)
    return cfg.model_dump()


@router.post("/reload")
async def reload_settings():
    """Reload configuration from the YAML file on disk."""
    cfg = config_service.load()
    return {"status": "reloaded", "config": cfg.model_dump()}

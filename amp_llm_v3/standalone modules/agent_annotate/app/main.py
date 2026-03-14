"""
Agent Annotate - FastAPI application entry point.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import CORS_ORIGINS, FRONTEND_DIR
from app.services.config_service import config_service

from app.routers import health, jobs, status, results, review, settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    # Load pipeline config on startup
    config_service.load()
    yield


app = FastAPI(
    title="Agent Annotate",
    description="Multi-model annotation pipeline for clinical trial data",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health.router)
app.include_router(jobs.router)
app.include_router(status.router)
app.include_router(results.router)
app.include_router(review.router)
app.include_router(settings.router)

# Serve frontend SPA (production build)
if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa_catch_all(full_path: str):
        """Serve index.html for all non-API routes (SPA routing)."""
        file_path = FRONTEND_DIR / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIR / "index.html")

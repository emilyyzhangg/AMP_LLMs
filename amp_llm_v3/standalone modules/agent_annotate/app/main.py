"""
Agent Annotate - FastAPI application entry point.
"""

import logging
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import CORS_ORIGINS, FRONTEND_DIR, LOGS_DIR
from app.services.config_service import config_service

from app.routers import health, jobs, status, results, review, settings


def setup_logging():
    """Configure structured logging with rotating file handler."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler - rotates at 10MB, keeps 10 backups
    fh = RotatingFileHandler(
        LOGS_DIR / "agent_annotate.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=10,
    )
    fh.setFormatter(fmt)
    fh.setLevel(logging.INFO)

    # Console handler
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    ch.setLevel(logging.INFO)

    root = logging.getLogger("agent_annotate")
    root.setLevel(logging.INFO)
    root.addHandler(fh)
    root.addHandler(ch)

    # Suppress noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


setup_logging()
logger = logging.getLogger("agent_annotate")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("Agent Annotate starting up...")
    config = config_service.load()
    logger.info(
        "Config loaded: %d verifiers, %d research agents, %d annotation fields",
        config.verification.num_verifiers,
        len(config.research_agents),
        len(config.annotation_agents),
    )
    yield
    logger.info("Agent Annotate shutting down...")


app = FastAPI(
    title="Agent Annotate",
    description="Publication-grade clinical trial annotation with specialized AI agents",
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
    assets_dir = FRONTEND_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    async def spa_catch_all(full_path: str):
        """Serve index.html for all non-API routes (SPA routing)."""
        file_path = FRONTEND_DIR / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIR / "index.html")

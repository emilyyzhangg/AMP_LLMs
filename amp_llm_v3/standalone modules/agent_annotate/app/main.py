"""
Agent Annotate - FastAPI application entry point.
"""

import logging
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import CORS_ORIGINS, FRONTEND_DIR, LOGS_DIR
from app.auth_client import get_token_from_request, validate_token

PATH_PREFIX = "/agent-annotate"
from app.services.config_service import config_service

from app.routers import health, jobs, status, results, review, settings, concordance

# API paths that do NOT require authentication
# (health/readiness used by auto-updater, active jobs used before restart)
AUTH_EXEMPT_API_PATHS = {
    "/api/health",
    "/api/health/ready",
    "/api/jobs/active",
}


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

# Strip /agent-annotate prefix so the app works both at
# localhost:9005/ (direct) and dev-llm.amphoraxe.ca/agent-annotate/ (via Cloudflare)
class StripPrefixMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.scope["path"]
        if path.startswith(PATH_PREFIX):
            request.scope["path"] = path[len(PATH_PREFIX):] or "/"
            request.state._behind_prefix = True
        else:
            request.state._behind_prefix = False
        return await call_next(request)


class AuthMiddleware(BaseHTTPMiddleware):
    """Require amp_auth cookie for all /api/* routes except health/readiness."""

    async def dispatch(self, request: Request, call_next):
        path = request.scope["path"]

        # Let CORS preflight (OPTIONS) through
        if request.method == "OPTIONS":
            return await call_next(request)

        # Only gate /api/* routes; static files / SPA pages are public
        if path.startswith("/api/") or path == "/api":
            # Allow exempt paths (health, readiness, active-job count)
            # Also allow resume endpoint (requires valid job_id anyway)
            is_exempt = (
                path in AUTH_EXEMPT_API_PATHS
                or path.endswith("/resume")
                or path.endswith("/cancel")
                or path.startswith("/api/status/pipeline/")
                or path.startswith("/api/concordance/")
                or (path == "/api/jobs" and request.method == "POST")
            )
            if not is_exempt:
                token = get_token_from_request(request)
                user = validate_token(token, app_slug="amp-llm") if token else None
                if not user:
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Not authenticated"},
                    )
                # Stash user on request state so handlers can use it if needed
                request.state.user = user

        return await call_next(request)


app.add_middleware(AuthMiddleware)
app.add_middleware(StripPrefixMiddleware)

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
app.include_router(concordance.router)

# Serve frontend SPA (production build)
if FRONTEND_DIR.exists():
    assets_dir = FRONTEND_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    async def spa_catch_all(request: Request, full_path: str):
        """Serve index.html for all non-API routes (SPA routing).

        Detects Cloudflare-proxied requests (Host != localhost) and injects
        a <base> tag so absolute asset paths resolve through the prefix.
        """
        file_path = FRONTEND_DIR / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)

        index_html = (FRONTEND_DIR / "index.html").read_text()

        # If the request came through a non-localhost host, it's via
        # Cloudflare tunnel and needs the /agent-annotate prefix for assets.
        host = request.headers.get("host", "")
        is_proxied = host and not host.startswith("localhost") and not host.startswith("127.0.0.1")

        if is_proxied:
            index_html = index_html.replace(
                "<head>",
                f'<head>\n    <base href="{PATH_PREFIX}/" />',
            )

        from fastapi.responses import HTMLResponse
        return HTMLResponse(index_html)

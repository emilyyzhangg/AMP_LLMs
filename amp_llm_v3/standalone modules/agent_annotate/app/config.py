"""
Application configuration - loads from .env and environment variables.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env - check project root first, then webapp/.env for shared keys
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")
# Also load webapp .env for shared API keys (SERPAPI_KEY, NCBI_API_KEY, etc.)
_WEBAPP_ENV = _PROJECT_ROOT.parent.parent / "webapp" / ".env"
if _WEBAPP_ENV.exists():
    load_dotenv(_WEBAPP_ENV, override=False)

# --- Server ---
AGENT_ANNOTATE_PORT = int(os.getenv("AGENT_ANNOTATE_PORT", "9005"))

# --- Ollama ---
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "localhost")
OLLAMA_PORT = int(os.getenv("OLLAMA_PORT", "11434"))
OLLAMA_BASE_URL = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}"
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "600"))

# --- NCT Service ---
NCT_SERVICE_PORT = int(os.getenv("NCT_SERVICE_PORT", "9002"))
NCT_SERVICE_URL = f"http://localhost:{NCT_SERVICE_PORT}"

# --- External API keys (optional) ---
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")
PUBMED_API_KEY = os.getenv("PUBMED_API_KEY", "")

# --- CORS ---
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://localhost:9005"
).split(",")

# --- Paths ---
CONFIG_DIR = _PROJECT_ROOT / "config"
DEFAULT_CONFIG_PATH = CONFIG_DIR / "default_config.yaml"
RESULTS_DIR = _PROJECT_ROOT / "results"
LOGS_DIR = _PROJECT_ROOT / "logs"
FRONTEND_DIR = _PROJECT_ROOT / "app" / "static" / "spa"

# Ensure output directories exist
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

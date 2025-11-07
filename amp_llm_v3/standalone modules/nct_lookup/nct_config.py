"""
NCT Lookup Configuration
========================

Centralized configuration management from environment variables.
All ports, paths, and settings are loaded from .env file.
"""

import os
from pathlib import Path
from typing import Optional, Set
from dotenv import load_dotenv

# Find .env file - it's in webapp directory
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent  # Go up to amp_llm_v3
env_file = project_root / "webapp" / ".env"

# Load environment variables from webapp/.env
if env_file.exists():
    load_dotenv(env_file)
    print(f"✓ Loaded .env from: {env_file}")
else:
    # Try current directory as fallback
    load_dotenv()
    print(f"⚠ .env not found at {env_file}, trying current directory")


class NCTConfig:
    """Configuration for NCT lookup service"""
    
    # Service Ports (from .env)
    MAIN_SERVER_PORT: int = int(os.getenv("MAIN_SERVER_PORT", "9000"))
    CHAT_SERVICE_PORT: int = int(os.getenv("CHAT_SERVICE_PORT", "9001"))
    NCT_SERVICE_PORT: int = int(os.getenv("NCT_SERVICE_PORT", "9002"))
    
    # Domain
    PUBLIC_DOMAIN: str = os.getenv("PUBLIC_DOMAIN", "localhost")
    
    # Environment
    ENVIRONMENT: str = os.getenv("environment", "development")
    
    # Ollama
    OLLAMA_HOST: str = os.getenv("ollama_host", "localhost")
    OLLAMA_PORT: int = int(os.getenv("ollama_port", "11434"))
    
    # API Keys
    SERPAPI_KEY: Optional[str] = os.getenv("SERPAPI_KEY")
    NCBI_API_KEY: Optional[str] = os.getenv("NCBI_API_KEY")
    OPENFDA_KEY: Optional[str] = os.getenv("OPENFDA_KEY")
    
    # API Authentication
    API_KEY_1: Optional[str] = os.getenv("API_KEY_1")
    API_KEY_2: Optional[str] = os.getenv("API_KEY_2")
    
    @property
    def api_keys(self) -> Set[str]:
        """Get all configured API keys"""
        keys = {self.API_KEY_1, self.API_KEY_2}
        return {k for k in keys if k}
    
    # Paths (relative to project root)
    BASE_DIR: Path = Path(__file__).parent.parent.parent
    OUTPUT_DIR: Path = BASE_DIR / "output"
    DATABASE_DIR: Path = BASE_DIR / "ct_database"
    CACHE_DIR: Path = BASE_DIR / ".cache" / "nct_lookup"
    
    # Service URLs (dynamically generated)
    @property
    def MAIN_SERVER_URL(self) -> str:
        return f"http://localhost:{self.MAIN_SERVER_PORT}"
    
    @property
    def CHAT_SERVICE_URL(self) -> str:
        return f"http://localhost:{self.CHAT_SERVICE_PORT}"
    
    @property
    def NCT_SERVICE_URL(self) -> str:
        return f"http://localhost:{self.NCT_SERVICE_PORT}"
    
    @property
    def OLLAMA_BASE_URL(self) -> str:
        return f"http://{self.OLLAMA_HOST}:{self.OLLAMA_PORT}"
    
    # OpenFDA Blacklist (hardcoded as specified)
    OPENFDA_BLACKLIST: Set[str] = {
        "drugs",
        "drug",
        "intervention",
        "interventions",
        "medication",
        "medications",
        "therapy",
        "therapies",
        "treatment",
        "treatments",
        "placebo",
        "control"
    }
    
    # Search Configuration
    MAX_RESULTS_PER_API: int = 50
    TIMEOUT_SECONDS: int = 120
    MAX_RETRIES: int = 3
    
    # CORS Origins
    @property
    def CORS_ORIGINS(self) -> list:
        """Get allowed CORS origins based on environment"""
        if self.ENVIRONMENT == "production":
            return [
                f"https://{self.PUBLIC_DOMAIN}",
                f"http://{self.PUBLIC_DOMAIN}",
                f"http://localhost:{self.MAIN_SERVER_PORT}"
            ]
        else:  # development
            return [
                "*",  # Allow all in development
                f"http://localhost:{self.MAIN_SERVER_PORT}",
                "http://localhost:3000",
                "http://127.0.0.1:3000"
            ]
    
    def __init__(self):
        """Initialize configuration and create necessary directories"""
        self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self.DATABASE_DIR.mkdir(parents=True, exist_ok=True)
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        
        # Log configuration
        self._log_config()
    
    def _log_config(self):
        """Log current configuration (for debugging)"""
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info("=" * 60)
        logger.info("NCT Lookup Service Configuration")
        logger.info("=" * 60)
        logger.info(f"Environment: {self.ENVIRONMENT}")
        logger.info(f"NCT Service Port: {self.NCT_SERVICE_PORT}")
        logger.info(f"Main Server Port: {self.MAIN_SERVER_PORT}")
        logger.info(f"Chat Service Port: {self.CHAT_SERVICE_PORT}")
        logger.info(f"Public Domain: {self.PUBLIC_DOMAIN}")
        logger.info(f"Output Directory: {self.OUTPUT_DIR}")
        logger.info(f"Database Directory: {self.DATABASE_DIR}")
        logger.info(f"Cache Directory: {self.CACHE_DIR}")
        logger.info(f"SERPAPI Key: {'✓ Configured' if self.SERPAPI_KEY else '✗ Not Set'}")
        logger.info(f"NCBI API Key: {'✓ Configured' if self.NCBI_API_KEY else '✗ Not Set'}")
        logger.info(f"OpenFDA Blacklist: {len(self.OPENFDA_BLACKLIST)} terms")
        logger.info("=" * 60)
    
    def is_term_blacklisted(self, term: str) -> bool:
        """Check if a term is blacklisted for OpenFDA searches"""
        if not term:
            return True
        return term.lower().strip() in self.OPENFDA_BLACKLIST
    
    def filter_blacklisted_terms(self, terms: list) -> list:
        """Filter out blacklisted terms from a list"""
        return [t for t in terms if not self.is_term_blacklisted(t)]


# Global configuration instance
config = NCTConfig()


# Export for convenience
__all__ = ['config', 'NCTConfig']
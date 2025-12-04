"""
Configuration management for webapp.
"""
import os
from typing import Set
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    """Application settings."""
    
    model_config = {
        "extra": "allow",
        "env_file": ".env"
    }
    
    # API Keys
    api_keys: Set[str] = set()
    
    # Ollama
    ollama_host: str = "localhost"
    ollama_port: int = 11434
    
    # Service Ports (read from environment)
    main_server_port: int = int(os.getenv("MAIN_SERVER_PORT", "8000"))
    chat_service_port: int = int(os.getenv("CHAT_SERVICE_PORT", "8001"))
    nct_service_port: int = int(os.getenv("NCT_SERVICE_PORT", "8002"))
    
    # Public domain
    public_domain: str = os.getenv("PUBLIC_DOMAIN", "localhost")
    
    # CORS - allow both production and dev domains
    allowed_origins: list = [
        "https://llm.amphoraxe.ca",
        "https://dev-llm.amphoraxe.ca",
        "http://localhost:3000"
    ]
    
    # Environment
    environment: str = os.getenv("environment", "development")
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Collect API keys from environment
        self.api_keys = {
            os.getenv("API_KEY_1", ""),
            os.getenv("API_KEY_2", ""),
            os.getenv("API_KEY_3", ""),
        }
        # Remove empty keys
        self.api_keys = {key for key in self.api_keys if key}
        
        if not self.api_keys:
            raise ValueError(
                "No API keys configured! Set API_KEY_1, API_KEY_2, etc. in .env"
            )
    
    @property
    def chat_service_url(self) -> str:
        """Get chat service URL based on environment."""
        return f"http://localhost:{self.chat_service_port}"
    
    @property
    def nct_service_url(self) -> str:
        """Get NCT service URL based on environment."""
        return f"http://localhost:{self.nct_service_port}"


settings = Settings()
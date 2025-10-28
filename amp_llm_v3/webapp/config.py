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

    # Service ports - NEW
    main_server_port: int
    chat_service_port: int
    nct_service_port: int

    # CORS
    allowed_origins: list = ["https://llm.amphoraxe.ca"]
    
    # Environment
    environment: str = "development"
    
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


settings = Settings()
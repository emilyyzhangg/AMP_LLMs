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
    
    # API Keys
    api_keys: Set[str] = {
        os.getenv("API_KEY_1", ""),
        os.getenv("API_KEY_2", ""),
        os.getenv("API_KEY_3", ""),
    }
    
    # Ollama
    ollama_host: str = os.getenv("OLLAMA_HOST", "localhost")
    ollama_port: int = int(os.getenv("OLLAMA_PORT", "11434"))
    
    # CORS
    allowed_origins: list = os.getenv(
        "ALLOWED_ORIGINS", 
        "https://llm.amphoraxe.ca"
    ).split(",")
    
    # Environment
    environment: str = os.getenv("ENVIRONMENT", "development")
    
    class Config:
        env_file = ".env"
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Remove empty keys
        self.api_keys = {key for key in self.api_keys if key}
        
        if not self.api_keys:
            raise ValueError(
                "No API keys configured! Set API_KEY_1, API_KEY_2, etc. in .env"
            )


settings = Settings()
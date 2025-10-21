"""
Chat Service Configuration
==========================

Centralized configuration for the chat service.
"""
import os
from pathlib import Path
from typing import Optional

class ChatConfig:
    """Configuration for chat service"""
    
    # Ollama connection
    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "localhost")
    OLLAMA_PORT: int = int(os.getenv("OLLAMA_PORT", "11434"))
    
    @property
    def OLLAMA_BASE_URL(self) -> str:
        return f"http://{self.OLLAMA_HOST}:{self.OLLAMA_PORT}"
    
    # Service configuration
    API_VERSION: str = "1.0.0"
    SERVICE_NAME: str = "LLM Chat Service"
    
    # Timeouts (seconds)
    GENERATION_TIMEOUT: int = 300  # 5 minutes
    CONNECTION_TIMEOUT: int = 10
    
    # Storage
    CONVERSATION_DIR: Path = Path("conversations")
    
    # CORS
    CORS_ORIGINS: list = ["*"]  # Configure for production
    
    def __init__(self):
        """Initialize and create necessary directories"""
        self.CONVERSATION_DIR.mkdir(exist_ok=True)


# Global config instance
config = ChatConfig()
"""
LLM Chat Service
================

Modular service for interactive chat with Ollama models.
"""

__version__ = "1.0.0"
__author__ = "AMP LLM Team"

from chat_api import app
from chat_client import OllamaClient
from chat_manager import ConversationManager
from chat_config import config

__all__ = [
    "app",
    "OllamaClient",
    "ConversationManager",
    "config"
]
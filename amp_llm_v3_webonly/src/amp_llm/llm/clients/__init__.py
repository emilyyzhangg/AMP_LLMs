"""
Ollama client implementations.

Provides both API (HTTP) and SSH-based clients for Ollama interaction.
"""

from .ollama_api import OllamaAPIClient
from .ollama_ssh import OllamaSSHClient
from .base import BaseLLMClient

__all__ = [
    'BaseLLMClient',
    'OllamaAPIClient',
    'OllamaSSHClient',
]
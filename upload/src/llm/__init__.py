# ============================================================================
# src/amp_llm/llm/__init__.py
# ============================================================================
"""
LLM integration modules for Ollama interaction.
"""
from .clients.ollama_api import OllamaAPIClient
from .clients.ollama_ssh import OllamaSSHClient

__all__ = ['OllamaAPIClient', 'OllamaSSHClient']

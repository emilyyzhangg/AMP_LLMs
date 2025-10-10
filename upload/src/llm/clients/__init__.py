# ============================================================================
# src/amp_llm/llm/clients/__init__.py
# ============================================================================
"""
LLM client interfaces for different connection methods.
"""
from .base import BaseLLMClient
from .ollama_api import OllamaAPIClient
from .ollama_ssh import OllamaSSHClient

__all__ = ['BaseLLMClient', 'OllamaAPIClient', 'OllamaSSHClient']
# ============================================================================
# src/amp_llm/llm/__init__.py
# ============================================================================
"""
LLM integration modules for Ollama interaction.
"""
from clients.ollama_api import OllamaAPIClient
from clients.ollama_ssh import OllamaSSHClient
from handlers import run_llm_entrypoint_api, run_llm_entrypoint_ssh

__all__ = [
    'OllamaAPIClient',
    'OllamaSSHClient', 
    'run_llm_entrypoint_api',
    'run_llm_entrypoint_ssh',
]
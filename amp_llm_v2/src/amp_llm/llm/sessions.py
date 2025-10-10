# ============================================================================
# src/amp_llm/llm/sessions.py
# ============================================================================
"""
Session management for remote Ollama LLM processes.
"""

from amp_llm.config import get_logger

logger = get_logger(__name__)


async def start_persistent_ollama(ssh, model: str):
    """
    Start a persistent Ollama LLM process remotely.
    This does NOT allocate a TTY (term_type=None) — optimized for programmatic I/O.
    """
    try:
        logger.info(f"Starting persistent Ollama model: {model}")
        process = await ssh.create_process(
            f"ollama run {model}",
            term_type=None,        # no TTY
            encoding="utf-8"
        )
        return process
    except Exception as e:
        logger.error(f"Failed to start Ollama process: {e}", exc_info=True)
        return None

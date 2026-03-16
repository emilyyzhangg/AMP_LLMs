"""
Async Ollama client for annotation and verification calls.

Uses asyncio.Lock to ensure only one model is loaded at a time
(16GB RAM constraint on M4 Mac Mini). On server profiles with
sufficient RAM, models are kept loaded via keep_alive to avoid
reload overhead between annotations.
"""

import asyncio
import logging
import httpx
from typing import Optional

from app.config import OLLAMA_BASE_URL, OLLAMA_TIMEOUT

logger = logging.getLogger("agent_annotate.ollama")

# How long to keep models loaded in Ollama after use.
# On Mac Mini (16GB): short keep-alive to free RAM for next model.
# On Server (240GB+): long keep-alive to avoid reload churn.
_KEEP_ALIVE_MAC = "5m"
_KEEP_ALIVE_SERVER = "60m"


class OllamaAnnotationClient:
    """Thread-safe async client for Ollama generate API."""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._base_url = OLLAMA_BASE_URL
        self._timeout = OLLAMA_TIMEOUT
        self._keep_alive = _KEEP_ALIVE_MAC  # default, updated by set_hardware_profile

    def set_hardware_profile(self, profile: str) -> None:
        """Set keep_alive based on hardware profile."""
        if profile == "server":
            self._keep_alive = _KEEP_ALIVE_SERVER
            logger.info("Ollama keep_alive set to %s (server profile)", self._keep_alive)
        else:
            self._keep_alive = _KEEP_ALIVE_MAC
            logger.info("Ollama keep_alive set to %s (mac_mini profile)", self._keep_alive)

    async def generate(
        self,
        model: str,
        prompt: str,
        temperature: float = 0.10,
        system: Optional[str] = None,
    ) -> dict:
        """Send a generate request to Ollama and return the parsed response."""
        payload: dict = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": self._keep_alive,
            "options": {"temperature": temperature},
        }
        if system:
            payload["system"] = system

        async with self._lock:
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(
                        f"{self._base_url}/api/generate",
                        json=payload,
                    )
                    resp.raise_for_status()
                    return resp.json()
            except httpx.ConnectError:
                logger.error("Ollama unreachable at %s", self._base_url)
                raise RuntimeError(
                    f"Ollama is unreachable at {self._base_url}. "
                    "Ensure Ollama is running (ollama serve)."
                )
            except httpx.TimeoutException:
                logger.error(
                    "Ollama timeout after %ds for model %s", self._timeout, model
                )
                raise RuntimeError(
                    f"Ollama timed out after {self._timeout}s. "
                    f"Model '{model}' may be too large or the prompt too long."
                )
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    logger.error("Model '%s' not found in Ollama", model)
                    raise RuntimeError(
                        f"Model '{model}' not found. Run: ollama pull {model}"
                    )
                logger.error("Ollama HTTP error %d: %s", e.response.status_code, e.response.text[:200])
                raise

    async def list_models(self) -> list[dict]:
        """Return list of locally available models."""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                resp.raise_for_status()
                data = resp.json()
                return data.get("models", [])
        except Exception as e:
            logger.warning("Failed to list Ollama models: %s", e)
            return []

    async def health_check(self) -> bool:
        """Return True if Ollama is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False


# Module-level singleton
ollama_client = OllamaAnnotationClient()

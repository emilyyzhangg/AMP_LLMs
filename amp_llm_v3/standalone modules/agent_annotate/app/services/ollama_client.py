"""
Async Ollama client for annotation and verification calls.
"""

import asyncio
import httpx
from typing import Optional

from app.config import OLLAMA_BASE_URL, OLLAMA_TIMEOUT


class OllamaAnnotationClient:
    """Thread-safe async client for Ollama generate API."""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._base_url = OLLAMA_BASE_URL
        self._timeout = OLLAMA_TIMEOUT

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
            "options": {"temperature": temperature},
        }
        if system:
            payload["system"] = system

        async with self._lock:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/api/generate",
                    json=payload,
                )
                resp.raise_for_status()
                return resp.json()

    async def list_models(self) -> list[dict]:
        """Return list of locally available models."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{self._base_url}/api/tags")
            resp.raise_for_status()
            data = resp.json()
            return data.get("models", [])

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

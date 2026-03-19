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
        self._call_count = 0
        self._call_count_by_model: dict[str, int] = {}
        self._verified_models: set[str] = set()  # models confirmed available

    def set_hardware_profile(self, profile: str) -> None:
        """Set keep_alive based on hardware profile."""
        if profile == "server":
            self._keep_alive = _KEEP_ALIVE_SERVER
            logger.info("Ollama keep_alive set to %s (server profile)", self._keep_alive)
        else:
            self._keep_alive = _KEEP_ALIVE_MAC
            logger.info("Ollama keep_alive set to %s (mac_mini profile)", self._keep_alive)

    async def ensure_model(self, model: str) -> None:
        """Check if a model is available locally; pull it if not.

        Caches successful checks so each model is only verified once per
        process lifetime. Pull can take minutes for large models — this
        is expected on first use.
        """
        if model in self._verified_models:
            return

        # Check if model exists
        models = await self.list_models()
        local_names = set()
        for m in models:
            name = m.get("name", "")
            local_names.add(name)
            # Also match without tag (e.g. "qwen2.5:14b" matches "qwen2.5:14b")
            # and base name (e.g. "qwen2.5" matches "qwen2.5:latest")
            if ":" in name:
                local_names.add(name.split(":")[0])

        # Check exact match or base name match
        if model in local_names:
            self._verified_models.add(model)
            return

        # Model not found — attempt to pull it
        logger.warning(
            "Model '%s' not found locally. Pulling from Ollama registry...", model
        )
        try:
            async with httpx.AsyncClient(timeout=3600) as client:
                # Ollama pull API streams progress — we consume it to completion
                async with client.stream(
                    "POST",
                    f"{self._base_url}/api/pull",
                    json={"name": model, "stream": True},
                    timeout=3600,
                ) as resp:
                    resp.raise_for_status()
                    last_status = ""
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            import json
                            data = json.loads(line)
                            status = data.get("status", "")
                            if status != last_status:
                                logger.info("  pull %s: %s", model, status)
                                last_status = status
                        except Exception:
                            pass
            logger.info("Successfully pulled model '%s'", model)
            self._verified_models.add(model)
        except Exception as e:
            logger.error("Failed to pull model '%s': %s", model, e)
            raise RuntimeError(
                f"Model '{model}' not found and auto-pull failed: {e}. "
                f"Try manually: ollama pull {model}"
            )

    async def generate(
        self,
        model: str,
        prompt: str,
        temperature: float = 0.10,
        system: Optional[str] = None,
    ) -> dict:
        """Send a generate request to Ollama and return the parsed response.

        Auto-pulls the model if not available locally (first call only).
        """
        # Ensure model is available (cached after first check)
        await self.ensure_model(model)

        payload: dict = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": self._keep_alive,
            "options": {"temperature": temperature},
        }
        if system:
            payload["system"] = system

        self._call_count += 1
        self._call_count_by_model[model] = self._call_count_by_model.get(model, 0) + 1

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
                    # Model vanished after ensure_model — clear cache and retry once
                    self._verified_models.discard(model)
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

    def get_call_count(self) -> int:
        """Total LLM calls since last reset."""
        return self._call_count

    def get_call_counts_by_model(self) -> dict[str, int]:
        """LLM calls broken down by model name."""
        return dict(self._call_count_by_model)

    def reset_call_count(self):
        """Reset call counters (call at start of each trial)."""
        self._call_count = 0
        self._call_count_by_model.clear()


# Module-level singleton
ollama_client = OllamaAnnotationClient()

"""
Per-drug in-process research cache (v42.6.5).

Many clinical trials in a batch test the same drug (e.g., 200+ semaglutide
trials). ChEMBL, UniProt, DBAASP, APD, IUPHAR, RCSB_PDB queries for that
drug return identical data across NCTs — re-querying them per-NCT burns
network + rate-limit budget for zero incremental value.

This module is a simple process-local cache keyed by (agent_name, drug_name).
It is:

- **Per-process**: lost on service restart. Warm-up cost is paid on the
  first NCT that tests each drug; subsequent NCTs get instant lookup.
- **Unbounded**: no TTL or size cap. Research data is structural (drug
  identity doesn't change) and the working set for any batch is bounded
  by unique drugs, typically << NCT count.
- **Thread-safe via asyncio**: uses an asyncio.Lock so concurrent
  ``get_or_compute`` calls for the same key don't duplicate work.
- **Opt-in per agent**: agents call ``get_or_compute(agent, key, coro_factory)``
  rather than the module auto-wrapping everything.

Usage:
    from agents.research.drug_cache import drug_cache
    cached = await drug_cache.get_or_compute(
        "chembl", drug_name_lower,
        lambda: _fetch_chembl(drug_name),
    )

When caller needs to disable (tests, deterministic runs), set
``orchestrator.per_drug_research_cache = False`` in config.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger("agent_annotate.research.drug_cache")


class DrugResearchCache:
    """Process-local async cache keyed by (agent_name, drug_name)."""

    def __init__(self) -> None:
        self._data: dict[tuple[str, str], Any] = {}
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}
        self.hits = 0
        self.misses = 0

    def _norm(self, agent: str, drug: str) -> tuple[str, str]:
        return (agent.strip().lower(), drug.strip().lower())

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {
            "size": len(self._data),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hits / total, 3) if total else 0.0,
        }

    def clear(self) -> None:
        self._data.clear()
        self._locks.clear()
        self.hits = 0
        self.misses = 0

    async def get_or_compute(
        self,
        agent: str,
        drug_name: str,
        compute: Callable[[], Awaitable[Any]],
    ) -> Any:
        """Return cached result for (agent, drug_name) or compute+cache.

        The lock guards against duplicate concurrent ``compute`` calls for the
        same key — first caller runs, others wait and get the cached result.
        """
        if not drug_name:
            return await compute()
        key = self._norm(agent, drug_name)

        # Fast path: already cached.
        if key in self._data:
            self.hits += 1
            return self._data[key]

        # Coalesce concurrent computes.
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            if key in self._data:
                self.hits += 1
                return self._data[key]
            self.misses += 1
            result = await compute()
            self._data[key] = result
            return result

    def is_enabled(self) -> bool:
        """Check the orchestrator config flag. Fails open (enabled) on
        config errors to keep tests / scripts working without full config."""
        try:
            from app.services.config_service import config_service
            cfg = config_service.get()
            return getattr(cfg.orchestrator, "per_drug_research_cache", True)
        except Exception:
            return True


# Module-level singleton. Shared across all research agents in the process.
drug_cache = DrugResearchCache()

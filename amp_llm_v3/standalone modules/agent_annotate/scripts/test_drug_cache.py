#!/usr/bin/env python3
"""
Unit tests for DrugResearchCache — the per-drug research coalescer.

No network, no LLM. Verifies:
  1. First call computes; second identical call hits cache.
  2. Different (agent, drug) pairs do not collide.
  3. Concurrent identical calls coalesce to a single compute.
  4. Empty drug name bypasses cache (always computes).
  5. Stats reflect hits/misses correctly.

Usage:
    cd <agent_annotate_dir>
    python3 scripts/test_drug_cache.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

from agents.research.drug_cache import DrugResearchCache  # noqa: E402


async def test_hit_miss():
    cache = DrugResearchCache()
    calls = 0

    async def compute():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return {"value": calls}

    r1 = await cache.get_or_compute("chembl", "Semaglutide", compute)
    r2 = await cache.get_or_compute("chembl", "Semaglutide", compute)
    r3 = await cache.get_or_compute("chembl", "semaglutide", compute)  # norm check

    assert calls == 1, f"expected 1 compute, got {calls}"
    assert r1["value"] == 1
    assert r2["value"] == 1
    assert r3["value"] == 1, "drug name case should normalize"
    stats = cache.stats()
    assert stats["hits"] == 2 and stats["misses"] == 1, stats
    print("  ✓ hit/miss behaviour + case normalization")


async def test_isolation_by_key():
    cache = DrugResearchCache()

    async def compute_a():
        return "A"

    async def compute_b():
        return "B"

    # Different drug → different cache entry
    r1 = await cache.get_or_compute("chembl", "Drug1", compute_a)
    r2 = await cache.get_or_compute("chembl", "Drug2", compute_b)
    # Different agent, same drug → different cache entry
    r3 = await cache.get_or_compute("dbaasp", "Drug1", compute_b)

    assert r1 == "A" and r2 == "B" and r3 == "B"
    assert cache.stats()["size"] == 3
    print("  ✓ isolation by (agent, drug) key")


async def test_concurrent_coalesce():
    """Two concurrent calls for the same key must coalesce to one compute."""
    cache = DrugResearchCache()
    calls = 0

    async def slow_compute():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return calls

    r1, r2, r3 = await asyncio.gather(
        cache.get_or_compute("chembl", "SharedDrug", slow_compute),
        cache.get_or_compute("chembl", "SharedDrug", slow_compute),
        cache.get_or_compute("chembl", "SharedDrug", slow_compute),
    )
    assert calls == 1, f"concurrent should coalesce, saw {calls} computes"
    assert r1 == r2 == r3 == 1
    print("  ✓ concurrent calls coalesce via lock")


async def test_empty_drug_bypasses():
    """Empty or whitespace drug name should always compute, never cache."""
    cache = DrugResearchCache()
    calls = 0

    async def compute():
        nonlocal calls
        calls += 1
        return calls

    await cache.get_or_compute("chembl", "", compute)
    await cache.get_or_compute("chembl", "", compute)
    assert calls == 2, "empty drug must not be cached"
    assert cache.stats()["size"] == 0
    print("  ✓ empty drug name bypasses cache")


async def test_exception_does_not_poison():
    """A compute that raises must not leave a bad entry in the cache."""
    cache = DrugResearchCache()
    attempts = 0

    async def flaky():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("transient")
        return "ok"

    try:
        await cache.get_or_compute("chembl", "FlakyDrug", flaky)
    except RuntimeError:
        pass

    result = await cache.get_or_compute("chembl", "FlakyDrug", flaky)
    assert result == "ok"
    assert attempts == 2, "exception must not leave cached entry"
    print("  ✓ raised exception does not poison the cache")


async def main() -> int:
    print("DrugResearchCache tests")
    print("-" * 60)
    tests = [
        test_hit_miss,
        test_isolation_by_key,
        test_concurrent_coalesce,
        test_empty_drug_bypasses,
        test_exception_does_not_poison,
    ]
    failed = 0
    for t in tests:
        try:
            await t()
        except AssertionError as e:
            print(f"  ✗ {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ {t.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print("-" * 60)
    if failed:
        print(f"FAIL: {failed}/{len(tests)}")
        return 1
    print(f"OK: {len(tests)}/{len(tests)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

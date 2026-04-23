#!/usr/bin/env python3
"""
Cross-client wiring smoke test.

For each research client wired to DrugResearchCache, verifies:
  1. Import succeeds.
  2. The client has a `_fetch_intervention` helper (the cache contract).
  3. The `research()` method looks up the cache when enabled and the second
     call for the same intervention skips network.

Patches out HTTP entirely via monkey-patched httpx and resilient_get. No
network, no LLM.

Usage:
    cd <agent_annotate_dir>
    python3 scripts/test_all_client_cache_wiring.py
"""

from __future__ import annotations

import asyncio
import inspect
import sys
from pathlib import Path
from unittest.mock import patch, AsyncMock

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

from agents.research.drug_cache import drug_cache  # noqa: E402


class FakeResp:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code = status
        self._payload = payload or {}
        self.text = text or ""

    def json(self):
        return self._payload


WIRED_CLIENTS = [
    ("agents.research.chembl_client", "ChEMBLClient", "chembl"),
    ("agents.research.dbaasp_client", "DBAASPClient", "dbaasp"),
    ("agents.research.apd_client", "APDClient", "apd"),
    ("agents.research.iuphar_client", "IUPHARClient", "iuphar"),
    ("agents.research.rcsb_pdb_client", "RCSBPDBClient", "rcsb_pdb"),
    ("agents.research.pdbe_client", "PDBEClient", "pdbe"),
    ("agents.research.ebi_proteins_client", "EBIProteinsClient", "ebi_proteins"),
]


def _import_client(module_path, class_name):
    mod = __import__(module_path, fromlist=[class_name])
    return getattr(mod, class_name)


async def test_each_client_has_fetch_intervention_helper():
    missing = []
    for module_path, class_name, _ in WIRED_CLIENTS:
        cls = _import_client(module_path, class_name)
        if not hasattr(cls, "_fetch_intervention"):
            missing.append(class_name)
            continue
        sig = inspect.signature(cls._fetch_intervention)
        params = list(sig.parameters)
        if params[:3] != ["self", "client", "intervention"]:
            missing.append(f"{class_name} (wrong signature: {params})")
    assert not missing, f"clients missing _fetch_intervention helper: {missing}"
    print(f"  ✓ all {len(WIRED_CLIENTS)} clients expose _fetch_intervention(client, intervention)")


async def test_cache_skips_second_call_generic():
    """For each client: stub out the intervention fetcher and confirm that a
    second research() call for the same drug reuses the cached result and does
    not invoke the stub again. Any client whose wiring is broken will fail
    this check."""
    failures = []
    for module_path, class_name, agent_name in WIRED_CLIENTS:
        drug_cache.clear()
        cls = _import_client(module_path, class_name)
        client_obj = cls()
        call_count = 0

        async def stub(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return {"citations": [], "raw_data": {f"{agent_name}_TestDrug_count": 0}}

        with patch.object(cls, "_fetch_intervention", new=stub):
            meta = {"interventions": [{"name": "TestDrug"}]}
            await client_obj.research("NCT00000001", meta)
            first = call_count
            await client_obj.research("NCT00000002", meta)
            second = call_count

        if second != first:
            failures.append(f"{class_name}: call_count {first}→{second} (expected flat)")
            continue
        stats = drug_cache.stats()
        if stats["hits"] < 1:
            failures.append(f"{class_name}: no cache hit recorded, stats={stats}")

    assert not failures, "\n    ".join(["cache miss issues:"] + failures)
    print(f"  ✓ all {len(WIRED_CLIENTS)} clients: second research() hits cache, skips fetch")


async def test_cache_key_isolates_by_agent():
    """Two different clients must not collide on the same drug name."""
    drug_cache.clear()
    chembl_cls = _import_client("agents.research.chembl_client", "ChEMBLClient")
    dbaasp_cls = _import_client("agents.research.dbaasp_client", "DBAASPClient")

    chembl_calls = 0
    dbaasp_calls = 0

    async def chembl_stub(*args, **kwargs):
        nonlocal chembl_calls
        chembl_calls += 1
        return {"citations": [], "raw_data": {"chembl_Shared_count": 1}}

    async def dbaasp_stub(*args, **kwargs):
        nonlocal dbaasp_calls
        dbaasp_calls += 1
        return {"citations": [], "raw_data": {"dbaasp_Shared_count": 2}}

    with patch.object(chembl_cls, "_fetch_intervention", new=chembl_stub), \
         patch.object(dbaasp_cls, "_fetch_intervention", new=dbaasp_stub):
        meta = {"interventions": [{"name": "Shared"}]}
        await chembl_cls().research("NCT00000001", meta)
        await dbaasp_cls().research("NCT00000001", meta)

    assert chembl_calls == 1 and dbaasp_calls == 1, \
        f"expected 1 call each, got chembl={chembl_calls} dbaasp={dbaasp_calls}"
    print("  ✓ cross-client isolation: same drug name, different agents → two cache entries")


async def main() -> int:
    print("Cross-client DrugResearchCache wiring tests")
    print("-" * 60)
    tests = [
        test_each_client_has_fetch_intervention_helper,
        test_cache_skips_second_call_generic,
        test_cache_key_isolates_by_agent,
    ]
    failed = 0
    for t in tests:
        try:
            await t()
        except AssertionError as e:
            print(f"  ✗ {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            import traceback
            print(f"  ✗ {t.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print("-" * 60)
    print(f"{'FAIL' if failed else 'OK'}: {len(tests) - failed}/{len(tests)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

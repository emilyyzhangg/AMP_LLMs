#!/usr/bin/env python3
"""
Wiring smoke test — ChEMBL client + DrugResearchCache.

Monkey-patches the HTTP layer so no network is used. Verifies:
  1. Refactor preserves output shape — citations list + raw_data dict
     matching v42.6.8 behavior.
  2. Second research() call for an NCT sharing the same intervention
     hits the cache and does NOT re-fetch.
  3. raw_data keys are intervention-prefixed and non-colliding across
     mergers.

Usage:
    cd <agent_annotate_dir>
    python3 scripts/test_chembl_cache_wiring.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch, AsyncMock

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

from agents.research.chembl_client import ChEMBLClient  # noqa: E402
from agents.research.drug_cache import drug_cache  # noqa: E402


class FakeResp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload or {}

    def json(self):
        return self._payload


def make_molecule_payload(name="Semaglutide", chembl_id="CHEMBL4297763"):
    return {
        "molecules": [{
            "molecule_chembl_id": chembl_id,
            "pref_name": name,
            "molecule_type": "Protein",
            "max_phase": 4,
            "helm_notation": "PEPTIDE1{H.S.E.G.T.F.T.S.D.V.S}$$$$",
            "first_approval": 2017,
            "molecule_synonyms": [{"molecule_synonym": name}],
            "molecule_properties": {"full_mwt": "4113.64", "alogp": None},
        }]
    }


async def test_output_shape():
    drug_cache.clear()
    client = ChEMBLClient()
    call_count = 0

    async def fake_get(url, client=None, params=None, headers=None):
        nonlocal call_count
        call_count += 1
        q = (params or {}).get("q", "")
        if "mechanism" in url:
            return FakeResp(200, {"mechanisms": [{"action_type": "AGONIST",
                                                   "mechanism_of_action": "GLP-1 receptor agonist"}]})
        if "activity" in url:
            return FakeResp(200, {"activities": []})
        return FakeResp(200, make_molecule_payload(q or "Semaglutide"))

    with patch("agents.research.chembl_client.resilient_get", AsyncMock(side_effect=fake_get)):
        metadata = {"interventions": [{"name": "Semaglutide"}]}
        result = await client.research("NCT00000001", metadata)

    assert result.agent_name == "chembl"
    assert result.nct_id == "NCT00000001"
    assert len(result.citations) >= 1, f"expected citations, got {len(result.citations)}"
    assert any("Semaglutide" in (c.snippet or "") for c in result.citations), \
        "snippet must mention intervention"
    assert "chembl_Semaglutide_count" in result.raw_data, \
        f"expected intervention-prefixed key, got {list(result.raw_data)}"
    assert "chembl_Semaglutide_molecules" in result.raw_data
    print("  ✓ output shape preserved (citations + intervention-prefixed raw_data)")


async def test_cache_hit_skips_network():
    drug_cache.clear()
    client = ChEMBLClient()
    call_count = 0

    async def fake_get(url, client=None, params=None, headers=None):
        nonlocal call_count
        call_count += 1
        if "mechanism" in url:
            return FakeResp(200, {"mechanisms": []})
        if "activity" in url:
            return FakeResp(200, {"activities": []})
        return FakeResp(200, make_molecule_payload("Semaglutide"))

    with patch("agents.research.chembl_client.resilient_get", AsyncMock(side_effect=fake_get)):
        meta = {"interventions": [{"name": "Semaglutide"}]}
        await client.research("NCT00000001", meta)
        first_calls = call_count
        # Second NCT, identical drug → cache hit, no new HTTP calls
        await client.research("NCT00000002", meta)
        second_calls = call_count

    assert second_calls == first_calls, \
        f"second research() should hit cache (calls={first_calls} vs {second_calls})"
    stats = drug_cache.stats()
    assert stats["hits"] >= 1, f"expected cache hit, stats={stats}"
    print(f"  ✓ second research() hits cache (HTTP calls flat at {first_calls}, stats={stats})")


async def test_multiple_interventions_distinct_keys():
    drug_cache.clear()
    client = ChEMBLClient()

    async def fake_get(url, client=None, params=None, headers=None):
        q = (params or {}).get("q", "")
        if "mechanism" in url:
            return FakeResp(200, {"mechanisms": []})
        if "activity" in url:
            return FakeResp(200, {"activities": []})
        return FakeResp(200, make_molecule_payload(q or "unknown", "CHEMBL_" + q))

    with patch("agents.research.chembl_client.resilient_get", AsyncMock(side_effect=fake_get)):
        meta = {"interventions": [{"name": "DrugA"}, {"name": "DrugB"}]}
        result = await client.research("NCT00000003", meta)

    # Both interventions should have their own raw_data keys (no collision)
    assert "chembl_DrugA_count" in result.raw_data
    assert "chembl_DrugB_count" in result.raw_data
    assert "chembl_DrugA_molecules" in result.raw_data
    assert "chembl_DrugB_molecules" in result.raw_data
    print("  ✓ multi-intervention results merge without collision")


async def main() -> int:
    print("ChEMBL + DrugResearchCache wiring tests")
    print("-" * 60)
    tests = [test_output_shape, test_cache_hit_skips_network,
             test_multiple_interventions_distinct_keys]
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

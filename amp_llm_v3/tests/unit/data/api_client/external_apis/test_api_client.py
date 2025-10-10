# tests/test_api_clients.py
import pytest
from amp_llm.data.api_clients.core import (
    ClinicalTrialsClient,
    PubMedClient,
    PMCBasicClient
)


@pytest.mark.asyncio
async def test_clinical_trials_client():
    async with ClinicalTrialsClient() as client:
        result = await client.fetch_by_id("NCT02950220")
        assert "nct_id" in result
        assert "clinical_trial_data" in result


@pytest.mark.asyncio
async def test_pubmed_client():
    async with PubMedClient() as client:
        pmids = await client.search("cancer immunotherapy", max_results=5)
        assert len(pmids["pmids"]) <= 5


@pytest.mark.asyncio
async def test_pmc_client():
    async with PMCBasicClient() as client:
        pmcids = await client.search("clinical trial", max_results=3)
        assert len(pmcids) <= 3
# tests/test_workflows.py
import pytest
from amp_llm.data.workflows import fetch_clinical_trial_and_pubmed_pmc


@pytest.mark.asyncio
async def test_core_workflow():
    result = await fetch_clinical_trial_and_pubmed_pmc("NCT02950220")
    
    assert result["nct_id"] == "NCT02950220"
    assert "sources" in result
    assert "clinical_trials" in result["sources"]
    assert "pubmed" in result["sources"]
    assert "pmc" in result["sources"]
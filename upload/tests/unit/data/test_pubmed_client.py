# tests/unit/data/test_pubmed_client.py

import pytest
from unittest.mock import AsyncMock, patch
from amp_llm.data.pubmed import PubMedClient, PubMedAPIError

@pytest.fixture
def pubmed_client():
    """Create PubMed client for testing."""
    return PubMedClient(api_key="test_key")

@pytest.fixture
def mock_response():
    """Mock PubMed API response."""
    return """<?xml version="1.0"?>
    <eSearchResult>
        <IdList>
            <Id>12345678</Id>
        </IdList>
    </eSearchResult>
    """

@pytest.mark.asyncio
async def test_search_success(pubmed_client, mock_response):
    """Test successful PubMed search."""
    with patch('aiohttp.ClientSession.get') as mock_get:
        mock_get.return_value.__aenter__.return_value.status = 200
        mock_get.return_value.__aenter__.return_value.text = AsyncMock(return_value=mock_response)
        
        results = await pubmed_client.search("test query")
        
        assert len(results) == 1
        assert results[0] == "12345678"

@pytest.mark.asyncio
async def test_search_api_error(pubmed_client):
    """Test PubMed API error handling."""
    with patch('aiohttp.ClientSession.get') as mock_get:
        mock_get.return_value.__aenter__.return_value.status = 500
        
        with pytest.raises(PubMedAPIError):
            await pubmed_client.search("test query")
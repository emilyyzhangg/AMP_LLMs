# amp_llm_v3/src/amp_llm/data/api_clients/core/pmc_basic.py
"""
PubMed Central (PMC) basic API client - fully migrated.
Replaces: data/clinical_trials/fetchers/pmc.py
"""
import requests
import aiohttp
import asyncio
import time
from typing import Dict, List, Any, Optional

from amp_llm.data.api_clients.base import BaseAPIClient, APIConfig
from amp_llm.config import get_logger

logger = get_logger(__name__)

# Configuration
DEFAULT_TIMEOUT = 15
SLEEP_BETWEEN_REQUESTS = 0.34

# =============================================================================
# NEW: Async Client Class
# =============================================================================

class PMCBasicClient(BaseAPIClient):
    """
    PubMed Central basic client for esearch and esummary.
    
    Replaces synchronous functions with async implementation.
    """
    
    @property
    def name(self) -> str:
        return "PMC"
    
    @property
    def base_url(self) -> str:
        return "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    
    async def search(self, query: str, max_results: int = None) -> List[str]:
        """
        Search PMC using esearch.
        
        Args:
            query: Search query
            max_results: Maximum results (defaults to config)
            
        Returns:
            List of PMC IDs
        """
        max_results = max_results or self.config.max_results
        
        url = f"{self.base_url}/esearch.fcgi"
        params = {
            "db": "pmc",
            "term": query,
            "retmode": "json",
            "retmax": max_results
        }
        
        try:
            async with await self._request("GET", url, params=params) as resp:
                data = await resp.json()
                pmcids = data.get("esearchresult", {}).get("idlist", [])
                
                if pmcids:
                    logger.info(f"{self.name}: found {len(pmcids)} matches")
                else:
                    logger.info(f"{self.name}: no matches found")
                
                return pmcids
        except Exception as e:
            logger.error(f"{self.name} esearch error: {e}")
            return []
    
    async def fetch_by_id(self, pmcid: str, **kwargs) -> Dict[str, Any]:
        """
        Fetch PMC metadata using esummary.
        
        Args:
            pmcid: PMC ID
            
        Returns:
            Dictionary with PMC metadata
        """
        url = f"{self.base_url}/esummary.fcgi"
        params = {
            "db": "pmc",
            "id": pmcid,
            "retmode": "json"
        }
        
        try:
            async with await self._request("GET", url, params=params) as resp:
                data = await resp.json()
                logger.info(f"{self.name}: fetched metadata for {pmcid}")
                return self._convert_summary(data, pmcid)
        except Exception as e:
            logger.error(f"{self.name} esummary error for {pmcid}: {e}")
            return {
                "error": str(e),
                "source": "pmc_esummary",
                "pmcid": pmcid
            }
    
    def _convert_summary(self, esummary: Dict, pmcid: str) -> Dict[str, Any]:
        """Extract metadata from esummary response."""
        result = esummary.get("result", {})
        
        if pmcid not in result:
            return {"pmcid": pmcid, "error": "Not found in response"}
        
        rec = result[pmcid]
        
        return {
            "pmcid": pmcid,
            "title": rec.get("title"),
            "journal": rec.get("source"),
            "pubdate": rec.get("pubdate"),
            "authors": [
                a.get("name") for a in rec.get("authors", [])
                if a.get("name")
            ],
            "doi": [
                aid.get("value")
                for aid in rec.get("articleids", [])
                if aid.get("idtype") == "doi"
            ],
            "pmid": rec.get("pmid"),
            "pmcid": rec.get("pmcid"),
            "volume": rec.get("volume"),
            "issue": rec.get("issue"),
            "pages": rec.get("pages"),
            "fulljournalname": rec.get("fulljournalname"),
            "sortpubdate": rec.get("sortpubdate"),
            "epubdate": rec.get("epubdate"),
            "essn": rec.get("essn"),
            "issn": rec.get("issn"),
        }


# =============================================================================
# OLD: Synchronous functions (kept for backward compatibility)
# =============================================================================

def search_pmc(query: str, max_results: int = 5) -> List[str]:
    """
    DEPRECATED: Use PMCBasicClient.search() instead.
    
    Search PMC using esearch (synchronous).
    """
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pmc", "term": query, "retmode": "json", "retmax": max_results}
    
    try:
        resp = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        ids = resp.json().get("esearchresult", {}).get("idlist", [])
        time.sleep(SLEEP_BETWEEN_REQUESTS)
        
        if ids:
            print(f"✅ PMC: found {len(ids)} matches.")
        else:
            print("⚠️ PMC: no matches found.")
        
        return ids
    except Exception as e:
        print(f"❌ PMC esearch error: {e}")
        return []


def fetch_pmc_esummary(pmcid: str) -> Dict:
    """
    DEPRECATED: Use PMCBasicClient.fetch_by_id() instead.
    
    Fetch PMC metadata using esummary (synchronous).
    """
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    params = {"db": "pmc", "id": pmcid, "retmode": "json"}
    
    try:
        resp = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        time.sleep(SLEEP_BETWEEN_REQUESTS)
        print(f"✅ PMC: fetched metadata for {pmcid}")
        return resp.json()
    except Exception as e:
        print(f"❌ PMC esummary error for {pmcid}: {e}")
        return {"error": str(e), "source": "pmc_esummary", "pmcid": pmcid}


def convert_pmc_summary_to_metadata(esum: Dict) -> Dict:
    """
    DEPRECATED: Use PMCBasicClient._convert_summary() instead.
    
    Extract detailed metadata from PMC esummary response (synchronous).
    """
    result = {}
    res = esum.get("result", {})
    
    for uid in res.get("uids", []):
        rec = res.get(uid, {})
        result[uid] = {
            "title": rec.get("title"),
            "journal": rec.get("source"),
            "pubdate": rec.get("pubdate"),
            "authors": [a.get("name") for a in rec.get("authors", []) if a.get("name")],
            "doi": [aid.get("value") for aid in rec.get("articleids", []) if aid.get("idtype") == "doi"],
            "pmid": rec.get("pmid"),
            "pmcid": rec.get("pmcid"),
            "volume": rec.get("volume"),
            "issue": rec.get("issue"),
            "pages": rec.get("pages"),
            "fulljournalname": rec.get("fulljournalname"),
            "sortpubdate": rec.get("sortpubdate"),
            "epubdate": rec.get("epubdate"),
            "essn": rec.get("essn"),
            "issn": rec.get("issn"),
        }
    
    return result
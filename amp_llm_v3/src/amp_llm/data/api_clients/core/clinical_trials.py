"""
ClinicalTrials.gov API client - FIXED with proper async class.
Handles fetching trial data from ClinicalTrials.gov API (v2 and legacy).
"""
import aiohttp
import asyncio
from typing import Dict, Any, Optional

from amp_llm.data.api_clients.base import BaseAPIClient, APIConfig
from amp_llm.config import get_logger

logger = get_logger(__name__)

# API endpoints
CTG_V2_BASE = "https://clinicaltrials.gov/api/v2/studies"
CTG_LEGACY_FULL = "https://clinicaltrials.gov/api/query/full_studies"


class ClinicalTrialsClient(BaseAPIClient):
    """
    ClinicalTrials.gov API client with async context manager support.
    
    Tries multiple endpoints in order:
    1. ClinicalTrials.gov v2 detail endpoint
    2. ClinicalTrials.gov v2 search endpoint
    3. ClinicalTrials.gov legacy endpoint
    
    Usage:
        async with ClinicalTrialsClient() as client:
            data = await client.fetch_by_id("NCT12345678")
    """
    
    @property
    def name(self) -> str:
        return "ClinicalTrials.gov"
    
    @property
    def base_url(self) -> str:
        return CTG_V2_BASE
    
    async def search(self, query: str, **kwargs) -> Dict[str, Any]:
        """
        Search for clinical trials.
        
        Args:
            query: Search query (NCT number, condition, etc.)
            
        Returns:
            Dictionary with search results
        """
        params = {
            "query.term": query,
            "pageSize": self.config.max_results
        }
        
        try:
            async with await self._request("GET", self.base_url, params=params) as resp:
                data = await resp.json()
                studies = data.get("studies", [])
                
                logger.info(f"{self.name}: Found {len(studies)} result(s)")
                
                return {
                    "studies": studies,
                    "total_count": len(studies)
                }
        
        except Exception as e:
            logger.error(f"{self.name} search error: {e}")
            return {"studies": [], "error": str(e)}
    
    async def fetch_by_id(self, nct_id: str, **kwargs) -> Dict[str, Any]:
        """
        Fetch clinical trial by NCT ID.
        
        Tries multiple endpoints in order for best reliability.
        
        Args:
            nct_id: NCT number (e.g., "NCT12345678")
            
        Returns:
            Dictionary with trial data or error information
        """
        nct = nct_id.strip().upper()
        
        # Try v2 detail endpoint first
        logger.info(f"{self.name}: Fetching {nct} from v2 detail endpoint")
        result = await self._try_v2_detail(nct)
        if "error" not in result:
            return result
        
        # Try v2 search fallback
        logger.info(f"{self.name}: Trying v2 search fallback for {nct}")
        result = await self._try_v2_search(nct)
        if "error" not in result:
            return result
        
        # Try legacy fallback
        logger.info(f"{self.name}: Trying legacy endpoint for {nct}")
        result = await self._try_legacy(nct)
        return result
    
    async def _try_v2_detail(self, nct: str) -> Dict[str, Any]:
        """Try v2 detail endpoint."""
        url = f"{CTG_V2_BASE}/{nct}"
        
        try:
            async with await self._request("GET", url) as resp:
                data = await resp.json()
                logger.info(f"{self.name}: Study found via v2 detail")
                
                return {
                    "nct_id": nct,
                    "clinical_trial_data": data,
                    "source": "clinicaltrials_v2_detail"
                }
        
        except Exception as e:
            logger.debug(f"v2 detail failed: {e}")
            return {"error": str(e)}
    
    async def _try_v2_search(self, nct: str) -> Dict[str, Any]:
        """Try v2 search endpoint."""
        params = {"query.term": nct, "pageSize": 1}
        
        try:
            async with await self._request("GET", CTG_V2_BASE, params=params) as resp:
                data = await resp.json()
                studies = data.get("studies", [])
                
                if studies:
                    logger.info(f"{self.name}: Study found via v2 search")
                    return {
                        "nct_id": nct,
                        "clinical_trial_data": studies[0],
                        "source": "clinicaltrials_v2_search"
                    }
                
                return {"error": "No results in v2 search"}
        
        except Exception as e:
            logger.debug(f"v2 search failed: {e}")
            return {"error": str(e)}
    
    async def _try_legacy(self, nct: str) -> Dict[str, Any]:
        """Try legacy endpoint."""
        params = {
            "expr": nct,
            "min_rnk": 1,
            "max_rnk": 1,
            "fmt": "json"
        }
        
        try:
            async with await self._request("GET", CTG_LEGACY_FULL, params=params) as resp:
                data = await resp.json()
                studies = data.get("FullStudiesResponse", {}).get("FullStudies", [])
                
                if studies:
                    logger.info(f"{self.name}: Study found via legacy endpoint")
                    return {
                        "nct_id": nct,
                        "clinical_trial_data": studies[0].get("Study", {}),
                        "source": "clinicaltrials_legacy_full"
                    }
                
                return {
                    "error": f"No study found for {nct}",
                    "source": "clinicaltrials_not_found"
                }
        
        except Exception as e:
            logger.error(f"Legacy endpoint error: {e}")
            return {
                "error": str(e),
                "source": "clinicaltrials_legacy_error"
            }


# =============================================================================
# BACKWARD COMPATIBILITY: Keep synchronous function for old code
# =============================================================================

def fetch_clinical_trial_data(nct_id: str) -> Dict[str, Any]:
    """
    DEPRECATED: Synchronous fetch of clinical trial data.
    
    Use ClinicalTrialsClient.fetch_by_id() instead for async code.
    
    This function is kept for backward compatibility only.
    """
    import requests
    
    nct = nct_id.strip().upper()
    
    # Try v2 detail endpoint first
    v2_detail_url = f"{CTG_V2_BASE}/{nct}"
    
    print(f"🔍 ClinicalTrials.gov v2: fetching {v2_detail_url}")
    try:
        resp = requests.get(v2_detail_url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            print("✅ ClinicalTrials.gov v2: Study found (detail).")
            return {
                "nct_id": nct,
                "clinical_trial_data": data,
                "source": "clinicaltrials_v2_detail"
            }
        elif resp.status_code == 404:
            print("⚠️ ClinicalTrials.gov v2: detail endpoint returned 404 — trying search fallback.")
        else:
            resp.raise_for_status()
    except Exception as e:
        print(f"❌ ClinicalTrials.gov v2 detail failed: {e}")
    
    # Try v2 search fallback
    try:
        params = {"query.term": nct, "pageSize": 1}
        print(f"🔍 ClinicalTrials.gov v2: searching with params {params}")
        resp2 = requests.get(CTG_V2_BASE, params=params, timeout=15)
        if resp2.status_code == 200:
            data2 = resp2.json()
            studies = data2.get("studies", [])
            if studies:
                print("✅ ClinicalTrials.gov v2: Study found via search.")
                return {
                    "nct_id": nct,
                    "clinical_trial_data": studies[0],
                    "source": "clinicaltrials_v2_search"
                }
            print("⚠️ ClinicalTrials.gov v2: no results found in search.")
    except Exception as e:
        print(f"❌ ClinicalTrials.gov v2 search failed: {e}")
    
    # Try legacy fallback
    try:
        params = {"expr": nct, "min_rnk": 1, "max_rnk": 1, "fmt": "json"}
        print("🔍 ClinicalTrials.gov legacy fallback: querying full_studies ...")
        resp3 = requests.get(CTG_LEGACY_FULL, params=params, timeout=15)
        resp3.raise_for_status()
        data3 = resp3.json()
        studies = data3.get("FullStudiesResponse", {}).get("FullStudies", [])
        if studies:
            print("✅ ClinicalTrials.gov legacy: Study found.")
            return {
                "nct_id": nct,
                "clinical_trial_data": studies[0].get("Study", {}),
                "source": "clinicaltrials_legacy_full"
            }
        else:
            print("❌ ClinicalTrials.gov legacy: no study found.")
            return {
                "error": f"No study found for {nct}",
                "source": "clinicaltrials_not_found"
            }
    except Exception as e:
        print(f"❌ ClinicalTrials.gov legacy error: {e}")
        return {
            "error": str(e),
            "source": "clinicaltrials_legacy_error"
        }
"""
ClinicalTrials.gov data fetcher.
Handles fetching trial data from ClinicalTrials.gov API (v2 and legacy).
"""
import requests
import aiohttp
import asyncio
from typing import Dict, Any, Optional
from amp_llm.config import get_logger

logger = get_logger(__name__)

# Configuration
DEFAULT_TIMEOUT = 15
CTG_V2_BASE = "https://clinicaltrials.gov/api/v2/studies"
CTG_LEGACY_FULL = "https://clinicaltrials.gov/api/query/full_studies"


def fetch_clinical_trial_data(nct_id: str) -> Dict[str, Any]:
    """
    Synchronous fetch of clinical trial data.
    
    Tries multiple endpoints in order:
    1. ClinicalTrials.gov v2 detail endpoint
    2. ClinicalTrials.gov v2 search endpoint
    3. ClinicalTrials.gov legacy endpoint
    
    Args:
        nct_id: NCT number (e.g., "NCT12345678")
        
    Returns:
        Dictionary with trial data or error information
    """
    nct = nct_id.strip().upper()
    
    # Try v2 detail endpoint first
    v2_detail_url = f"{CTG_V2_BASE}/{nct}"
    
    print(f"🔍 ClinicalTrials.gov v2: fetching {v2_detail_url}")
    try:
        resp = requests.get(v2_detail_url, timeout=DEFAULT_TIMEOUT)
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
        resp2 = requests.get(CTG_V2_BASE, params=params, timeout=DEFAULT_TIMEOUT)
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
        resp3 = requests.get(CTG_LEGACY_FULL, params=params, timeout=DEFAULT_TIMEOUT)
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
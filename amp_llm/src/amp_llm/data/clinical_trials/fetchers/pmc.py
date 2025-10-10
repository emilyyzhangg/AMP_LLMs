"""
PubMed Central (PMC) data fetcher.
Handles searching and fetching metadata from PMC via NCBI E-utilities.
"""
import requests
import time
from typing import Dict, List

# Configuration
DEFAULT_TIMEOUT = 15
SLEEP_BETWEEN_REQUESTS = 0.34


def search_pmc(query: str, max_results: int = 5) -> List[str]:
    """
    Search PMC using esearch.
    
    Args:
        query: Search query
        max_results: Maximum number of results
        
    Returns:
        List of PMC IDs
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
    Fetch PMC metadata using esummary.
    
    Args:
        pmcid: PMC ID
        
    Returns:
        Dictionary with PMC metadata
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
    Extract detailed metadata from PMC esummary response.
    
    Args:
        esum: Raw esummary JSON response
        
    Returns:
        Dictionary with structured metadata keyed by PMC ID
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
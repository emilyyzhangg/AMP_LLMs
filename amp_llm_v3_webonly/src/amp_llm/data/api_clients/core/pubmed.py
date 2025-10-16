# amp_llm_v3/src/amp_llm/data/api_clients/core/pubmed.py
"""
PubMed API client - fully migrated and async.
Replaces: data/clinical_trials/fetchers/pubmed.py
"""
import xml.etree.ElementTree as ET
import aiohttp
import asyncio
from typing import Dict, List, Any, Optional

from amp_llm.data.api_clients.base import BaseAPIClient, APIConfig
from amp_llm.config import get_logger

logger = get_logger(__name__)


class PubMedClient(BaseAPIClient):
    """
    PubMed client using NCBI E-utilities.
    
    Replaces: data/clinical_trials/fetchers/pubmed.py
    """
    
    @property
    def name(self) -> str:
        return "PubMed"
    
    @property
    def base_url(self) -> str:
        return "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    
    async def search(self, query: str, max_results: int = None) -> Dict[str, Any]:
        """
        Search PubMed using esearch.
        
        Args:
            query: Search query
            max_results: Maximum results (defaults to config)
            
        Returns:
            Dictionary with PMIDs
        """
        max_results = max_results or self.config.max_results
        
        url = f"{self.base_url}/esearch.fcgi"
        params = {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": max_results
        }
        
        logger.info(f"{self.name}: Searching for '{query[:100]}'...")
        
        try:
            async with await self._request("GET", url, params=params) as resp:
                data = await resp.json()
                pmids = data.get("esearchresult", {}).get("idlist", [])
                
                logger.info(f"{self.name}: Found {len(pmids)} result(s)")
                
                return {
                    "pmids": pmids,
                    "count": len(pmids),
                    "query": query
                }
        
        except Exception as e:
            logger.error(f"{self.name} search error: {e}")
            return {"error": str(e), "pmids": []}
    
    async def fetch_by_id(self, pmid: str, **kwargs) -> Dict[str, Any]:
        """
        Fetch PubMed article by PMID.
        
        Args:
            pmid: PubMed ID
            
        Returns:
            Article metadata
        """
        url = f"{self.base_url}/efetch.fcgi"
        params = {
            "db": "pubmed",
            "id": pmid,
            "retmode": "xml"
        }
        
        logger.info(f"{self.name}: Fetching PMID {pmid}")
        
        try:
            async with await self._request("GET", url, params=params) as resp:
                xml_content = await resp.text()
                metadata = self._parse_xml(xml_content, pmid)
                
                logger.info(f"{self.name}: Retrieved {pmid}")
                return metadata
        
        except Exception as e:
            logger.error(f"{self.name} fetch error for {pmid}: {e}")
            return {"error": str(e), "pmid": pmid}
    
    async def search_by_title_authors(
        self,
        title: str,
        authors: List[str]
    ) -> str:
        """
        Search PubMed by title and authors.
        
        Args:
            title: Article title
            authors: List of author names
            
        Returns:
            First PMID or empty string
        """
        # Build query
        query_parts = []
        
        if title:
            title_words = title.split()[:5]
            query_parts.append(" ".join(title_words))
        
        if authors:
            author = authors[0]
            if "," in author:
                last_name = author.split(",")[0].strip()
            else:
                parts = author.split()
                last_name = parts[-1] if parts else author
            query_parts.append(f"{last_name}[Author]")
        
        query = " AND ".join(query_parts)
        
        result = await self.search(query, max_results=1)
        pmids = result.get("pmids", [])
        
        return pmids[0] if pmids else ""
    
    def _parse_xml(self, xml_content: str, pmid: str) -> Dict[str, Any]:
        """Parse PubMed XML response."""
        try:
            root = ET.fromstring(xml_content)
            article = root.find(".//Article")
            
            if article is None:
                return {"pmid": pmid, "error": "No article data"}
            
            # Extract fields
            title_elem = article.find(".//ArticleTitle")
            title = title_elem.text if title_elem is not None else ""
            
            journal_elem = article.find(".//Journal/Title")
            journal = journal_elem.text if journal_elem is not None else ""
            
            pub_date = article.find(".//PubDate")
            year = ""
            if pub_date is not None:
                year_elem = pub_date.find("Year")
                year = year_elem.text if year_elem is not None else ""
            
            # Extract authors
            authors = []
            for author in article.findall(".//Author"):
                last = author.find("LastName")
                first = author.find("ForeName")
                if last is not None and first is not None:
                    authors.append(f"{last.text}, {first.text}")
                elif last is not None:
                    authors.append(last.text)
            
            # Extract abstract
            abstract_elem = article.find(".//Abstract/AbstractText")
            abstract = abstract_elem.text if abstract_elem is not None else ""
            
            return {
                "pmid": pmid,
                "title": title,
                "journal": journal,
                "publication_date": year,
                "authors": authors,
                "abstract": abstract,
                "source": "pubmed"
            }
        
        except Exception as e:
            logger.error(f"XML parse error for {pmid}: {e}")
            return {"pmid": pmid, "error": str(e)}
        
# =============================================================================
# OLD: Synchronous functions (kept for backward compatibility)
# =============================================================================

import requests
import time

DEFAULT_TIMEOUT = 15
SLEEP_BETWEEN_REQUESTS = 0.34


def search_pubmed_esearch(query: str, max_results: int = 10) -> List[str]:
    """
    DEPRECATED: Use PubMedClient.search() instead.
    
    Search PubMed using esearch (synchronous).
    """
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": query, "retmode": "json", "retmax": max_results}
    
    try:
        resp = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        pmids = resp.json().get("esearchresult", {}).get("idlist", [])
        time.sleep(SLEEP_BETWEEN_REQUESTS)
        
        if pmids:
            print(f"✅ PubMed: found {len(pmids)} matches.")
        else:
            print("⚠️ PubMed: no matches found.")
        
        return pmids
    except Exception as e:
        print(f"❌ PubMed esearch error: {e}")
        return []


def fetch_pubmed_by_pmid(pmid: str) -> Dict[str, Any]:
    """
    DEPRECATED: Use PubMedClient.fetch_by_id() instead.
    
    Fetch PubMed article metadata (synchronous).
    """
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {"db": "pubmed", "id": pmid, "retmode": "xml"}
    
    try:
        resp = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        time.sleep(SLEEP_BETWEEN_REQUESTS)
        
        xml_content = resp.text
        
        # Parse XML
        root = ET.fromstring(xml_content)
        article = root.find(".//Article")
        
        if article is None:
            return {"pmid": pmid, "error": "No article data"}
        
        title_elem = article.find(".//ArticleTitle")
        title = title_elem.text if title_elem is not None else ""
        
        journal_elem = article.find(".//Journal/Title")
        journal = journal_elem.text if journal_elem is not None else ""
        
        pub_date = article.find(".//PubDate")
        year = ""
        if pub_date is not None:
            year_elem = pub_date.find("Year")
            year = year_elem.text if year_elem is not None else ""
        
        authors = []
        for author in article.findall(".//Author"):
            last = author.find("LastName")
            first = author.find("ForeName")
            if last is not None and first is not None:
                authors.append(f"{last.text}, {first.text}")
        
        print(f"✅ PubMed: fetched metadata for PMID {pmid}")
        return {
            "pmid": pmid,
            "title": title,
            "journal": journal,
            "publication_date": year,
            "authors": authors,
            "source": "pubmed"
        }
    except Exception as e:
        print(f"❌ PubMed efetch error for {pmid}: {e}")
        return {"error": str(e), "pmid": pmid}


def search_pubmed_by_title_authors(title: str, authors: List[str]) -> str:
    """
    DEPRECATED: Use PubMedClient.search_by_title_authors() instead.
    
    Search PubMed by title and authors (synchronous).
    """
    query_parts = []
    
    if title:
        title_words = title.split()[:5]
        query_parts.append(" ".join(title_words))
    
    if authors:
        author = authors[0]
        if "," in author:
            last_name = author.split(",")[0].strip()
        else:
            parts = author.split()
            last_name = parts[-1] if parts else author
        query_parts.append(f"{last_name}[Author]")
    
    query = " AND ".join(query_parts)
    pmids = search_pubmed_esearch(query, max_results=1)
    
    return pmids[0] if pmids else ""
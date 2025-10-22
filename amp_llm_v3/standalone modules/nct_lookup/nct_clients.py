"""
NCT Database Clients
===================

Individual client implementations for each database.
"""

import asyncio
import aiohttp
import json
from typing import Dict, List, Any, Optional
from abc import ABC, abstractmethod
import xml.etree.ElementTree as ET
import logging

logger = logging.getLogger(__name__)


class BaseClient(ABC):
    """Base class for all database clients."""
    
    def __init__(self, session: aiohttp.ClientSession, api_key: Optional[str] = None):
        self.session = session
        self.api_key = api_key
        self.rate_limit_delay = 0.34  # NCBI recommends 3 requests/second
    
    @abstractmethod
    async def fetch(self, identifier: str) -> Dict[str, Any]:
        """Fetch data by identifier."""
        pass
    
    @abstractmethod
    async def search(self, query: str, **kwargs) -> Any:
        """Search database."""
        pass
    
    async def _rate_limit(self):
        """Enforce rate limiting."""
        await asyncio.sleep(self.rate_limit_delay)


class ClinicalTrialsClient(BaseClient):
    """ClinicalTrials.gov API client."""
    
    BASE_URL = "https://clinicaltrials.gov/api/v2/studies"
    
    async def fetch(self, nct_id: str) -> Dict[str, Any]:
        """Fetch trial data by NCT ID."""
        url = f"{self.BASE_URL}/{nct_id}"
        
        try:
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    logger.info(f"Fetched {nct_id} from ClinicalTrials.gov")
                    return data
                else:
                    return {"error": f"HTTP {resp.status}"}
        except Exception as e:
            logger.error(f"ClinicalTrials fetch error: {e}")
            return {"error": str(e)}
    
    async def search(self, query: str, **kwargs) -> Dict[str, Any]:
        """Search ClinicalTrials.gov."""
        params = {
            "query.term": query,
            "pageSize": kwargs.get("max_results", 10)
        }
        
        try:
            async with self.session.get(self.BASE_URL, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data
                else:
                    return {"error": f"HTTP {resp.status}"}
        except Exception as e:
            return {"error": str(e)}


class PubMedClient(BaseClient):
    """PubMed API client."""
    
    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    
    async def search(self, query: str, max_results: int = 10) -> List[str]:
        """Search PubMed, return PMIDs."""
        url = f"{self.BASE_URL}/esearch.fcgi"
        params = {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": max_results
        }
        
        if self.api_key:
            params["api_key"] = self.api_key
        
        try:
            await self._rate_limit()
            async with self.session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    pmids = data.get("esearchresult", {}).get("idlist", [])
                    logger.info(f"PubMed search found {len(pmids)} results")
                    return pmids
                return []
        except Exception as e:
            logger.error(f"PubMed search error: {e}")
            return []
    
    async def fetch(self, pmid: str) -> Dict[str, Any]:
        """Fetch article metadata by PMID."""
        url = f"{self.BASE_URL}/efetch.fcgi"
        params = {
            "db": "pubmed",
            "id": pmid,
            "retmode": "xml"
        }
        
        if self.api_key:
            params["api_key"] = self.api_key
        
        try:
            await self._rate_limit()
            async with self.session.get(url, params=params) as resp:
                if resp.status == 200:
                    xml_content = await resp.text()
                    return self._parse_xml(xml_content, pmid)
                return {"error": f"HTTP {resp.status}"}
        except Exception as e:
            logger.error(f"PubMed fetch error: {e}")
            return {"error": str(e)}
    
    async def search_by_title_authors(
        self,
        title: str,
        authors: List[str]
    ) -> Optional[str]:
        """Search by title and authors, return first PMID."""
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
        pmids = await self.search(query, max_results=1)
        
        return pmids[0] if pmids else None
    
    def _parse_xml(self, xml_content: str, pmid: str) -> Dict[str, Any]:
        """Parse PubMed XML response."""
        try:
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
            
            abstract_elem = article.find(".//Abstract/AbstractText")
            abstract = abstract_elem.text if abstract_elem is not None else ""
            
            return {
                "pmid": pmid,
                "title": title,
                "journal": journal,
                "year": year,
                "authors": authors,
                "abstract": abstract
            }
        except Exception as e:
            logger.error(f"XML parse error: {e}")
            return {"pmid": pmid, "error": str(e)}


class PMCClient(BaseClient):
    """PubMed Central API client."""
    
    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    
    async def search(self, query: str, max_results: int = 10) -> List[str]:
        """Search PMC, return PMC IDs."""
        url = f"{self.BASE_URL}/esearch.fcgi"
        params = {
            "db": "pmc",
            "term": query,
            "retmode": "json",
            "retmax": max_results
        }
        
        if self.api_key:
            params["api_key"] = self.api_key
        
        try:
            await self._rate_limit()
            async with self.session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    pmcids = data.get("esearchresult", {}).get("idlist", [])
                    logger.info(f"PMC search found {len(pmcids)} results")
                    return pmcids
                return []
        except Exception as e:
            logger.error(f"PMC search error: {e}")
            return []
    
    async def fetch(self, pmcid: str) -> Dict[str, Any]:
        """Fetch article metadata by PMC ID."""
        url = f"{self.BASE_URL}/esummary.fcgi"
        params = {
            "db": "pmc",
            "id": pmcid,
            "retmode": "json"
        }
        
        if self.api_key:
            params["api_key"] = self.api_key
        
        try:
            await self._rate_limit()
            async with self.session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return self._parse_summary(data, pmcid)
                return {"error": f"HTTP {resp.status}"}
        except Exception as e:
            logger.error(f"PMC fetch error: {e}")
            return {"error": str(e)}
    
    def _parse_summary(self, data: Dict, pmcid: str) -> Dict[str, Any]:
        """Parse PMC esummary response."""
        result = data.get("result", {})
        
        if pmcid not in result:
            return {"pmcid": pmcid, "error": "Not found"}
        
        rec = result[pmcid]
        
        return {
            "pmcid": pmcid,
            "title": rec.get("title"),
            "journal": rec.get("fulljournalname"),
            "pubdate": rec.get("pubdate"),
            "authors": [
                a.get("name") for a in rec.get("authors", [])
                if a.get("name")
            ],
            "doi": [
                aid.get("value")
                for aid in rec.get("articleids", [])
                if aid.get("idtype") == "doi"
            ]
        }
    
class PMCBioClient(BaseClient):
    """PMC BioC API client."""
    
    async def fetch(self, identifier: str) -> Dict[str, Any]:
        """
        Fetch article by PMID/PMCID (implements BaseClient abstract method).
        This is a wrapper around fetch_pmc_bioc for consistency with base class.
        
        Args:
            identifier: PubMed ID or PMC ID
            
        Returns:
            Dict containing BioC formatted article data or error
        """
        return await self.fetch_pmc_bioc(identifier, format="json", encoding="unicode")
    
    async def search(self, query: str, **kwargs) -> Dict[str, Any]:
        """
        BioC API does not support search functionality.
        Use PubMed/PMC to find PMIDs first, then use fetch() to get BioC data.
        
        Args:
            query: Search query (not used - BioC doesn't support search)
            **kwargs: Additional parameters (not used)
            
        Returns:
            Error dict explaining BioC doesn't support search
        """
        return {
            "error": "BioC API does not support search",
            "message": "Use PubMed or PMC to find PMIDs first, then fetch individual articles"
        }
    
    async def fetch_pmc_bioc(
        self,
        pmid: str,
        format: str = "json",
        encoding: str = "unicode"
    ) -> Dict[str, Any]:
        """
        Fetch article from PubMed Central Open Access in BioC format.
        
        Args:
            pmid: PubMed ID or PMC ID
            format: 'xml' or 'json'
            encoding: 'unicode' or 'ascii'
        
        Returns:
            Dict containing BioC formatted article data or error
        """
        base_url = "https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi"
        url = f"{base_url}/BioC_{format}/{pmid}/{encoding}"
        
        try:
            await self._rate_limit()
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    if format == "json":
                        data = await resp.json()
                        logger.info(f"PMC BioC fetch successful for {pmid}")
                        return data
                    else:  # xml
                        xml_content = await resp.text()
                        logger.info(f"PMC BioC fetch successful for {pmid}")
                        return {"xml": xml_content}
                elif resp.status == 404:
                    logger.warning(f"Article {pmid} not found in PMC Open Access")
                    return {"error": "Article not available in PMC Open Access"}
                else:
                    logger.error(f"PMC BioC fetch error: HTTP {resp.status}")
                    return {"error": f"HTTP {resp.status}"}
        except Exception as e:
            logger.error(f"PMC BioC fetch error for {pmid}: {e}")
            return {"error": str(e)}


    async def fetch_multiple_pmc_bioc(
        self,
        pmids: List[str],
        format: str = "json",
        encoding: str = "unicode"
    ) -> Dict[str, Dict[str, Any]]:
        """
        Fetch multiple articles from PMC Open Access in BioC format.
        
        Args:
            pmids: List of PubMed IDs or PMC IDs
            format: 'xml' or 'json'
            encoding: 'unicode' or 'ascii'
        
        Returns:
            Dict mapping PMIDs to their BioC data
        """
        results = {}
        
        for pmid in pmids:
            result = await self.fetch_pmc_bioc(pmid, format, encoding)
            results[pmid] = result
        
        logger.info(f"Fetched {len(results)} articles from PMC BioC")
        return results


class DuckDuckGoClient(BaseClient):
    """DuckDuckGo search client."""
    
    async def search(
        self,
        nct_id: str,
        title: str,
        condition: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search DuckDuckGo."""
        try:
            from duckduckgo_search import DDGS
            
            # Build query
            query_parts = [nct_id]
            if title:
                query_parts.append(" ".join(title.split()[:10]))
            if condition:
                query_parts.append(condition)
            
            query = " ".join(query_parts)
            
            # Run search in executor (blocking operation)
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                self._search_sync,
                query
            )
            
            logger.info(f"DuckDuckGo found {len(results)} results")
            
            return {
                "query": query,
                "results": results,
                "total_found": len(results)
            }
            
        except ImportError:
            return {"error": "duckduckgo-search not installed"}
        except Exception as e:
            logger.error(f"DuckDuckGo error: {e}")
            return {"error": str(e)}
    
    def _search_sync(self, query: str) -> List[Dict]:
        """Synchronous search helper."""
        from duckduckgo_search import DDGS
        
        results = []
        with DDGS() as ddgs:
            search_results = ddgs.text(query, max_results=10)
            for result in search_results:
                results.append({
                    'title': result.get('title', ''),
                    'url': result.get('href', ''),
                    'snippet': result.get('body', '')
                })
        
        return results
    
    async def fetch(self, identifier: str) -> Dict[str, Any]:
        """Not implemented for DuckDuckGo."""
        return {"error": "Fetch not supported"}


class SerpAPIClient(BaseClient):
    """SERP API (Google Search) client."""
    
    BASE_URL = "https://serpapi.com/search"
    
    async def search(
        self,
        nct_id: str,
        title: str,
        condition: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search via SERP API."""
        if not self.api_key:
            return {"error": "SERPAPI_KEY not configured"}
        
        query_parts = [nct_id]
        if title:
            query_parts.append(" ".join(title.split()[:10]))
        if condition:
            query_parts.append(condition)
        
        query = " ".join(query_parts)
        
        params = {
            'q': query,
            'api_key': self.api_key,
            'num': 10,
            'engine': 'google'
        }
        
        try:
            async with self.session.get(self.BASE_URL, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = [
                        {
                            'title': r.get('title', ''),
                            'url': r.get('link', ''),
                            'snippet': r.get('snippet', '')
                        }
                        for r in data.get('organic_results', [])
                    ]
                    
                    logger.info(f"SERP API found {len(results)} results")
                    
                    return {
                        "query": query,
                        "results": results,
                        "total_found": len(results)
                    }
                else:
                    return {"error": f"HTTP {resp.status}"}
        except Exception as e:
            logger.error(f"SERP API error: {e}")
            return {"error": str(e)}
    
    async def fetch(self, identifier: str) -> Dict[str, Any]:
        """Not implemented."""
        return {"error": "Fetch not supported"}


class GoogleScholarClient(BaseClient):
    """Google Scholar via SERP API."""
    
    BASE_URL = "https://serpapi.com/search"
    
    async def search(
        self,
        nct_id: str,
        title: str,
        condition: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search Google Scholar."""
        if not self.api_key:
            return {"error": "SERPAPI_KEY not configured"}
        
        query_parts = [nct_id]
        if title:
            query_parts.append(" ".join(title.split()[:10]))
        if condition:
            query_parts.append(condition)
        
        query = " ".join(query_parts)
        
        params = {
            'q': query,
            'api_key': self.api_key,
            'num': 10,
            'engine': 'google_scholar'
        }
        
        try:
            async with self.session.get(self.BASE_URL, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = [
                        {
                            'title': r.get('title', ''),
                            'url': r.get('link', ''),
                            'snippet': r.get('snippet', ''),
                            'cited_by': r.get('inline_links', {}).get('cited_by', {}).get('total')
                        }
                        for r in data.get('organic_results', [])
                    ]
                    
                    logger.info(f"Scholar found {len(results)} results")
                    
                    return {
                        "query": query,
                        "results": results,
                        "total_found": len(results)
                    }
                else:
                    return {"error": f"HTTP {resp.status}"}
        except Exception as e:
            logger.error(f"Scholar error: {e}")
            return {"error": str(e)}
    
    async def fetch(self, identifier: str) -> Dict[str, Any]:
        """Not implemented."""
        return {"error": "Fetch not supported"}


class OpenFDAClient(BaseClient):
    """OpenFDA API client."""
    
    BASE_URL = "https://api.fda.gov/drug"
    
    async def search(self, query: str) -> Dict[str, Any]:
        """Search OpenFDA drug database."""
        if not query:
            return {"error": "No query provided"}
        
        url = f"{self.BASE_URL}/label.json"
        params = {
            "search": f"openfda.generic_name:\"{query}\" OR openfda.brand_name:\"{query}\"",
            "limit": 5
        }
        
        try:
            async with self.session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = data.get("results", [])
                    
                    logger.info(f"OpenFDA found {len(results)} results")
                    
                    return {
                        "query": query,
                        "results": results,
                        "total_found": len(results)
                    }
                else:
                    return {"error": f"HTTP {resp.status}"}
        except Exception as e:
            logger.error(f"OpenFDA error: {e}")
            return {"error": str(e)}
    
    async def fetch(self, identifier: str) -> Dict[str, Any]:
        """Not implemented."""
        return {"error": "Fetch not supported"}
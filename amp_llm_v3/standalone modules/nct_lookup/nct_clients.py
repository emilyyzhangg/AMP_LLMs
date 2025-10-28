"""
NCT Database Clients
===================

Individual client implementations for each database.
Enhanced with comprehensive error handling and improved search strategies.
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
    
    async def convert_pmcids_to_pmids(self, pmcids: List[str]) -> Dict[str, str]:
        """
        Convert PMCIDs to PMIDs using NCBI ID Converter API.
        
        Args:
            pmcids: List of PMC IDs (e.g., ['PMC1193645', 'PMC1134901'])
            
        Returns:
            Dict mapping PMCID to PMID (e.g., {'PMC1193645': '14699080'})
        """
        if not pmcids:
            return {}
        
        # Ensure PMC prefix
        formatted_pmcids = []
        for pmcid in pmcids:
            if not pmcid.startswith('PMC'):
                formatted_pmcids.append(f'PMC{pmcid}')
            else:
                formatted_pmcids.append(pmcid)
        
        # NCBI ID Converter API endpoint
        base_url = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
        
        # Build query parameters
        params = {
            'ids': ','.join(formatted_pmcids[:200]),  # API limit: 200 IDs per request
            'format': 'json',
            'idtype': 'pmcid'
        }
        
        try:
            # Rate limiting
            await asyncio.sleep(0.34)
            
            logger.info(f"Converting {len(formatted_pmcids)} PMCIDs to PMIDs")
            
            async with self.session.get(base_url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    # Parse the response
                    pmcid_to_pmid = {}
                    
                    if 'records' in data:
                        for record in data['records']:
                            pmcid = record.get('pmcid', '')
                            pmid = record.get('pmid', '')
                            
                            if pmcid and pmid:
                                pmcid_to_pmid[pmcid] = pmid
                                logger.debug(f"Converted {pmcid} → PMID {pmid}")
                    
                    logger.info(f"Successfully converted {len(pmcid_to_pmid)}/{len(formatted_pmcids)} PMCIDs to PMIDs")
                    return pmcid_to_pmid
                    
                else:
                    error_text = await resp.text()
                    logger.error(f"PMCID conversion failed: HTTP {resp.status} - {error_text}")
                    return {}
                    
        except asyncio.TimeoutError:
            logger.error("PMCID conversion timeout")
            return {}
        except Exception as e:
            logger.error(f"PMCID conversion error: {e}")
            return {}
    
    async def fetch_pmc_bioc(
        self,
        pmid: str,
        format: str = "biocjson"
    ) -> Dict[str, Any]:
        """
        Fetch article from PubTator3 API in BioC format.
        
        Args:
            pmid: PubMed ID or PMC ID
            format: 'biocjson' or 'biocxml' (default: biocjson)
        
        Returns:
            Dict containing BioC formatted article data or error
        """
        # PubTator3 API endpoint
        base_url = "https://www.ncbi.nlm.nih.gov/research/pubtator3-api/publications/export"
        
        # Validate format
        if format not in ["biocjson", "biocxml"]:
            format = "biocjson"
        
        try:
            # Rate limiting - NCBI recommends 3 requests/second
            await asyncio.sleep(0.34)
            
            # PubTator3 URL structure: /export/{format}?pmids={pmid}
            url = f"{base_url}/{format}?pmids={pmid}"
            
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    if format == "biocjson":
                        data = await resp.json()
                        logger.info(f"PubTator3 BioC fetch successful for {pmid}")
                        return data
                    else:  # biocxml
                        xml_content = await resp.text()
                        logger.info(f"PubTator3 BioC XML fetch successful for {pmid}")
                        return {"xml": xml_content}
                elif resp.status == 404:
                    logger.warning(f"Article {pmid} not found in PubTator3")
                    return {"error": "Article not available in PubTator3"}
                else:
                    error_text = await resp.text()
                    logger.error(f"PubTator3 fetch error: HTTP {resp.status} - {error_text[:200]}")
                    return {"error": f"HTTP {resp.status}: {error_text[:200]}"}
                    
        except asyncio.TimeoutError:
            logger.error(f"PubTator3 fetch timeout for {pmid}")
            return {"error": "Request timeout"}
        except Exception as e:
            logger.error(f"PubTator3 fetch error for {pmid}: {e}")
            return {"error": str(e)}


    async def fetch_multiple_pmc_bioc(
        self,
        pmids: List[str],
        format: str = "biocjson",
        encoding: str = "unicode"
    ) -> Dict[str, Dict[str, Any]]:
        """
        Fetch multiple articles from PMC Open Access in BioC format.
        
        Args:
            pmids: List of PubMed IDs or PMC IDs
            format: 'biocjson' or 'biocxml'
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
    """DuckDuckGo search client with enhanced error handling."""
    
    async def search(
        self,
        nct_id: str,
        title: str,
        condition: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search DuckDuckGo."""
        try:
            # Check if library is available
            try:
                from duckduckgo_search import DDGS
            except ImportError:
                logger.error("duckduckgo-search library not installed")
                return {
                    "error": "duckduckgo-search library not installed. Install with: pip install duckduckgo-search",
                    "query": nct_id,
                    "results": [],
                    "total_found": 0
                }
            
            # Build query
            query_parts = [nct_id]
            if title:
                query_parts.append(" ".join(title.split()[:10]))
            if condition:
                query_parts.append(condition)
            
            query = " ".join(query_parts)
            
            logger.info(f"DuckDuckGo searching for: {query}")
            
            # Run search in executor (blocking operation)
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                self._search_sync,
                query
            )
            
            if not results:
                logger.warning(f"DuckDuckGo returned no results for: {query}")
            else:
                logger.info(f"DuckDuckGo found {len(results)} results for: {query}")
            
            return {
                "query": query,
                "results": results,
                "total_found": len(results)
            }
            
        except ImportError as e:
            logger.error(f"DuckDuckGo import error: {e}")
            return {
                "error": f"Required library not available: {str(e)}",
                "query": nct_id,
                "results": [],
                "total_found": 0
            }
        except Exception as e:
            logger.error(f"DuckDuckGo search error: {e}", exc_info=True)
            return {
                "error": f"DuckDuckGo search failed: {str(e)}",
                "query": nct_id,
                "results": [],
                "total_found": 0
            }
    
    def _search_sync(self, query: str) -> List[Dict]:
        """Synchronous search helper with timeout and error handling."""
        try:
            from duckduckgo_search import DDGS
            
            results = []
            
            # Use context manager with timeout
            with DDGS(timeout=20) as ddgs:
                try:
                    search_results = ddgs.text(query, max_results=10)
                    
                    for result in search_results:
                        results.append({
                            'title': result.get('title', ''),
                            'url': result.get('href', ''),
                            'snippet': result.get('body', '')
                        })
                    
                    logger.info(f"DuckDuckGo sync search completed: {len(results)} results")
                    
                except Exception as search_error:
                    logger.error(f"DuckDuckGo search execution error: {search_error}")
                    raise
            
            return results
            
        except Exception as e:
            logger.error(f"DuckDuckGo _search_sync error: {e}")
            return []
    
    async def fetch(self, identifier: str) -> Dict[str, Any]:
        """Not implemented for DuckDuckGo."""
        return {"error": "Fetch not supported for DuckDuckGo"}
    
class SerpAPIClient(BaseClient):
    """SERP API (Google Search) client with proper error handling."""
    
    BASE_URL = "https://serpapi.com/search"
    
    async def search(
        self,
        nct_id: str,
        title: str,
        condition: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search via SERP API."""
        if not self.api_key:
            return {
                "error": "SERPAPI_KEY not configured",
                "query": nct_id,
                "results": [],
                "total_found": 0
            }
        
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
            async with self.session.get(self.BASE_URL, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    # Check for API-level errors
                    if 'error' in data:
                        logger.error(f"SERP API error: {data['error']}")
                        return {
                            "error": f"SERP API error: {data['error']}",
                            "query": query,
                            "results": [],
                            "total_found": 0
                        }
                    
                    results = [
                        {
                            'title': r.get('title', ''),
                            'url': r.get('link', ''),
                            'snippet': r.get('snippet', '')
                        }
                        for r in data.get('organic_results', [])
                    ]
                    
                    logger.info(f"SERP API found {len(results)} results for '{query}'")
                    
                    return {
                        "query": query,
                        "results": results,
                        "total_found": len(results)
                    }
                else:
                    error_text = await resp.text()
                    logger.error(f"SERP API HTTP {resp.status}: {error_text[:200]}")
                    return {
                        "error": f"SERP API request failed (HTTP {resp.status})",
                        "query": query,
                        "results": [],
                        "total_found": 0
                    }
        except asyncio.TimeoutError:
            logger.error(f"SERP API timeout for query: {query}")
            return {
                "error": "SERP API request timeout",
                "query": query,
                "results": [],
                "total_found": 0
            }
        except Exception as e:
            logger.error(f"SERP API error: {e}")
            return {
                "error": f"SERP API request failed: {str(e)}",
                "query": query,
                "results": [],
                "total_found": 0
            }
    
    async def fetch(self, identifier: str) -> Dict[str, Any]:
        """Not implemented."""
        return {"error": "Fetch not supported"}


class GoogleScholarClient(BaseClient):
    """Google Scholar via SERP API with proper error handling."""
    
    BASE_URL = "https://serpapi.com/search"
    
    async def search(
        self,
        nct_id: str,
        title: str,
        condition: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search Google Scholar."""
        if not self.api_key:
            return {
                "error": "SERPAPI_KEY not configured",
                "query": nct_id,
                "results": [],
                "total_found": 0
            }
        
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
            async with self.session.get(self.BASE_URL, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    # Check for API-level errors
                    if 'error' in data:
                        logger.error(f"Google Scholar API error: {data['error']}")
                        return {
                            "error": f"Google Scholar API error: {data['error']}",
                            "query": query,
                            "results": [],
                            "total_found": 0
                        }
                    
                    results = [
                        {
                            'title': r.get('title', ''),
                            'url': r.get('link', ''),
                            'snippet': r.get('snippet', ''),
                            'cited_by': r.get('inline_links', {}).get('cited_by', {}).get('total')
                        }
                        for r in data.get('organic_results', [])
                    ]
                    
                    logger.info(f"Google Scholar found {len(results)} results for '{query}'")
                    
                    return {
                        "query": query,
                        "results": results,
                        "total_found": len(results)
                    }
                else:
                    error_text = await resp.text()
                    logger.error(f"Google Scholar HTTP {resp.status}: {error_text[:200]}")
                    return {
                        "error": f"Google Scholar request failed (HTTP {resp.status})",
                        "query": query,
                        "results": [],
                        "total_found": 0
                    }
        except asyncio.TimeoutError:
            logger.error(f"Google Scholar timeout for query: {query}")
            return {
                "error": "Google Scholar request timeout",
                "query": query,
                "results": [],
                "total_found": 0
            }
        except Exception as e:
            logger.error(f"Google Scholar error: {e}")
            return {
                "error": f"Google Scholar request failed: {str(e)}",
                "query": query,
                "results": [],
                "total_found": 0
            }
    
    async def fetch(self, identifier: str) -> Dict[str, Any]:
        """Not implemented."""
        return {"error": "Fetch not supported"}


class OpenFDAClient(BaseClient):
    """
    OpenFDA API client with comprehensive search capabilities.
    
    Searches across multiple FDA databases:
    - Drug labels
    - Adverse events
    - Drug enforcement reports
    """
    
    BASE_URL = "https://api.fda.gov/drug"
    
    COMMON_TERMS_BLACKLIST = {
        # Generic/broad terms
        "human", "humans", "patient", "patients", "subject", "subjects",
        "people", "person", "individual", "individuals",
        
        # Technology terms
        "artificial intelligence", "ai", "machine learning", "ml",
        "computer", "software", "algorithm", "technology",
        
        # Generic medical terms
        "treatment", "therapy", "drug", "medication", "medicine",
        "disease", "condition", "diagnosis", "symptom",
        
        # Study terms
        "study", "trial", "research", "investigation", "analysis",
        "clinical", "medical", "health", "healthcare",
        
        # Very common conditions
        "pain", "fever", "infection", "inflammation",
        
        # Single letters/numbers
        "a", "b", "c", "d", "e", "i", "ii", "iii", "iv", "v",
        "1", "2", "3", "4", "5", "6", "7", "8", "9", "10"
    }

    def _filter_common_terms(self, identifiers: List[str]) -> List[str]:
        """Filter out very common terms that won't yield useful FDA results."""
        filtered = []
        for term in identifiers:
            term_lower = term.lower().strip()
            # Skip if it's a common term
            if term_lower in self.COMMON_TERMS_BLACKLIST:
                logger.info(f"Skipping common term: {term}")
                continue
            # Skip if it's too short (less than 4 characters)
            if len(term_lower) < 4:
                continue
            filtered.append(term)
        return filtered

    async def search_enhanced(self, nct_id: str, trial_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enhanced OpenFDA search with common term filtering.
        """
        search_terms = self._extract_drug_identifiers(trial_data)
        
        # Filter out common terms
        search_terms = self._filter_common_terms(search_terms)
        
        if not search_terms:
            logger.info(f"OpenFDA: All terms were common/generic for {nct_id}")
            return {
                "query": "No specific drug identifiers found (only common terms)",
                "drug_labels": [],
                "adverse_events": [],
                "enforcement_reports": [],
                "total_found": 0,
                "search_terms_used": [],
                "filtered_out": "Common terms filtered"
            }
        
        logger.info(f"OpenFDA: Searching with filtered terms: {search_terms}")
        
        # Continue with normal search logic...
        results = {
            "query": ", ".join(search_terms[:3]),
            "drug_labels": [],
            "adverse_events": [],
            "enforcement_reports": [],
            "total_found": 0,
            "search_terms_used": search_terms
        }
        
        for term in search_terms[:10]:
            labels = await self._search_drug_labels(term)
            results["drug_labels"].extend(labels)
            
            events = await self._search_adverse_events(term)
            results["adverse_events"].extend(events)
            
            enforcement = await self._search_enforcement(term)
            results["enforcement_reports"].extend(enforcement)
        
        results["drug_labels"] = self._deduplicate_results(results["drug_labels"])
        results["adverse_events"] = self._deduplicate_results(results["adverse_events"])
        results["enforcement_reports"] = self._deduplicate_results(results["enforcement_reports"])
        
        results["total_found"] = (
            len(results["drug_labels"]) +
            len(results["adverse_events"]) +
            len(results["enforcement_reports"])
        )
        
        logger.info(f"OpenFDA: Found {results['total_found']} total results for {nct_id}")
        
        return results
    
    def _extract_drug_identifiers(self, trial_data: Dict[str, Any]) -> List[str]:
            """Extract drug identifiers with common term filtering."""
            identifiers = []
            
            try:
                protocol = trial_data.get("protocolSection", {})
                
                # Get interventions
                arms_interventions = protocol.get("armsInterventionsModule", {})
                interventions = arms_interventions.get("interventions", [])
                
                for intervention in interventions:
                    if isinstance(intervention, dict):
                        # Intervention name
                        name = intervention.get("name", "").strip()
                        if name and self._is_valid_search_term(name):
                            identifiers.append(name)
                        
                        # Other names/synonyms
                        other_names = intervention.get("otherNames", [])
                        if isinstance(other_names, list):
                            for alt_name in other_names:
                                alt_name = alt_name.strip()
                                if alt_name and self._is_valid_search_term(alt_name):
                                    identifiers.append(alt_name)
                
                # Get from conditions (some drugs are condition-specific)
                conditions_module = protocol.get("conditionsModule", {})
                conditions = conditions_module.get("conditions", [])
                if isinstance(conditions, list):
                    for condition in conditions:
                        condition = condition.strip()
                        if condition and self._is_valid_search_term(condition):
                            identifiers.append(condition)
            
            except Exception as e:
                logger.warning(f"Error extracting drug identifiers: {e}")
            
            # Clean and deduplicate
            cleaned = []
            seen = set()
            for identifier in identifiers:
                clean = identifier.lower().strip()
                if clean and clean not in seen and len(clean) > 2:
                    seen.add(clean)
                    cleaned.append(identifier)
            
            filtered_count = len(identifiers) - len(cleaned)
            if filtered_count > 0:
                logger.info(f"OpenFDA: Filtered out {filtered_count} common/invalid terms")
            
            return cleaned[:10]  # Limit to 10 most relevant terms
    
    async def _search_drug_labels(self, drug_name: str) -> List[Dict]:
        """Search FDA drug labels."""
        url = f"{self.BASE_URL}/label.json"
        params = {
            "search": f'openfda.generic_name:"{drug_name}" OR openfda.brand_name:"{drug_name}"',
            "limit": 3
        }
        
        try:
            async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = data.get("results", [])
                    return [self._format_label_result(r) for r in results]
                elif resp.status == 404:
                    return []  # No results, not an error
                else:
                    logger.debug(f"OpenFDA labels returned {resp.status} for '{drug_name}'")
                    return []
        except Exception as e:
            logger.debug(f"OpenFDA labels search error for '{drug_name}': {e}")
            return []
    
    async def _search_adverse_events(self, drug_name: str) -> List[Dict]:
        """Search FDA adverse events."""
        url = f"{self.BASE_URL}/event.json"
        params = {
            "search": f'patient.drug.openfda.generic_name:"{drug_name}" OR patient.drug.openfda.brand_name:"{drug_name}"',
            "limit": 3
        }
        
        try:
            async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = data.get("results", [])
                    return [self._format_event_result(r) for r in results]
                elif resp.status == 404:
                    return []
                else:
                    logger.debug(f"OpenFDA events returned {resp.status} for '{drug_name}'")
                    return []
        except Exception as e:
            logger.debug(f"OpenFDA events search error for '{drug_name}': {e}")
            return []
    
    async def _search_enforcement(self, drug_name: str) -> List[Dict]:
        """Search FDA enforcement reports."""
        url = f"{self.BASE_URL}/enforcement.json"
        params = {
            "search": f'openfda.generic_name:"{drug_name}" OR openfda.brand_name:"{drug_name}"',
            "limit": 3
        }
        
        try:
            async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = data.get("results", [])
                    return [self._format_enforcement_result(r) for r in results]
                elif resp.status == 404:
                    return []
                else:
                    logger.debug(f"OpenFDA enforcement returned {resp.status} for '{drug_name}'")
                    return []
        except Exception as e:
            logger.debug(f"OpenFDA enforcement search error for '{drug_name}': {e}")
            return []
    
    def _format_label_result(self, result: Dict) -> Dict:
        """Format drug label result."""
        return {
            "type": "drug_label",
            "product": result.get("openfda", {}).get("brand_name", [""])[0] if result.get("openfda", {}).get("brand_name") else "Unknown",
            "manufacturer": result.get("openfda", {}).get("manufacturer_name", [""])[0] if result.get("openfda", {}).get("manufacturer_name") else "Unknown",
            "purpose": result.get("purpose", [""])[0] if result.get("purpose") else None,
            "warnings": result.get("warnings", [""])[0][:200] if result.get("warnings") else None
        }
    
    def _format_event_result(self, result: Dict) -> Dict:
        """Format adverse event result."""
        return {
            "type": "adverse_event",
            "date": result.get("receivedate", "Unknown"),
            "serious": result.get("serious", 0),
            "reactions": [r.get("reactionmeddrapt", "Unknown") for r in result.get("patient", {}).get("reaction", [])[:3]]
        }
    
    def _format_enforcement_result(self, result: Dict) -> Dict:
        """Format enforcement report result."""
        return {
            "type": "enforcement",
            "classification": result.get("classification", "Unknown"),
            "status": result.get("status", "Unknown"),
            "recall_date": result.get("recall_initiation_date", "Unknown"),
            "reason": result.get("reason_for_recall", "")[:200]
        }
    
    def _deduplicate_results(self, results: List[Dict]) -> List[Dict]:
        """Remove duplicate results."""
        seen = set()
        unique = []
        
        for result in results:
            # Create a simple hash of the result
            result_hash = json.dumps(result, sort_keys=True)
            if result_hash not in seen:
                seen.add(result_hash)
                unique.append(result)
        
        return unique
    
    async def fetch(self, identifier: str) -> Dict[str, Any]:
        """Not implemented - use search() instead."""
        return {"error": "Use search() method with trial data"}
    
class UniProtClient(BaseClient):
    """
    UniProt API client for protein sequence and functional information.
    
    Searches UniProt database using drug/intervention names from clinical trials.
    """
    
    BASE_URL = "https://rest.uniprot.org/uniprotkb/search"
    
    async def search(
        self,
        nct_id: str,
        trial_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Search UniProt using intervention data from clinical trial.
        
        Args:
            nct_id: NCT trial identifier
            trial_data: Full clinical trial data dictionary
            
        Returns:
            Dict with UniProt search results
        """
        # Extract intervention names
        interventions = self._extract_interventions(trial_data)
        
        if not interventions:
            logger.info(f"UniProt: No interventions found for {nct_id}")
            return {
                "query": "No interventions found",
                "results": [],
                "total_found": 0,
                "interventions_searched": []
            }
        
        logger.info(f"UniProt: Searching with interventions: {interventions}")
        
        # Initialize results
        results = {
            "interventions_searched": interventions,
            "results": [],
            "total_found": 0,
            "query": ", ".join(interventions[:3])  # Show first 3
        }
        
        # Search each intervention
        for intervention in interventions[:5]:  # Limit to first 5
            intervention_results = await self._search_intervention(intervention)
            
            if intervention_results:
                results["results"].extend(intervention_results)
        
        # Deduplicate by UniProt ID
        results["results"] = self._deduplicate_results(results["results"])
        results["total_found"] = len(results["results"])
        
        logger.info(f"UniProt: Found {results['total_found']} results for {nct_id}")
        
        return results
    
    async def _search_intervention(self, intervention: str) -> List[Dict[str, Any]]:
        """
        Search UniProt for a specific intervention/drug name.
        
        Args:
            intervention: Drug or intervention name
            
        Returns:
            List of UniProt entries
        """
        # Build query - search in protein names and gene names
        # This searches for proteins that might be drug targets
        query = f'({intervention}) AND (reviewed:true)'
        
        params = {
            'query': query,
            'format': 'json',
            'size': 10  # Limit results per intervention
        }
        
        try:
            await asyncio.sleep(0.1)  # Rate limiting - UniProt is generous
            
            async with self.session.get(
                self.BASE_URL,
                params=params,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = data.get("results", [])
                    
                    # Format results
                    formatted_results = [
                        self._format_uniprot_entry(entry, intervention)
                        for entry in results
                    ]
                    
                    logger.info(f"UniProt: Found {len(formatted_results)} results for '{intervention}'")
                    return formatted_results
                    
                elif resp.status == 400:
                    logger.warning(f"UniProt: Invalid query for '{intervention}'")
                    return []
                    
                else:
                    error_text = await resp.text()
                    logger.error(f"UniProt HTTP {resp.status}: {error_text[:200]}")
                    return []
                    
        except asyncio.TimeoutError:
            logger.error(f"UniProt: Timeout for query '{intervention}'")
            return []
        except Exception as e:
            logger.error(f"UniProt error for '{intervention}': {e}")
            return []
    
    def _extract_interventions(self, trial_data: Dict[str, Any]) -> List[str]:
        """
        Extract intervention names from clinical trial data.
        
        Args:
            trial_data: Full clinical trial data
            
        Returns:
            List of intervention/drug names
        """
        interventions = []
        
        try:
            protocol = trial_data.get("protocolSection", {})
            arms_interventions = protocol.get("armsInterventionsModule", {})
            intervention_list = arms_interventions.get("interventions", [])
            
            for intervention in intervention_list:
                if isinstance(intervention, dict):
                    # Get intervention name
                    name = intervention.get("name", "").strip()
                    if name:
                        interventions.append(name)
                    
                    # Get other names/synonyms
                    other_names = intervention.get("otherNames", [])
                    if isinstance(other_names, list):
                        interventions.extend([n.strip() for n in other_names if n.strip()])
            
        except Exception as e:
            logger.warning(f"Error extracting interventions: {e}")
        
        # Clean and deduplicate
        cleaned = []
        seen = set()
        for intervention in interventions:
            clean = intervention.lower().strip()
            if clean and clean not in seen and len(clean) > 2:
                seen.add(clean)
                cleaned.append(intervention)
        
        return cleaned[:10]  # Limit to 10 most relevant
    
    def _is_valid_search_term(self, term: str) -> bool:
        """
        Check if a term is valid for OpenFDA search.
        Returns False for common/generic terms.
        """
        if not term:
            return False
        
        term_lower = term.lower().strip()
        
        # Check blacklist
        if term_lower in self.COMMON_TERMS_BLACKLIST:
            logger.debug(f"OpenFDA: Skipping blacklisted term '{term}'")
            return False
        
        # Check for very short terms (< 3 chars)
        if len(term_lower) < 3:
            logger.debug(f"OpenFDA: Skipping short term '{term}'")
            return False
        
        # Check for terms that are too generic (all common words)
        common_words = ["the", "and", "or", "for", "with", "without", "in", "on", "at"]
        words = term_lower.split()
        if all(word in common_words for word in words):
            logger.debug(f"OpenFDA: Skipping generic term '{term}'")
            return False
        
        return True
    
    async def search(self, query: str, **kwargs) -> Dict[str, Any]:
        """
        Comprehensive OpenFDA search using trial data.
        
        Args:
            query: NCT trial identifier (nct_id)
            **kwargs: Additional parameters including 'trial_data' with full trial info
            
        Returns:
            Dict with combined results from multiple FDA endpoints
        """
        nct_id = query
        trial_data = kwargs.get('trial_data', {})
        
        # Extract all possible drug identifiers from trial data
        search_terms = self._extract_drug_identifiers(trial_data)
        
        if not search_terms:
            logger.info(f"OpenFDA: No valid drug/intervention identifiers found for {nct_id}")
            return {
                "query": "No valid identifiers found (common terms filtered)",
                "drug_labels": [],
                "adverse_events": [],
                "enforcement_reports": [],
                "total_found": 0,
                "search_terms_used": [],
                "terms_filtered": "Common terms like 'human', 'AI', etc. were excluded"
            }
        
        logger.info(f"OpenFDA: Searching with {len(search_terms)} valid terms: {search_terms}")

    def _format_uniprot_entry(self, entry: Dict[str, Any], intervention: str) -> Dict[str, Any]:
        """
        Format a UniProt entry for storage.
        
        Args:
            entry: Raw UniProt entry
            intervention: The intervention that matched this entry
            
        Returns:
            Formatted entry dict
        """
        # Extract primary accession
        primary_accession = entry.get("primaryAccession", "")
        
        # Extract protein names
        protein_description = entry.get("proteinDescription", {})
        recommended_name = protein_description.get("recommendedName", {})
        full_name = recommended_name.get("fullName", {}).get("value", "")
        
        # Get alternative names
        alternative_names = []
        alt_names_list = protein_description.get("alternativeNames", [])
        for alt in alt_names_list[:3]:  # Limit to 3
            if isinstance(alt, dict):
                alt_full = alt.get("fullName", {}).get("value", "")
                if alt_full:
                    alternative_names.append(alt_full)
        
        # Extract gene names
        gene_names = []
        genes = entry.get("genes", [])
        for gene in genes[:3]:  # Limit to 3
            if isinstance(gene, dict):
                gene_name = gene.get("geneName", {}).get("value", "")
                if gene_name:
                    gene_names.append(gene_name)
        
        # Extract organism
        organism = entry.get("organism", {})
        organism_name = organism.get("scientificName", "")
        
        # Extract function (first comment of type FUNCTION)
        function = ""
        comments = entry.get("comments", [])
        for comment in comments:
            if isinstance(comment, dict) and comment.get("commentType") == "FUNCTION":
                texts = comment.get("texts", [])
                if texts and isinstance(texts, list):
                    function = texts[0].get("value", "")[:500]  # Limit length
                    break
        
        return {
            "type": "uniprot_entry",
            "intervention_matched": intervention,
            "accession": primary_accession,
            "protein_name": full_name,
            "alternative_names": alternative_names,
            "gene_names": gene_names,
            "organism": organism_name,
            "function": function if function else None,
            "url": f"https://www.uniprot.org/uniprotkb/{primary_accession}"
        }
    
    def _deduplicate_results(self, results: List[Dict]) -> List[Dict]:
        """Remove duplicate UniProt entries by accession."""
        seen = set()
        unique = []
        
        for result in results:
            accession = result.get("accession", "")
            if accession and accession not in seen:
                seen.add(accession)
                unique.append(result)
        
        return unique
    
    async def fetch(self, identifier: str) -> Dict[str, Any]:
        """
        Fetch a specific UniProt entry by accession.
        
        Args:
            identifier: UniProt accession (e.g., P12345)
            
        Returns:
            UniProt entry data
        """
        url = f"https://rest.uniprot.org/uniprotkb/{identifier}.json"
        
        try:
            await asyncio.sleep(0.1)  # Rate limiting
            
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    logger.info(f"UniProt: Fetched entry {identifier}")
                    return data
                elif resp.status == 404:
                    return {"error": f"UniProt entry {identifier} not found"}
                else:
                    error_text = await resp.text()
                    return {"error": f"HTTP {resp.status}: {error_text[:200]}"}
                    
        except Exception as e:
            logger.error(f"UniProt fetch error for {identifier}: {e}")
            return {"error": str(e)}

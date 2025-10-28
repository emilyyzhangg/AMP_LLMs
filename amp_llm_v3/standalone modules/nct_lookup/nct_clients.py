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
    
    async def search(self, query: str, **kwargs) -> List[str]:
        """Search PubMed, return PMIDs."""
        max_results = kwargs.get("max_results", 10)
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
    
    async def search(self, query: str, **kwargs) -> List[str]:
        """Search PMC, return PMC IDs."""
        max_results = kwargs.get("max_results", 10)
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
        return await self.fetch_pmc_bioc(identifier, format="biocjson")
    
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
            result = await self.fetch_pmc_bioc(pmid, format)
            results[pmid] = result
        
        logger.info(f"Fetched {len(results)} articles from PMC BioC")
        return results


class DuckDuckGoClient(BaseClient):
    """DuckDuckGo search client."""
    
    async def search(self, nct_id: str, trial_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Search DuckDuckGo using trial data.
        
        Args:
            nct_id: NCT trial identifier
            trial_data: Full clinical trial data
            
        Returns:
            Dict with search results
        """
        # Extract search parameters from trial data
        title = self._extract_title(trial_data)
        condition = self._extract_condition(trial_data)
        
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
            
            logger.info(f"DuckDuckGo found {len(results)} results for '{query}'")
            
            return {
                "query": query,
                "results": results,
                "total_found": len(results)
            }
            
        except ImportError:
            return {
                "error": "duckduckgo-search library not installed",
                "query": nct_id,
                "results": [],
                "total_found": 0
            }
        except Exception as e:
            logger.error(f"DuckDuckGo error: {e}")
            return {
                "error": f"DuckDuckGo search failed: {str(e)}",
                "query": nct_id,
                "results": [],
                "total_found": 0
            }
    
    def _extract_title(self, trial_data: Dict[str, Any]) -> str:
        """Extract trial title."""
        try:
            protocol = trial_data.get("protocolSection", {})
            ident = protocol.get("identificationModule", {})
            return ident.get("officialTitle") or ident.get("briefTitle") or ""
        except:
            return ""
    
    def _extract_condition(self, trial_data: Dict[str, Any]) -> str:
        """Extract primary condition."""
        try:
            protocol = trial_data.get("protocolSection", {})
            cond_mod = protocol.get("conditionsModule", {})
            conditions = cond_mod.get("conditions", [])
            if conditions and isinstance(conditions, list):
                return conditions[0].strip()
            return ""
        except:
            return ""
    
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
    """SERP API (Google Search) client with proper error handling."""
    
    BASE_URL = "https://serpapi.com/search"
    
    async def search(self, nct_id: str, trial_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Search via SERP API using trial data.
        
        Args:
            nct_id: NCT trial identifier
            trial_data: Full clinical trial data
            
        Returns:
            Dict with search results
        """
        if not self.api_key:
            return {
                "error": "SERPAPI_KEY not configured",
                "query": nct_id,
                "results": [],
                "total_found": 0
            }
        
        # Extract search parameters
        title = self._extract_title(trial_data)
        condition = self._extract_condition(trial_data)
        
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
    
    def _extract_title(self, trial_data: Dict[str, Any]) -> str:
        """Extract trial title."""
        try:
            protocol = trial_data.get("protocolSection", {})
            ident = protocol.get("identificationModule", {})
            return ident.get("officialTitle") or ident.get("briefTitle") or ""
        except:
            return ""
    
    def _extract_condition(self, trial_data: Dict[str, Any]) -> str:
        """Extract primary condition."""
        try:
            protocol = trial_data.get("protocolSection", {})
            cond_mod = protocol.get("conditionsModule", {})
            conditions = cond_mod.get("conditions", [])
            if conditions and isinstance(conditions, list):
                return conditions[0].strip()
            return ""
        except:
            return ""
    
    async def fetch(self, identifier: str) -> Dict[str, Any]:
        """Not implemented."""
        return {"error": "Fetch not supported"}

class GoogleScholarClient(BaseClient):
    """Google Scholar via SERP API with proper error handling."""
    
    BASE_URL = "https://serpapi.com/search"
    
    async def search(self, nct_id: str, trial_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Search Google Scholar using trial data.
        
        Args:
            nct_id: NCT trial identifier
            trial_data: Full clinical trial data
            
        Returns:
            Dict with search results
        """
        if not self.api_key:
            return {
                "error": "SERPAPI_KEY not configured",
                "query": nct_id,
                "results": [],
                "total_found": 0
            }
        
        # Extract search parameters
        title = self._extract_title(trial_data)
        condition = self._extract_condition(trial_data)
        
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
    
    def _extract_title(self, trial_data: Dict[str, Any]) -> str:
        """Extract trial title."""
        try:
            protocol = trial_data.get("protocolSection", {})
            ident = protocol.get("identificationModule", {})
            return ident.get("officialTitle") or ident.get("briefTitle") or ""
        except:
            return ""
    
    def _extract_condition(self, trial_data: Dict[str, Any]) -> str:
        """Extract primary condition."""
        try:
            protocol = trial_data.get("protocolSection", {})
            cond_mod = protocol.get("conditionsModule", {})
            conditions = cond_mod.get("conditions", [])
            if conditions and isinstance(conditions, list):
                return conditions[0].strip()
            return ""
        except:
            return ""
    
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
    
    async def search(self, nct_id: str, trial_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Comprehensive OpenFDA search using trial data.
        
        Args:
            query: NCT trial identifier
            **kwargs: Must include 'trial_data' with full clinical trial data dictionary
            
        Returns:
            Dict with combined results from multiple FDA endpoints
        """
        nct_id = query
        trial_data = kwargs.get('trial_data', {})
        
        if not trial_data:
            return {
                "error": "trial_data required in kwargs",
                "query": nct_id,
                "drug_labels": [],
                "adverse_events": [],
                "enforcement_reports": [],
                "total_found": 0,
                "search_terms_used": []
            }
        
        # Extract all possible drug identifiers from trial data
        search_terms = self._extract_drug_identifiers(trial_data)
        
        if not search_terms:
            logger.info(f"OpenFDA: No drug/intervention identifiers found for {nct_id}")
            return {
                "query": "No drug identifiers found",
                "drug_labels": [],
                "adverse_events": [],
                "enforcement_reports": [],
                "total_found": 0,
                "search_terms_used": []
            }
        
        logger.info(f"OpenFDA: Searching with terms: {search_terms}")
        
        # Search across all FDA databases
        results = {
            "query": ", ".join(search_terms[:3]),  # Show first 3 terms
            "drug_labels": [],
            "adverse_events": [],
            "enforcement_reports": [],
            "total_found": 0,
            "search_terms_used": search_terms
        }
        
        # Search each term across databases
        for term in search_terms[:5]:  # Limit to first 5 terms
            # Drug labels
            labels = await self._search_drug_labels(term)
            results["drug_labels"].extend(labels)
            
            # Adverse events
            events = await self._search_adverse_events(term)
            results["adverse_events"].extend(events)
            
            # Enforcement reports
            enforcement = await self._search_enforcement(term)
            results["enforcement_reports"].extend(enforcement)
        
        # Remove duplicates and count
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
        """Extract all possible drug/intervention identifiers from trial data."""
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
                    if name:
                        identifiers.append(name)
                    
                    # Other names/synonyms
                    other_names = intervention.get("otherNames", [])
                    if isinstance(other_names, list):
                        identifiers.extend([n.strip() for n in other_names if n.strip()])
            
            # Get from conditions (some drugs are condition-specific)
            conditions_module = protocol.get("conditionsModule", {})
            conditions = conditions_module.get("conditions", [])
            if isinstance(conditions, list):
                identifiers.extend([c.strip() for c in conditions if c.strip()])
            
            # Get from trial title (may contain drug names)
            ident_module = protocol.get("identificationModule", {})
            title = ident_module.get("officialTitle", "") or ident_module.get("briefTitle", "")
            if title:
                # Extract potential drug names (words in title that might be drugs)
                # This is a simple heuristic - could be improved
                title_words = title.split()
                for i, word in enumerate(title_words):
                    # Check if word looks like a drug name (capitalized, not common words)
                    if (word[0].isupper() and len(word) > 3 and 
                        word.lower() not in ['trial', 'study', 'phase', 'randomized', 'controlled']):
                        identifiers.append(word.strip('()[]{}:,;.'))
            
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
    """UniProt API client for protein data."""
    
    BASE_URL = "https://rest.uniprot.org"
    
    async def search(self, nct_id: str, trial_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Search UniProt using protein/gene names from trial data.
        
        Args:
            nct_id: NCT trial identifier
            trial_data: Full clinical trial data
            
        Returns:
            Dict with UniProt search results
        """
        # Extract intervention names that might be proteins/genes
        search_terms = self._extract_protein_terms(trial_data)
        
        if not search_terms:
            logger.info(f"UniProt: No protein/gene identifiers found for {nct_id}")
            return {
                "query": "No protein identifiers found",
                "results": [],
                "total_found": 0,
                "search_terms_used": []
            }
        
        logger.info(f"UniProt: Searching with terms: {search_terms}")
        
        results = {
            "query": ", ".join(search_terms[:3]),
            "results": [],
            "total_found": 0,
            "search_terms_used": search_terms
        }
        
        # Search each term
        for term in search_terms[:5]:  # Limit to first 5
            proteins = await self._search_proteins(term)
            results["results"].extend(proteins)
        
        # Deduplicate by accession
        seen = set()
        unique_results = []
        for protein in results["results"]:
            acc = protein.get("accession")
            if acc and acc not in seen:
                seen.add(acc)
                unique_results.append(protein)
        
        results["results"] = unique_results
        results["total_found"] = len(unique_results)
        
        logger.info(f"UniProt: Found {results['total_found']} proteins for {nct_id}")
        
        return results
    
    def _extract_protein_terms(self, trial_data: Dict[str, Any]) -> List[str]:
        """Extract potential protein/gene names from trial data."""
        terms = []
        
        try:
            protocol = trial_data.get("protocolSection", {})
            arms_interventions = protocol.get("armsInterventionsModule", {})
            interventions = arms_interventions.get("interventions", [])
            
            for intervention in interventions:
                if isinstance(intervention, dict):
                    name = intervention.get("name", "").strip()
                    if name:
                        terms.append(name)
                    
                    other_names = intervention.get("otherNames", [])
                    if isinstance(other_names, list):
                        terms.extend([n.strip() for n in other_names if n.strip()])
        
        except Exception as e:
            logger.warning(f"Error extracting protein terms: {e}")
        
        return terms[:10]  # Limit to 10 terms
    
    async def _search_proteins(self, query: str) -> List[Dict]:
        """Search UniProt for proteins matching query."""
        url = f"{self.BASE_URL}/uniprotkb/search"
        
        params = {
            "query": query,
            "format": "json",
            "size": 5  # Limit results per query
        }
        
        try:
            async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = data.get("results", [])
                    
                    return [self._format_protein(p) for p in results]
                else:
                    logger.debug(f"UniProt search returned {resp.status} for '{query}'")
                    return []
        
        except Exception as e:
            logger.debug(f"UniProt search error for '{query}': {e}")
            return []
    
    def _format_protein(self, protein: Dict) -> Dict:
        """Format UniProt protein entry."""
        return {
            "accession": protein.get("primaryAccession"),
            "name": protein.get("uniProtkbId"),
            "protein_name": protein.get("proteinDescription", {}).get("recommendedName", {}).get("fullName", {}).get("value"),
            "organism": protein.get("organism", {}).get("scientificName"),
            "gene": protein.get("genes", [{}])[0].get("geneName", {}).get("value") if protein.get("genes") else None
        }
    
    async def fetch(self, identifier: str) -> Dict[str, Any]:
        """Fetch specific protein by accession."""
        url = f"{self.BASE_URL}/uniprotkb/{identifier}"
        
        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    return {"error": f"HTTP {resp.status}"}
        except Exception as e:
            return {"error": str(e)}
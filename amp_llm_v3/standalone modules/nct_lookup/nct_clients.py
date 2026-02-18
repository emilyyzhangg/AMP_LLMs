"""
NCT Database Clients
===================

Individual client implementations for each database.
Enhanced with comprehensive error handling and improved search strategies.
Now includes proper rate limiting to prevent hitting API limits.
"""

import asyncio
import aiohttp
import json
from typing import Dict, List, Any, Optional
from abc import ABC, abstractmethod
import xml.etree.ElementTree as ET
import logging

from rate_limiter import rate_limited, RateLimitExceeded

logger = logging.getLogger(__name__)


class BaseClient(ABC):
    """Base class for all database clients."""

    # Override this in subclasses for per-client rate limiting
    API_NAME = "default"

    def __init__(self, session: aiohttp.ClientSession, api_key: Optional[str] = None):
        self.session = session
        self.api_key = api_key
        self.rate_limit_delay = 0.34  # Legacy - kept for compatibility

    @abstractmethod
    async def fetch(self, identifier: str) -> Dict[str, Any]:
        """Fetch data by identifier."""
        pass

    @abstractmethod
    async def search(self, query: str, **kwargs) -> Any:
        """Search database."""
        pass

    async def _rate_limit(self):
        """Legacy rate limiting - now uses the rate_limited context manager."""
        # This is kept for backwards compatibility with existing code
        # New code should use: async with rate_limited(self.API_NAME):
        await asyncio.sleep(self.rate_limit_delay)

    def rate_limited_call(self, timeout: float = 30.0):
        """
        Get a rate-limited context manager for this client.

        Usage:
            async with self.rate_limited_call():
                response = await self.session.get(url)
        """
        return rate_limited(self.API_NAME, timeout)


class ClinicalTrialsClient(BaseClient):
    """ClinicalTrials.gov API client."""

    API_NAME = "clinicaltrials"
    BASE_URL = "https://clinicaltrials.gov/api/v2/studies"

    async def fetch(self, nct_id: str) -> Dict[str, Any]:
        """Fetch trial data by NCT ID."""
        url = f"{self.BASE_URL}/{nct_id}"

        try:
            async with self.rate_limited_call():
                async with self.session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        logger.info(f"Fetched {nct_id} from ClinicalTrials.gov")
                        return data
                    else:
                        return {"error": f"HTTP {resp.status}"}
        except RateLimitExceeded as e:
            logger.warning(f"Rate limit exceeded for ClinicalTrials: {e}")
            return {"error": "Rate limit exceeded, please try again later"}
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
            async with self.rate_limited_call():
                async with self.session.get(self.BASE_URL, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data
                    else:
                        return {"error": f"HTTP {resp.status}"}
        except RateLimitExceeded as e:
            logger.warning(f"Rate limit exceeded for ClinicalTrials search: {e}")
            return {"error": "Rate limit exceeded"}
        except Exception as e:
            return {"error": str(e)}


class PubMedClient(BaseClient):
    """PubMed API client."""

    API_NAME = "pubmed"
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
            async with self.rate_limited_call():
                async with self.session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        pmids = data.get("esearchresult", {}).get("idlist", [])
                        logger.info(f"PubMed search found {len(pmids)} results")
                        return pmids
                    return []
        except RateLimitExceeded as e:
            logger.warning(f"Rate limit exceeded for PubMed search: {e}")
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
            async with self.rate_limited_call():
                async with self.session.get(url, params=params) as resp:
                    if resp.status == 200:
                        xml_content = await resp.text()
                        return self._parse_xml(xml_content, pmid)
                    return {"error": f"HTTP {resp.status}"}
        except RateLimitExceeded as e:
            logger.warning(f"Rate limit exceeded for PubMed fetch: {e}")
            return {"error": "Rate limit exceeded"}
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
            Dict containing BioC formatted article data or detailed error
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
                    return {
                        "error": "Not available in PubTator3",
                        "error_type": "not_found",
                        "pmid": pmid,
                        "note": "Article may not be open access or not yet processed by PubTator3"
                    }
                else:
                    error_text = await resp.text()
                    logger.error(f"PubTator3 fetch error: HTTP {resp.status} - {error_text[:200]}")
                    return {
                        "error": f"HTTP {resp.status}",
                        "error_type": "http_error",
                        "pmid": pmid,
                        "details": error_text[:200]
                    }
                    
        except asyncio.TimeoutError:
            logger.error(f"PubTator3 fetch timeout for {pmid}")
            return {
                "error": "Request timeout",
                "error_type": "timeout",
                "pmid": pmid
            }
        except Exception as e:
            logger.error(f"PubTator3 fetch error for {pmid}: {e}")
            return {
                "error": str(e),
                "error_type": "exception",
                "pmid": pmid
            }
        
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


class EuropePMCClient(BaseClient):
    """
    Europe PMC API client - Free biomedical literature database.
    Provides access to worldwide biomedical and life sciences literature.
    """

    BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest"

    async def search(self, nct_id: str, trial_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Search Europe PMC using NCT ID and trial data.

        Args:
            nct_id: NCT trial identifier
            trial_data: Full clinical trial data

        Returns:
            Dict with search results
        """
        title = self._extract_title(trial_data)

        results = {
            "query": nct_id,
            "results": [],
            "total_found": 0,
            "search_strategies": []
        }

        # Strategy 1: Search by NCT ID (most specific)
        nct_results = await self._search_query(f'"{nct_id}"', max_results=10)
        if nct_results:
            results["results"].extend(nct_results)
            results["search_strategies"].append({"type": "nct_id", "count": len(nct_results)})

        # Strategy 2: Search by title keywords if NCT search yields few results
        if len(results["results"]) < 5 and title:
            # Use first 6 significant words from title
            title_words = [w for w in title.split() if len(w) > 3][:6]
            title_query = " AND ".join(title_words)

            title_results = await self._search_query(title_query, max_results=10)
            # Filter to avoid duplicates
            existing_ids = {r.get("pmid") or r.get("pmcid") for r in results["results"]}
            for r in title_results:
                if (r.get("pmid") or r.get("pmcid")) not in existing_ids:
                    results["results"].append(r)

            results["search_strategies"].append({"type": "title", "count": len(title_results)})

        results["total_found"] = len(results["results"])
        logger.info(f"Europe PMC found {results['total_found']} results for {nct_id}")

        return results

    async def _search_query(self, query: str, max_results: int = 10) -> List[Dict]:
        """Execute a Europe PMC search query."""
        url = f"{self.BASE_URL}/search"
        params = {
            "query": query,
            "format": "json",
            "pageSize": max_results,
            "resultType": "core"  # Get full metadata
        }

        try:
            async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    result_list = data.get("resultList", {}).get("result", [])

                    return [self._format_result(r) for r in result_list]
                else:
                    logger.debug(f"Europe PMC search returned {resp.status}")
                    return []
        except Exception as e:
            logger.debug(f"Europe PMC search error: {e}")
            return []

    def _format_result(self, result: Dict) -> Dict:
        """Format Europe PMC search result."""
        return {
            "pmid": result.get("pmid"),
            "pmcid": result.get("pmcid"),
            "doi": result.get("doi"),
            "title": result.get("title"),
            "authors": result.get("authorString"),
            "journal": result.get("journalTitle"),
            "year": result.get("pubYear"),
            "abstract": result.get("abstractText", "")[:500] if result.get("abstractText") else None,
            "citation_count": result.get("citedByCount"),
            "is_open_access": result.get("isOpenAccess") == "Y",
            "source": "europe_pmc"
        }

    def _extract_title(self, trial_data: Dict[str, Any]) -> str:
        """Extract trial title."""
        try:
            protocol = trial_data.get("protocolSection", {})
            ident = protocol.get("identificationModule", {})
            return ident.get("officialTitle") or ident.get("briefTitle") or ""
        except:
            return ""

    async def fetch(self, identifier: str) -> Dict[str, Any]:
        """Fetch article by PMID or PMCID."""
        url = f"{self.BASE_URL}/search"

        # Determine ID type
        if identifier.startswith("PMC"):
            query = f"PMCID:{identifier}"
        else:
            query = f"EXT_ID:{identifier}"

        params = {"query": query, "format": "json", "resultType": "core"}

        try:
            async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = data.get("resultList", {}).get("result", [])
                    if results:
                        return self._format_result(results[0])
                return {"error": "Not found"}
        except Exception as e:
            return {"error": str(e)}


class SemanticScholarClient(BaseClient):
    """
    Semantic Scholar API client - Free academic paper search.
    100 requests per 5 minutes without API key.
    """

    BASE_URL = "https://api.semanticscholar.org/graph/v1"

    def __init__(self, session: aiohttp.ClientSession, api_key: Optional[str] = None):
        super().__init__(session, api_key)
        self.rate_limit_delay = 0.5  # Be conservative with rate limiting

    async def search(self, nct_id: str, trial_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Search Semantic Scholar for papers related to the clinical trial.

        Args:
            nct_id: NCT trial identifier
            trial_data: Full clinical trial data

        Returns:
            Dict with search results including citation data
        """
        title = self._extract_title(trial_data)
        condition = self._extract_condition(trial_data)
        intervention = self._extract_intervention(trial_data)

        results = {
            "query": nct_id,
            "results": [],
            "total_found": 0,
            "search_strategies": []
        }

        # Strategy 1: Search by NCT ID
        nct_results = await self._search_papers(nct_id, limit=10)
        if nct_results:
            results["results"].extend(nct_results)
            results["search_strategies"].append({"type": "nct_id", "count": len(nct_results)})

        # Strategy 2: Search by condition + intervention if we have them
        if len(results["results"]) < 5 and condition and intervention:
            combo_query = f"{condition} {intervention}"
            combo_results = await self._search_papers(combo_query, limit=10)

            existing_ids = {r.get("paperId") for r in results["results"] if r.get("paperId")}
            for r in combo_results:
                if r.get("paperId") not in existing_ids:
                    results["results"].append(r)

            results["search_strategies"].append({"type": "condition_intervention", "count": len(combo_results)})

        # Strategy 3: Search by title keywords
        if len(results["results"]) < 5 and title:
            title_words = [w for w in title.split() if len(w) > 4][:5]
            title_query = " ".join(title_words)
            title_results = await self._search_papers(title_query, limit=10)

            existing_ids = {r.get("paperId") for r in results["results"] if r.get("paperId")}
            for r in title_results:
                if r.get("paperId") not in existing_ids:
                    results["results"].append(r)

            results["search_strategies"].append({"type": "title", "count": len(title_results)})

        results["total_found"] = len(results["results"])
        logger.info(f"Semantic Scholar found {results['total_found']} results for {nct_id}")

        return results

    async def _search_papers(self, query: str, limit: int = 10) -> List[Dict]:
        """Execute Semantic Scholar paper search."""
        url = f"{self.BASE_URL}/paper/search"
        params = {
            "query": query,
            "limit": limit,
            "fields": "paperId,title,authors,year,venue,citationCount,influentialCitationCount,abstract,url,openAccessPdf"
        }

        headers = {}
        if self.api_key:
            headers["x-api-key"] = self.api_key

        try:
            await self._rate_limit()
            async with self.session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    papers = data.get("data", [])
                    return [self._format_paper(p) for p in papers]
                elif resp.status == 429:
                    logger.warning("Semantic Scholar rate limit hit")
                    return []
                else:
                    logger.debug(f"Semantic Scholar search returned {resp.status}")
                    return []
        except Exception as e:
            logger.debug(f"Semantic Scholar search error: {e}")
            return []

    def _format_paper(self, paper: Dict) -> Dict:
        """Format Semantic Scholar paper result."""
        authors = paper.get("authors", [])
        author_names = [a.get("name") for a in authors if a.get("name")][:5]

        return {
            "paperId": paper.get("paperId"),
            "title": paper.get("title"),
            "authors": author_names,
            "year": paper.get("year"),
            "venue": paper.get("venue"),
            "citation_count": paper.get("citationCount"),
            "influential_citations": paper.get("influentialCitationCount"),
            "abstract": paper.get("abstract", "")[:500] if paper.get("abstract") else None,
            "url": paper.get("url"),
            "open_access_pdf": paper.get("openAccessPdf", {}).get("url") if paper.get("openAccessPdf") else None,
            "source": "semantic_scholar"
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

    def _extract_intervention(self, trial_data: Dict[str, Any]) -> str:
        """Extract primary intervention."""
        try:
            protocol = trial_data.get("protocolSection", {})
            arms = protocol.get("armsInterventionsModule", {})
            interventions = arms.get("interventions", [])
            if interventions and isinstance(interventions, list):
                return interventions[0].get("name", "").strip()
            return ""
        except:
            return ""

    async def fetch(self, paper_id: str) -> Dict[str, Any]:
        """Fetch paper by Semantic Scholar paper ID."""
        url = f"{self.BASE_URL}/paper/{paper_id}"
        params = {
            "fields": "paperId,title,authors,year,venue,citationCount,influentialCitationCount,abstract,url,openAccessPdf,references,citations"
        }

        headers = {}
        if self.api_key:
            headers["x-api-key"] = self.api_key

        try:
            await self._rate_limit()
            async with self.session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return self._format_paper(data)
                return {"error": f"HTTP {resp.status}"}
        except Exception as e:
            return {"error": str(e)}


class CrossRefClient(BaseClient):
    """
    CrossRef API client - Free DOI lookup and scholarly metadata.
    No API key required, but polite pool is available with email.
    """

    BASE_URL = "https://api.crossref.org"

    async def search(self, nct_id: str, trial_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Search CrossRef for publications related to the clinical trial.

        Args:
            nct_id: NCT trial identifier
            trial_data: Full clinical trial data

        Returns:
            Dict with search results including DOI information
        """
        title = self._extract_title(trial_data)

        results = {
            "query": nct_id,
            "results": [],
            "total_found": 0,
            "search_strategies": []
        }

        # Strategy 1: Search by NCT ID
        nct_results = await self._search_works(nct_id, rows=10)
        if nct_results:
            results["results"].extend(nct_results)
            results["search_strategies"].append({"type": "nct_id", "count": len(nct_results)})

        # Strategy 2: Search by title if NCT search yields few results
        if len(results["results"]) < 5 and title:
            # Use first part of title
            title_query = " ".join(title.split()[:8])
            title_results = await self._search_works(title_query, rows=10)

            existing_dois = {r.get("doi") for r in results["results"] if r.get("doi")}
            for r in title_results:
                if r.get("doi") not in existing_dois:
                    results["results"].append(r)

            results["search_strategies"].append({"type": "title", "count": len(title_results)})

        results["total_found"] = len(results["results"])
        logger.info(f"CrossRef found {results['total_found']} results for {nct_id}")

        return results

    async def _search_works(self, query: str, rows: int = 10) -> List[Dict]:
        """Execute CrossRef works search."""
        url = f"{self.BASE_URL}/works"
        params = {
            "query": query,
            "rows": rows,
            "select": "DOI,title,author,published-print,published-online,container-title,abstract,is-referenced-by-count,type,URL"
        }

        headers = {
            "User-Agent": "NCTLookup/1.0 (mailto:support@amphoraxe.com)"  # Polite pool
        }

        try:
            await asyncio.sleep(0.2)  # Rate limiting
            async with self.session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    items = data.get("message", {}).get("items", [])
                    return [self._format_work(w) for w in items]
                else:
                    logger.debug(f"CrossRef search returned {resp.status}")
                    return []
        except Exception as e:
            logger.debug(f"CrossRef search error: {e}")
            return []

    def _format_work(self, work: Dict) -> Dict:
        """Format CrossRef work result."""
        # Extract authors
        authors = work.get("author", [])
        author_names = []
        for a in authors[:5]:
            name = f"{a.get('family', '')}, {a.get('given', '')}".strip(", ")
            if name:
                author_names.append(name)

        # Extract publication date
        pub_date = work.get("published-print") or work.get("published-online") or {}
        date_parts = pub_date.get("date-parts", [[]])[0]
        year = date_parts[0] if date_parts else None

        # Extract title
        titles = work.get("title", [])
        title = titles[0] if titles else None

        # Extract journal
        containers = work.get("container-title", [])
        journal = containers[0] if containers else None

        return {
            "doi": work.get("DOI"),
            "title": title,
            "authors": author_names,
            "journal": journal,
            "year": year,
            "citation_count": work.get("is-referenced-by-count"),
            "type": work.get("type"),
            "url": work.get("URL"),
            "abstract": work.get("abstract", "")[:500] if work.get("abstract") else None,
            "source": "crossref"
        }

    def _extract_title(self, trial_data: Dict[str, Any]) -> str:
        """Extract trial title."""
        try:
            protocol = trial_data.get("protocolSection", {})
            ident = protocol.get("identificationModule", {})
            return ident.get("officialTitle") or ident.get("briefTitle") or ""
        except:
            return ""

    async def fetch(self, doi: str) -> Dict[str, Any]:
        """Fetch work by DOI."""
        # Clean DOI
        doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
        url = f"{self.BASE_URL}/works/{doi}"

        headers = {
            "User-Agent": "NCTLookup/1.0 (mailto:support@amphoraxe.com)"
        }

        try:
            async with self.session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    work = data.get("message", {})
                    return self._format_work(work)
                return {"error": f"HTTP {resp.status}"}
        except Exception as e:
            return {"error": str(e)}


class DuckDuckGoClient(BaseClient):
    """
    Improved DuckDuckGo search client with relevance filtering.
    Uses targeted queries and filters out irrelevant results.
    """

    # Domains that typically have relevant clinical trial content
    RELEVANT_DOMAINS = [
        'clinicaltrials.gov', 'pubmed.ncbi.nlm.nih.gov', 'ncbi.nlm.nih.gov',
        'nature.com', 'nejm.org', 'thelancet.com', 'bmj.com', 'jamanetwork.com',
        'sciencedirect.com', 'springer.com', 'wiley.com', 'nih.gov',
        'fda.gov', 'ema.europa.eu', 'who.int', 'cochranelibrary.com',
        'medrxiv.org', 'biorxiv.org', 'researchgate.net', 'semanticscholar.org',
        'europepmc.org', 'scholar.google.com', 'plos.org', 'frontiersin.org'
    ]

    # Keywords that indicate irrelevant results
    IRRELEVANT_KEYWORDS = [
        'shopping', 'buy', 'price', 'amazon', 'ebay', 'alibaba',
        'facebook', 'twitter', 'instagram', 'tiktok', 'youtube',
        'recipe', 'dating', 'casino', 'betting', 'lottery'
    ]

    async def search(self, nct_id: str, trial_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Search DuckDuckGo with improved relevance filtering.

        Args:
            nct_id: NCT trial identifier
            trial_data: Full clinical trial data

        Returns:
            Dict with filtered search results
        """
        title = self._extract_title(trial_data)
        condition = self._extract_condition(trial_data)
        intervention = self._extract_intervention(trial_data)

        results = {
            "query": nct_id,
            "results": [],
            "total_found": 0,
            "filtered_out": 0,
            "search_strategies": []
        }

        try:
            from duckduckgo_search import DDGS

            # Strategy 1: Exact NCT ID search (most specific)
            query1 = f'"{nct_id}" clinical trial'
            raw_results1 = await self._execute_search(query1)
            filtered1 = self._filter_results(raw_results1, nct_id)
            results["results"].extend(filtered1)
            results["search_strategies"].append({
                "type": "nct_id_exact",
                "query": query1,
                "raw": len(raw_results1),
                "filtered": len(filtered1)
            })

            # Strategy 2: Search with condition + intervention (if we have few results)
            if len(results["results"]) < 5 and condition and intervention:
                query2 = f'{nct_id} {condition} {intervention}'
                raw_results2 = await self._execute_search(query2)
                filtered2 = self._filter_results(raw_results2, nct_id)

                existing_urls = {r.get("url") for r in results["results"]}
                for r in filtered2:
                    if r.get("url") not in existing_urls:
                        results["results"].append(r)

                results["search_strategies"].append({
                    "type": "condition_intervention",
                    "query": query2,
                    "raw": len(raw_results2),
                    "added": len([r for r in filtered2 if r.get("url") not in existing_urls])
                })

            # Strategy 3: Search by title keywords (if still few results)
            if len(results["results"]) < 5 and title:
                title_words = [w for w in title.split() if len(w) > 4][:5]
                query3 = f'{nct_id} {" ".join(title_words)}'
                raw_results3 = await self._execute_search(query3)
                filtered3 = self._filter_results(raw_results3, nct_id)

                existing_urls = {r.get("url") for r in results["results"]}
                for r in filtered3:
                    if r.get("url") not in existing_urls:
                        results["results"].append(r)

                results["search_strategies"].append({
                    "type": "title_keywords",
                    "query": query3,
                    "raw": len(raw_results3),
                    "added": len([r for r in filtered3 if r.get("url") not in existing_urls])
                })

            results["total_found"] = len(results["results"])
            logger.info(f"DuckDuckGo found {results['total_found']} relevant results for {nct_id}")

            return results

        except ImportError:
            return {
                "error": "duckduckgo-search library not installed. Run: pip install duckduckgo-search",
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

    async def _execute_search(self, query: str, max_results: int = 15) -> List[Dict]:
        """Execute DuckDuckGo search with rate limiting."""
        from duckduckgo_search import DDGS

        try:
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                lambda: self._search_sync(query, max_results)
            )
            return results
        except Exception as e:
            logger.debug(f"DuckDuckGo search error for '{query}': {e}")
            return []

    def _search_sync(self, query: str, max_results: int) -> List[Dict]:
        """Synchronous search helper with region set to US."""
        from duckduckgo_search import DDGS

        results = []
        try:
            with DDGS() as ddgs:
                # Set region to US to avoid non-English results
                search_results = ddgs.text(
                    query,
                    region='us-en',  # Force US English results
                    max_results=max_results
                )
                for result in search_results:
                    results.append({
                        'title': result.get('title', ''),
                        'url': result.get('href', ''),
                        'snippet': result.get('body', '')
                    })
        except Exception as e:
            logger.debug(f"DuckDuckGo sync search error: {e}")

        return results

    def _filter_results(self, results: List[Dict], nct_id: str) -> List[Dict]:
        """
        Filter search results for relevance.

        Criteria:
        1. Prefer results from known medical/research domains
        2. Remove results with irrelevant keywords
        3. Prioritize results that mention the NCT ID
        4. Remove non-English looking content
        """
        filtered = []
        nct_lower = nct_id.lower()

        for result in results:
            url = result.get('url', '').lower()
            title = result.get('title', '').lower()
            snippet = result.get('snippet', '').lower()

            # Skip if URL contains irrelevant keywords
            if any(kw in url for kw in self.IRRELEVANT_KEYWORDS):
                continue

            # Skip if title/snippet contains too many non-ASCII characters (likely non-English)
            title_ascii_ratio = sum(1 for c in result.get('title', '') if ord(c) < 128) / max(len(result.get('title', '')), 1)
            if title_ascii_ratio < 0.7:
                continue

            # Calculate relevance score
            score = 0

            # Bonus for mentioning NCT ID
            if nct_lower in title or nct_lower in snippet:
                score += 10

            # Bonus for relevant domains
            if any(domain in url for domain in self.RELEVANT_DOMAINS):
                score += 5

            # Bonus for medical/research keywords
            medical_keywords = ['clinical', 'trial', 'study', 'research', 'patient', 'treatment', 'therapy', 'drug', 'efficacy', 'safety']
            for kw in medical_keywords:
                if kw in title or kw in snippet:
                    score += 1

            # Only include results with minimum relevance
            if score >= 3:
                result['relevance_score'] = score
                result['source'] = 'duckduckgo'
                filtered.append(result)

        # Sort by relevance score
        filtered.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)

        return filtered[:10]  # Return top 10 most relevant

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

    def _extract_intervention(self, trial_data: Dict[str, Any]) -> str:
        """Extract primary intervention."""
        try:
            protocol = trial_data.get("protocolSection", {})
            arms = protocol.get("armsInterventionsModule", {})
            interventions = arms.get("interventions", [])
            if interventions and isinstance(interventions, list):
                return interventions[0].get("name", "").strip()
            return ""
        except:
            return ""

    async def fetch(self, identifier: str) -> Dict[str, Any]:
        """Not implemented for DuckDuckGo."""
        return {"error": "Fetch not supported for DuckDuckGo"}


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
    
    async def fetch(self, identifier: str) -> Dict[str, Any]:
        """
        Fetch is not the primary method for OpenFDA.
        Use search() method with trial data instead.
        
        Args:
            identifier: Not used for OpenFDA
            
        Returns:
            Error message directing to use search() instead
        """
        return {
            "error": "Use search() method with trial data",
            "note": "OpenFDA requires trial context for effective searching"
        }
    
    async def search(self, nct_id: str, trial_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Comprehensive OpenFDA search using trial data.
        
        Args:
            nct_id: NCT trial identifier
            trial_data: Full clinical trial data dictionary
            
        Returns:
            Dict with combined results from multiple FDA endpoints
        """
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
                title_words = title.split()
                for word in title_words:
                    # Check if word looks like a drug name (capitalized, not common words)
                    if (word and len(word) > 3 and 
                        word[0].isupper() and 
                        word.lower() not in ['trial', 'study', 'phase', 'randomized', 'controlled', 'versus', 'with', 'without']):
                        clean_word = word.strip('()[]{}:,;.')
                        if clean_word:
                            identifiers.append(clean_word)
            
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
        except asyncio.TimeoutError:
            logger.debug(f"OpenFDA labels timeout for '{drug_name}'")
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
        except asyncio.TimeoutError:
            logger.debug(f"OpenFDA events timeout for '{drug_name}'")
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
        except asyncio.TimeoutError:
            logger.debug(f"OpenFDA enforcement timeout for '{drug_name}'")
            return []
        except Exception as e:
            logger.debug(f"OpenFDA enforcement search error for '{drug_name}': {e}")
            return []
    
    def _format_label_result(self, result: Dict) -> Dict:
        """Format drug label result."""
        openfda = result.get("openfda", {})
        return {
            "type": "drug_label",
            "product": openfda.get("brand_name", ["Unknown"])[0] if openfda.get("brand_name") else "Unknown",
            "manufacturer": openfda.get("manufacturer_name", ["Unknown"])[0] if openfda.get("manufacturer_name") else "Unknown",
            "purpose": result.get("purpose", [""])[0][:200] if result.get("purpose") else None,
            "warnings": result.get("warnings", [""])[0][:200] if result.get("warnings") else None
        }
    
    def _format_event_result(self, result: Dict) -> Dict:
        """Format adverse event result."""
        patient = result.get("patient", {})
        reactions = patient.get("reaction", [])
        
        return {
            "type": "adverse_event",
            "date": result.get("receivedate", "Unknown"),
            "serious": result.get("serious", 0),
            "reactions": [r.get("reactionmeddrapt", "Unknown") for r in reactions[:3]]
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
        import json
        seen = set()
        unique = []
        
        for result in results:
            # Create a simple hash of the result
            result_hash = json.dumps(result, sort_keys=True)
            if result_hash not in seen:
                seen.add(result_hash)
                unique.append(result)
        
        return unique
    
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
    
    # Common noise words to filter out from intervention names
    NOISE_WORDS = {
        'vaccine', 'peptide', 'drug', 'therapy', 'treatment', 'injection',
        'infusion', 'oral', 'iv', 'subcutaneous', 'intramuscular', 'placebo',
        'dose', 'mg', 'mcg', 'ml', 'daily', 'weekly', 'monthly', 'phase',
        'study', 'trial', 'arm', 'group', 'combination', 'plus', 'with',
        'low', 'high', 'standard', 'experimental', 'control', 'active'
    }

    # Known drug-to-target mappings for common clinical trial drugs
    DRUG_TARGET_MAP = {
        'pembrolizumab': ['PD-1', 'PDCD1'],
        'nivolumab': ['PD-1', 'PDCD1'],
        'atezolizumab': ['PD-L1', 'CD274'],
        'durvalumab': ['PD-L1', 'CD274'],
        'ipilimumab': ['CTLA-4', 'CTLA4'],
        'trastuzumab': ['HER2', 'ERBB2'],
        'pertuzumab': ['HER2', 'ERBB2'],
        'cetuximab': ['EGFR'],
        'rituximab': ['CD20', 'MS4A1'],
        'bevacizumab': ['VEGF', 'VEGFA'],
        'adalimumab': ['TNF', 'TNFA'],
        'infliximab': ['TNF', 'TNFA'],
        'etanercept': ['TNF', 'TNFA'],
    }

    def _extract_protein_terms(self, trial_data: Dict[str, Any]) -> List[str]:
        """
        Extract potential protein/gene names from trial data.

        Enhanced to:
        1. Extract target proteins from conditions (e.g., HER2 from "HER2-positive Breast Cancer")
        2. Map known drugs to their target proteins
        3. Extract gene/protein identifiers from descriptions
        4. Filter noise words for cleaner searches
        """
        terms = []
        seen = set()  # Track seen terms to avoid duplicates

        def add_term(term: str):
            """Add term if not already seen."""
            term = term.strip()
            if term and term.lower() not in seen:
                seen.add(term.lower())
                terms.append(term)

        try:
            protocol = trial_data.get("protocolSection", {})

            # 1. Extract from interventions (original behavior)
            arms_interventions = protocol.get("armsInterventionsModule", {})
            interventions = arms_interventions.get("interventions", [])

            for intervention in interventions:
                if isinstance(intervention, dict):
                    name = intervention.get("name", "").strip()
                    if name:
                        # Check if this is a known drug with target mapping
                        name_lower = name.lower()
                        for drug, targets in self.DRUG_TARGET_MAP.items():
                            if drug in name_lower:
                                for target in targets:
                                    add_term(target)

                        # Also add cleaned intervention name
                        cleaned = self._clean_intervention_name(name)
                        if cleaned:
                            add_term(cleaned)

                    other_names = intervention.get("otherNames", [])
                    if isinstance(other_names, list):
                        for n in other_names:
                            if n and n.strip():
                                add_term(n.strip())

            # 2. Extract protein/gene names from conditions
            conditions_module = protocol.get("conditionsModule", {})
            conditions = conditions_module.get("conditions", [])

            for condition in conditions:
                if isinstance(condition, str):
                    # Look for protein/gene patterns in conditions
                    extracted = self._extract_gene_names(condition)
                    for gene in extracted:
                        add_term(gene)

            # 3. Extract from brief title and description
            id_module = protocol.get("identificationModule", {})
            brief_title = id_module.get("briefTitle", "")

            desc_module = protocol.get("descriptionModule", {})
            brief_summary = desc_module.get("briefSummary", "")

            for text in [brief_title, brief_summary]:
                if text:
                    extracted = self._extract_gene_names(text)
                    for gene in extracted:
                        add_term(gene)

        except Exception as e:
            logger.warning(f"Error extracting protein terms: {e}")

        logger.debug(f"Extracted protein search terms: {terms[:10]}")
        return terms[:10]  # Limit to 10 terms

    def _clean_intervention_name(self, name: str) -> str:
        """Remove noise words from intervention name."""
        words = name.split()
        cleaned = [w for w in words if w.lower() not in self.NOISE_WORDS and len(w) > 2]
        return ' '.join(cleaned) if cleaned else ''

    def _extract_gene_names(self, text: str) -> List[str]:
        """
        Extract potential gene/protein names from text using patterns.

        Looks for:
        - All-caps words 2-10 chars (e.g., HER2, EGFR, BRCA1)
        - Words with numbers suggesting gene names (e.g., TP53, BCL2)
        - Known receptor patterns (e.g., PD-1, CTLA-4)
        """
        import re
        genes = []

        # Pattern 1: All caps 2-10 chars, may include numbers (HER2, BRCA1, TP53)
        caps_pattern = r'\b([A-Z][A-Z0-9]{1,9})\b'
        for match in re.findall(caps_pattern, text):
            # Filter out common non-gene abbreviations
            if match not in {'NCT', 'FDA', 'USA', 'AND', 'THE', 'FOR', 'WITH', 'NOT'}:
                genes.append(match)

        # Pattern 2: Receptor names with hyphen (PD-1, CTLA-4, HER-2)
        receptor_pattern = r'\b([A-Z]{2,5}-[0-9A-Z]{1,3})\b'
        for match in re.findall(receptor_pattern, text):
            genes.append(match)

        # Pattern 3: Known protein keywords followed by gene names
        known_patterns = [
            r'(?:anti-?|targeting\s+)([A-Z][A-Z0-9]{1,9})',
            r'([A-Z][A-Z0-9]{1,9})[\s-]?(?:positive|negative|expressing)',
            r'([A-Z][A-Z0-9]{1,9})[\s-]?(?:inhibitor|antibody|antagonist|agonist)',
        ]
        for pattern in known_patterns:
            for match in re.findall(pattern, text, re.IGNORECASE):
                if isinstance(match, str) and len(match) >= 2:
                    genes.append(match.upper())

        return list(set(genes))  # Deduplicate
    
    async def _search_proteins(self, query: str) -> List[Dict]:
        """
        Search UniProt for proteins matching query.

        Searches human proteins first (most relevant for clinical trials),
        then falls back to broader search if no results.
        """
        url = f"{self.BASE_URL}/uniprotkb/search"

        # Try human proteins first (most relevant for clinical trials)
        human_query = f"({query}) AND (organism_id:9606)"

        params = {
            "query": human_query,
            "format": "json",
            "size": 5,  # Limit results per query
            # CRITICAL: Must explicitly request sequence field - not included by default
            "fields": "accession,id,protein_name,gene_names,organism_name,sequence,cc_function,keyword"
        }

        try:
            async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = data.get("results", [])

                    if results:
                        logger.debug(f"UniProt: Found {len(results)} human proteins for '{query}'")
                        return [self._format_protein(p) for p in results]

            # If no human results, try broader search (but still prefer reviewed entries)
            broader_query = f"({query}) AND (reviewed:true)"
            params["query"] = broader_query

            async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = data.get("results", [])

                    if results:
                        logger.debug(f"UniProt: Found {len(results)} reviewed proteins for '{query}'")
                        return [self._format_protein(p) for p in results]

            # Final fallback: any results
            params["query"] = query
            async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = data.get("results", [])
                    logger.debug(f"UniProt: Found {len(results)} proteins for '{query}' (broad search)")
                    return [self._format_protein(p) for p in results]
                else:
                    logger.debug(f"UniProt search returned {resp.status} for '{query}'")
                    return []

        except Exception as e:
            logger.debug(f"UniProt search error for '{query}': {e}")
            return []
    
    def _format_protein(self, protein: Dict) -> Dict:
        """Format UniProt protein entry."""
        # Extract sequence information - CRITICAL for annotation
        sequence_info = protein.get("sequence", {})
        sequence_value = sequence_info.get("value", "")
        sequence_length = sequence_info.get("length", 0)

        # Extract function comments for classification
        function_text = ""
        comments = protein.get("comments", [])
        for comment in comments:
            if comment.get("commentType") == "FUNCTION":
                texts = comment.get("texts", [])
                if texts:
                    function_text = texts[0].get("value", "")
                break

        # Extract keywords
        keywords = []
        for kw in protein.get("keywords", []):
            kw_name = kw.get("name", "")
            if kw_name:
                keywords.append(kw_name)

        return {
            "primaryAccession": protein.get("primaryAccession"),
            "accession": protein.get("primaryAccession"),  # Keep for backward compatibility
            "uniProtkbId": protein.get("uniProtkbId"),
            "name": protein.get("uniProtkbId"),  # Keep for backward compatibility
            "proteinDescription": protein.get("proteinDescription", {}),
            "protein_name": protein.get("proteinDescription", {}).get("recommendedName", {}).get("fullName", {}).get("value"),
            "organism": protein.get("organism", {}),
            "gene": protein.get("genes", [{}])[0].get("geneName", {}).get("value") if protein.get("genes") else None,
            # CRITICAL: Include sequence data for annotation
            "sequence": {
                "value": sequence_value,
                "length": sequence_length
            },
            # Include function and keywords for classification
            "comments": comments,
            "keywords": protein.get("keywords", []),
            "function": function_text
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
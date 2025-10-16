"""
Semantic Scholar API Client
AI-powered academic paper search and citation analysis.

API Documentation: https://api.semanticscholar.org/
"""
import aiohttp
import asyncio
from typing import Dict, List, Any, Optional
import os

from amp_llm.config import get_logger

logger = get_logger(__name__)


class SemanticScholarClient:
    """
    Semantic Scholar API client.
    
    Provides access to:
    - Paper search
    - Citation data
    - Paper recommendations
    - Author information
    - Full paper metadata
    """
    
    def __init__(self, api_key: Optional[str] = None, timeout: int = 30, max_results: int = 10):
        """
        Initialize Semantic Scholar client.
        
        Args:
            api_key: Optional API key for higher rate limits
            timeout: Request timeout in seconds
            max_results: Maximum results to return
        """
        self.base_url = "https://api.semanticscholar.org/graph/v1"
        self.api_key = api_key or os.getenv('SEMANTIC_SCHOLAR_API_KEY')
        self.timeout = timeout
        self.max_results = max_results
        
        # Rate limiting: 100 req/5min without key, 5000 req/5min with key
        self.rate_limit_delay = 0.3 if not self.api_key else 0.06
    
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with optional API key."""
        headers = {
            'User-Agent': 'Clinical-Trials-Research-Bot/1.0'
        }
        
        if self.api_key:
            headers['x-api-key'] = self.api_key
        
        return headers
    
    async def search_papers(
        self,
        query: str,
        fields: Optional[List[str]] = None,
        year: Optional[str] = None,
        venue: Optional[str] = None,
        open_access_pdf: bool = False
    ) -> Dict[str, Any]:
        """
        Search for academic papers.
        
        Args:
            query: Search query
            fields: Fields to return (default: title, authors, year, abstract)
            year: Year filter (e.g., "2020", "2020-2022")
            venue: Venue/journal filter
            open_access_pdf: Only return papers with open access PDFs
            
        Returns:
            Dictionary with search results
        """
        print(f"🔍 Semantic Scholar: Searching for '{query[:100]}'...")
        
        if fields is None:
            fields = [
                'paperId', 'title', 'abstract', 'year', 'authors',
                'citationCount', 'referenceCount', 'url', 'venue',
                'publicationTypes', 'openAccessPdf', 'fieldsOfStudy'
            ]
        
        url = f"{self.base_url}/paper/search"
        
        params = {
            'query': query,
            'fields': ','.join(fields),
            'limit': self.max_results
        }
        
        if year:
            params['year'] = year
        
        if venue:
            params['venue'] = venue
        
        if open_access_pdf:
            params['openAccessPdf'] = ''
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        papers = data.get('data', [])
                        total = data.get('total', len(papers))
                        
                        print(f"✅ Semantic Scholar: Found {len(papers)} paper(s) ({total} total)")
                        logger.info(f"Semantic Scholar search returned {len(papers)} results")
                        
                        await asyncio.sleep(self.rate_limit_delay)
                        
                        return {
                            "papers": papers,
                            "total": total,
                            "offset": data.get('offset', 0),
                            "next": data.get('next')
                        }
                    else:
                        error_text = await resp.text()
                        print(f"⚠️ Semantic Scholar: Error {resp.status}")
                        logger.warning(f"Semantic Scholar error {resp.status}: {error_text[:200]}")
                        return {"papers": [], "error": f"http_error_{resp.status}"}
        
        except asyncio.TimeoutError:
            print(f"⚠️ Semantic Scholar: Search timed out")
            return {"papers": [], "error": "timeout"}
        except Exception as e:
            print(f"❌ Semantic Scholar: Search error: {e}")
            logger.error(f"Semantic Scholar search error: {e}")
            return {"papers": [], "error": str(e)}
    
    async def get_paper_by_id(
        self,
        paper_id: str,
        fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Get paper details by Semantic Scholar ID, DOI, ArXiv ID, etc.
        
        Args:
            paper_id: Paper identifier (S2 ID, DOI, ArXiv ID, PMID, etc.)
            fields: Fields to return
            
        Returns:
            Dictionary with paper details
        """
        print(f"🔍 Semantic Scholar: Fetching paper {paper_id}...")
        
        if fields is None:
            fields = [
                'paperId', 'title', 'abstract', 'year', 'authors',
                'citationCount', 'referenceCount', 'citations', 'references',
                'url', 'venue', 'publicationTypes', 'openAccessPdf',
                'fieldsOfStudy', 'embedding'
            ]
        
        # Handle different ID types
        if paper_id.startswith('PMID:'):
            paper_id = f"PMID:{paper_id.replace('PMID:', '')}"
        elif paper_id.startswith('PMC'):
            paper_id = f"PMCID:{paper_id}"
        elif '/' in paper_id or paper_id.startswith('10.'):
            paper_id = f"DOI:{paper_id}"
        
        url = f"{self.base_url}/paper/{paper_id}"
        
        params = {
            'fields': ','.join(fields)
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    if resp.status == 200:
                        paper = await resp.json()
                        
                        print(f"✅ Semantic Scholar: Retrieved paper {paper_id}")
                        logger.info(f"Retrieved paper {paper_id}")
                        
                        await asyncio.sleep(self.rate_limit_delay)
                        
                        return paper
                    elif resp.status == 404:
                        print(f"ℹ️ Semantic Scholar: Paper {paper_id} not found")
                        return {"error": "not_found", "paper_id": paper_id}
                    else:
                        error_text = await resp.text()
                        print(f"⚠️ Semantic Scholar: Error {resp.status}")
                        return {"error": f"http_error_{resp.status}", "paper_id": paper_id}
        
        except asyncio.TimeoutError:
            print(f"⚠️ Semantic Scholar: Fetch timed out for {paper_id}")
            return {"error": "timeout", "paper_id": paper_id}
        except Exception as e:
            print(f"❌ Semantic Scholar: Fetch error for {paper_id}: {e}")
            logger.error(f"Semantic Scholar fetch error: {e}")
            return {"error": str(e), "paper_id": paper_id}
    
    async def get_paper_citations(
        self,
        paper_id: str,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get papers that cite this paper.
        
        Args:
            paper_id: Paper identifier
            limit: Maximum number of citations to return
            
        Returns:
            Dictionary with citing papers
        """
        print(f"🔍 Semantic Scholar: Fetching citations for {paper_id}...")
        
        limit = limit or self.max_results
        
        url = f"{self.base_url}/paper/{paper_id}/citations"
        
        params = {
            'fields': 'paperId,title,year,authors,citationCount',
            'limit': limit
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        citations = data.get('data', [])
                        
                        print(f"✅ Semantic Scholar: Found {len(citations)} citing paper(s)")
                        logger.info(f"Retrieved {len(citations)} citations for {paper_id}")
                        
                        await asyncio.sleep(self.rate_limit_delay)
                        
                        return {
                            "citations": citations,
                            "total": len(citations),
                            "next": data.get('next')
                        }
                    else:
                        print(f"⚠️ Semantic Scholar: Error {resp.status}")
                        return {"citations": [], "error": f"http_error_{resp.status}"}
        
        except Exception as e:
            print(f"❌ Semantic Scholar: Citations error: {e}")
            return {"citations": [], "error": str(e)}
    
    async def get_paper_references(
        self,
        paper_id: str,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get papers referenced by this paper.
        
        Args:
            paper_id: Paper identifier
            limit: Maximum number of references to return
            
        Returns:
            Dictionary with referenced papers
        """
        print(f"🔍 Semantic Scholar: Fetching references for {paper_id}...")
        
        limit = limit or self.max_results
        
        url = f"{self.base_url}/paper/{paper_id}/references"
        
        params = {
            'fields': 'paperId,title,year,authors,citationCount',
            'limit': limit
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        references = data.get('data', [])
                        
                        print(f"✅ Semantic Scholar: Found {len(references)} reference(s)")
                        logger.info(f"Retrieved {len(references)} references for {paper_id}")
                        
                        await asyncio.sleep(self.rate_limit_delay)
                        
                        return {
                            "references": references,
                            "total": len(references),
                            "next": data.get('next')
                        }
                    else:
                        print(f"⚠️ Semantic Scholar: Error {resp.status}")
                        return {"references": [], "error": f"http_error_{resp.status}"}
        
        except Exception as e:
            print(f"❌ Semantic Scholar: References error: {e}")
            return {"references": [], "error": str(e)}
    
    async def get_author_papers(
        self,
        author_id: str,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get papers by a specific author.
        
        Args:
            author_id: Semantic Scholar author ID
            limit: Maximum number of papers to return
            
        Returns:
            Dictionary with author's papers
        """
        print(f"🔍 Semantic Scholar: Fetching papers for author {author_id}...")
        
        limit = limit or self.max_results
        
        url = f"{self.base_url}/author/{author_id}/papers"
        
        params = {
            'fields': 'paperId,title,year,citationCount,venue',
            'limit': limit
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        papers = data.get('data', [])
                        
                        print(f"✅ Semantic Scholar: Found {len(papers)} paper(s) by author")
                        logger.info(f"Retrieved {len(papers)} papers for author {author_id}")
                        
                        await asyncio.sleep(self.rate_limit_delay)
                        
                        return {
                            "papers": papers,
                            "total": len(papers),
                            "next": data.get('next')
                        }
                    else:
                        print(f"⚠️ Semantic Scholar: Error {resp.status}")
                        return {"papers": [], "error": f"http_error_{resp.status}"}
        
        except Exception as e:
            print(f"❌ Semantic Scholar: Author papers error: {e}")
            return {"papers": [], "error": str(e)}
    
    async def recommend_papers(
        self,
        paper_id: str,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get recommended papers based on a paper.
        
        Args:
            paper_id: Paper identifier
            limit: Maximum number of recommendations
            
        Returns:
            Dictionary with recommended papers
        """
        print(f"🔍 Semantic Scholar: Getting recommendations for {paper_id}...")
        
        limit = limit or self.max_results
        
        url = f"{self.base_url}/recommendations/v1/papers/forpaper/{paper_id}"
        
        params = {
            'fields': 'paperId,title,year,authors,citationCount,abstract',
            'limit': limit
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        recommendations = data.get('recommendedPapers', [])
                        
                        print(f"✅ Semantic Scholar: Found {len(recommendations)} recommendation(s)")
                        logger.info(f"Retrieved {len(recommendations)} recommendations")
                        
                        await asyncio.sleep(self.rate_limit_delay)
                        
                        return {
                            "recommendations": recommendations,
                            "total": len(recommendations)
                        }
                    else:
                        print(f"⚠️ Semantic Scholar: Error {resp.status}")
                        return {"recommendations": [], "error": f"http_error_{resp.status}"}
        
        except Exception as e:
            print(f"❌ Semantic Scholar: Recommendations error: {e}")
            return {"recommendations": [], "error": str(e)}
    
    async def search_by_clinical_trial(
        self,
        nct_id: str,
        title: str = None,
        condition: str = None
    ) -> Dict[str, Any]:
        """
        Search for papers related to a clinical trial.
        
        Args:
            nct_id: NCT number
            title: Trial title
            condition: Medical condition
            
        Returns:
            Dictionary with related papers
        """
        print(f"🔍 Semantic Scholar: Searching papers for {nct_id}...")
        
        # Build comprehensive query
        query_parts = [nct_id]
        
        if title:
            # Add key terms from title (first 10 words)
            title_terms = ' '.join(title.split()[:10])
            query_parts.append(title_terms)
        
        if condition:
            query_parts.append(condition)
        
        query = ' '.join(query_parts)
        
        # Search with clinical trial filters
        results = await self.search_papers(
            query=query,
            year="2000-",  # Last 20+ years
            fields=[
                'paperId', 'title', 'abstract', 'year', 'authors',
                'citationCount', 'url', 'venue', 'publicationTypes',
                'openAccessPdf'
            ]
        )
        
        if results.get("papers"):
            print(f"✅ Found {len(results['papers'])} paper(s) for {nct_id}")
        
        return results
    
    async def batch_search(
        self,
        queries: List[str]
    ) -> Dict[str, Any]:
        """
        Perform multiple searches concurrently.
        
        Args:
            queries: List of search queries
            
        Returns:
            Dictionary mapping queries to results
        """
        print(f"🔍 Semantic Scholar: Batch searching {len(queries)} quer(ies)...")
        
        tasks = [
            self.search_papers(query)
            for query in queries
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Organize results
        batch_results = {}
        success_count = 0
        
        for query, result in zip(queries, results):
            if isinstance(result, Exception):
                logger.error(f"Batch search failed for '{query}': {result}")
                batch_results[query] = {"papers": [], "error": str(result)}
            else:
                batch_results[query] = result
                if result.get("papers"):
                    success_count += 1
        
        print(f"✅ Semantic Scholar: {success_count}/{len(queries)} searches successful")
        
        return batch_results
    
    async def get_trending_papers(
        self,
        field: Optional[str] = None,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get trending papers (highly cited recent papers).
        
        Args:
            field: Field of study filter (e.g., "Medicine", "Biology")
            limit: Maximum number of papers
            
        Returns:
            Dictionary with trending papers
        """
        print(f"🔍 Semantic Scholar: Getting trending papers...")
        
        limit = limit or self.max_results
        
        # Search for recent highly-cited papers
        current_year = 2025
        year_range = f"{current_year-2}-{current_year}"
        
        query = "clinical trial" if not field else f"{field} clinical trial"
        
        results = await self.search_papers(
            query=query,
            year=year_range,
            fields=[
                'paperId', 'title', 'year', 'authors',
                'citationCount', 'abstract', 'url', 'venue'
            ]
        )
        
        # Sort by citation count
        if results.get("papers"):
            papers = sorted(
                results["papers"],
                key=lambda p: p.get("citationCount", 0),
                reverse=True
            )
            
            print(f"✅ Semantic Scholar: Found {len(papers)} trending paper(s)")
            
            return {
                "papers": papers[:limit],
                "total": len(papers)
            }
        
        return results
    
    async def bulk_paper_fetch(
        self,
        paper_ids: List[str]
    ) -> Dict[str, Any]:
        """
        Fetch multiple papers by ID concurrently.
        
        Args:
            paper_ids: List of paper IDs
            
        Returns:
            Dictionary mapping paper IDs to paper data
        """
        print(f"🔍 Semantic Scholar: Bulk fetching {len(paper_ids)} paper(s)...")
        
        tasks = [
            self.get_paper_by_id(paper_id)
            for paper_id in paper_ids
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Organize results
        bulk_results = {}
        success_count = 0
        
        for paper_id, result in zip(paper_ids, results):
            if isinstance(result, Exception):
                logger.error(f"Bulk fetch failed for {paper_id}: {result}")
                bulk_results[paper_id] = {"error": str(result)}
            else:
                bulk_results[paper_id] = result
                if "error" not in result:
                    success_count += 1
        
        print(f"✅ Semantic Scholar: Successfully fetched {success_count}/{len(paper_ids)}")
        
        return bulk_results
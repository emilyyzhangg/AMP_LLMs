"""
Google Search via SerpAPI Client
Provides access to Google Search results via SerpAPI.

API Documentation: https://serpapi.com/
Requires: SERPAPI_KEY environment variable
"""
import asyncio
import aiohttp
from typing import Dict, List, Any, Optional
import os

from amp_llm.config import get_logger

logger = get_logger(__name__)


class SerpAPIClient:
    """
    Google Search via SerpAPI.
    
    Provides high-quality search results from Google.
    Requires API key (free tier: 100 searches/month).
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: int = 30,
        max_results: int = 10
    ):
        """
        Initialize SerpAPI client.
        
        Args:
            api_key: SerpAPI key (or set SERPAPI_KEY env var)
            timeout: Request timeout in seconds
            max_results: Maximum results to return
        """
        self.api_key = api_key or os.getenv('SERPAPI_KEY')
        self.base_url = "https://serpapi.com/search"
        self.timeout = timeout
        self.max_results = max_results
        self.name = "Google (SerpAPI)"
        
        if not self.api_key:
            logger.warning(f"{self.name}: No API key found. Set SERPAPI_KEY environment variable.")
    
    async def search(
        self,
        query: str,
        search_type: str = 'search',
        location: str = None
    ) -> Dict[str, Any]:
        """
        Search Google via SerpAPI.
        
        Args:
            query: Search query
            search_type: Type of search (search, scholar, news, etc.)
            location: Location for localized results
            
        Returns:
            Dictionary with search results
        """
        if not self.api_key:
            return {
                "results": [],
                "error": "No API key. Set SERPAPI_KEY in .env file. Get key at https://serpapi.com/"
            }
        
        print(f"🔍 {self.name}: Searching for '{query[:100]}'...")
        
        params = {
            'q': query,
            'api_key': self.api_key,
            'num': self.max_results,
            'engine': 'google'
        }
        
        if location:
            params['location'] = location
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.base_url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results = self._parse_results(data, search_type)
                        
                        print(f"✅ {self.name}: Found {len(results)} result(s)")
                        logger.info(f"{self.name} search returned {len(results)} results")
                        
                        return {
                            "results": results,
                            "total_count": len(results),
                            "search_metadata": data.get('search_metadata', {})
                        }
                    elif resp.status == 401:
                        error_msg = "Invalid API key"
                        print(f"❌ {self.name}: {error_msg}")
                        return {"results": [], "error": error_msg}
                    else:
                        error_text = await resp.text()
                        print(f"⚠️ {self.name}: Error {resp.status}")
                        logger.warning(f"{self.name} error {resp.status}: {error_text[:200]}")
                        return {"results": [], "error": f"http_error_{resp.status}"}
        
        except asyncio.TimeoutError:
            print(f"⚠️ {self.name}: Search timed out")
            return {"results": [], "error": "timeout"}
        except Exception as e:
            print(f"❌ {self.name}: Search error: {e}")
            logger.error(f"{self.name} search error: {e}")
            return {"results": [], "error": str(e)}
    
    def _parse_results(self, data: Dict[str, Any], search_type: str) -> List[Dict[str, Any]]:
        """Parse SerpAPI response."""
        results = []
        
        # Organic results (regular search)
        for item in data.get('organic_results', [])[:self.max_results]:
            results.append({
                'title': item.get('title', ''),
                'url': item.get('link', ''),
                'snippet': item.get('snippet', ''),
                'position': item.get('position'),
                'source': 'google_serpapi'
            })
        
        # Knowledge graph
        kg = data.get('knowledge_graph')
        if kg:
            results.append({
                'title': kg.get('title', ''),
                'url': kg.get('website', ''),
                'snippet': kg.get('description', ''),
                'type': 'knowledge_graph',
                'source': 'google_serpapi'
            })
        
        return results
    
    async def search_scholar(self, query: str) -> Dict[str, Any]:
        """
        Search Google Scholar via SerpAPI.
        
        Args:
            query: Academic search query
            
        Returns:
            Dictionary with scholar results
        """
        if not self.api_key:
            return {
                "results": [],
                "error": "No API key configured"
            }
        
        print(f"🔍 {self.name} Scholar: Searching for '{query[:100]}'...")
        
        params = {
            'q': query,
            'api_key': self.api_key,
            'num': self.max_results,
            'engine': 'google_scholar'
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.base_url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results = []
                        
                        for item in data.get('organic_results', [])[:self.max_results]:
                            results.append({
                                'title': item.get('title', ''),
                                'url': item.get('link', ''),
                                'snippet': item.get('snippet', ''),
                                'publication': item.get('publication_info', {}).get('summary', ''),
                                'cited_by': item.get('inline_links', {}).get('cited_by', {}).get('total'),
                                'source': 'google_scholar'
                            })
                        
                        print(f"✅ {self.name} Scholar: Found {len(results)} paper(s)")
                        
                        return {
                            "results": results,
                            "total_count": len(results)
                        }
                    else:
                        error_text = await resp.text()
                        return {"results": [], "error": f"http_error_{resp.status}"}
        
        except Exception as e:
            print(f"❌ {self.name} Scholar: Error: {e}")
            return {"results": [], "error": str(e)}
    
    async def search_by_nct(self, nct_id: str) -> Dict[str, Any]:
        """
        Search for clinical trial by NCT number.
        
        Args:
            nct_id: NCT number
            
        Returns:
            Dictionary with search results
        """
        query = f"{nct_id} clinical trial"
        return await self.search(query)
    
    async def search_by_clinical_trial(
        self,
        nct_id: str,
        title: str = None,
        condition: str = None
    ) -> Dict[str, Any]:
        """
        Search for publications related to a clinical trial.
        
        Args:
            nct_id: NCT number
            title: Trial title
            condition: Medical condition
            
        Returns:
            Dictionary with related publications
        """
        print(f"🔍 {self.name}: Searching for papers related to {nct_id}...")
        
        # Build comprehensive query
        query_parts = [nct_id]
        
        if title:
            # Add key terms from title (first 10 words)
            title_terms = ' '.join(title.split()[:10])
            query_parts.append(title_terms)
        
        if condition:
            query_parts.append(condition)
        
        query = ' '.join(query_parts)
        
        # Try both regular search and scholar
        regular_results = await self.search(query)
        scholar_results = await self.search_scholar(query)
        
        # Combine results
        combined_results = regular_results.get('results', []) + scholar_results.get('results', [])
        
        if combined_results:
            print(f"✅ Found {len(combined_results)} result(s) for {nct_id}")
        else:
            print(f"ℹ️ No results for {nct_id} in {self.name}")
        
        return {
            "results": combined_results,
            "total_count": len(combined_results),
            "regular_count": len(regular_results.get('results', [])),
            "scholar_count": len(scholar_results.get('results', []))
        }
    
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
        print(f"🔍 {self.name}: Batch searching {len(queries)} quer(ies)...")
        
        tasks = [self.search(query) for query in queries]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Organize results
        batch_results = {}
        success_count = 0
        
        for query, result in zip(queries, results):
            if isinstance(result, Exception):
                logger.error(f"Batch search failed for '{query}': {result}")
                batch_results[query] = {"results": [], "error": str(result)}
            else:
                batch_results[query] = result
                if result.get("results"):
                    success_count += 1
        
        print(f"✅ {self.name}: {success_count}/{len(queries)} searches successful")
        
        return batch_results
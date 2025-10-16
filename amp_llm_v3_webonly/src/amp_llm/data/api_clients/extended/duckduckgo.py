"""
DuckDuckGo Search API Client
Free web search without API keys.

Uses: duckduckgo-search library
"""
import asyncio
from typing import Dict, List, Any, Optional

from amp_llm.config import get_logger

logger = get_logger(__name__)


class DuckDuckGoClient:
    """
    DuckDuckGo search client.
    
    Free web search for clinical trial information.
    No API key required.
    """
    
    def __init__(self, timeout: int = 30, max_results: int = 10):
        """
        Initialize DuckDuckGo client.
        
        Args:
            timeout: Request timeout in seconds
            max_results: Maximum results to return
        """
        self.timeout = timeout
        self.max_results = max_results
        self.name = "DuckDuckGo"
    
    async def search(
        self,
        query: str,
        region: str = 'wt-wt',
        safesearch: str = 'moderate'
    ) -> Dict[str, Any]:
        """
        Search DuckDuckGo.
        
        Args:
            query: Search query
            region: Region code (default: worldwide)
            safesearch: Safe search setting
            
        Returns:
            Dictionary with search results
        """
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            logger.error("duckduckgo-search not installed")
            return {
                "results": [],
                "error": "duckduckgo-search library not installed. Run: pip install duckduckgo-search"
            }
        
        print(f"🔍 {self.name}: Searching for '{query[:100]}'...")
        
        try:
            # Run search in executor to avoid blocking
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                self._search_sync,
                query,
                region,
                safesearch
            )
            
            print(f"✅ {self.name}: Found {len(results)} result(s)")
            logger.info(f"{self.name} search returned {len(results)} results")
            
            return {
                "results": results,
                "total_count": len(results)
            }
        
        except Exception as e:
            print(f"❌ {self.name}: Search error: {e}")
            logger.error(f"{self.name} search error: {e}")
            return {"results": [], "error": str(e)}
    
    def _search_sync(self, query: str, region: str, safesearch: str) -> List[Dict[str, Any]]:
        """Synchronous search helper."""
        from duckduckgo_search import DDGS
        
        results = []
        
        with DDGS() as ddgs:
            search_results = ddgs.text(
                query,
                region=region,
                safesearch=safesearch,
                max_results=self.max_results
            )
            
            for result in search_results:
                results.append({
                    'title': result.get('title', ''),
                    'url': result.get('href', ''),
                    'snippet': result.get('body', ''),
                    'source': 'duckduckgo'
                })
        
        return results
    
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
        
        results = await self.search(query)
        
        if results.get("results"):
            print(f"✅ Found {len(results['results'])} result(s) for {nct_id}")
        else:
            print(f"ℹ️ No results for {nct_id} in {self.name}")
        
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
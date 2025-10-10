"""
External API clients for extended clinical trial research.
Integrates: Meilisearch, Swirl, OpenFDA, Health Canada, DuckDuckGo, SERP API.

All searches use title and authors from clinical trial data.
"""
import asyncio
import aiohttp
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from src.amp_llm.config import get_logger, get_config

logger = get_logger(__name__)
config = get_config()


@dataclass
class SearchConfig:
    """Configuration for API searches."""
    # API Keys (set via environment variables)
    serpapi_key: Optional[str] = None
    meilisearch_url: Optional[str] = "http://localhost:7700"
    meilisearch_key: Optional[str] = None
    swirl_url: Optional[str] = "http://localhost:8000"
    
    # Search parameters
    max_results: int = 10
    timeout: int = 15
    
    def __post_init__(self):
        """Load from environment if available."""
        import os
        self.serpapi_key = self.serpapi_key or os.getenv('SERPAPI_KEY')
        self.meilisearch_key = self.meilisearch_key or os.getenv('MEILISEARCH_KEY')


class MeilisearchClient:
    """Meilisearch API client for semantic search."""
    
    def __init__(self, config: SearchConfig):
        self.config = config
        self.base_url = config.meilisearch_url
        self.headers = {}
        if config.meilisearch_key:
            self.headers['Authorization'] = f'Bearer {config.meilisearch_key}'
    
    async def search(self, title: str, authors: List[str], index: str = "clinical_trials") -> Dict[str, Any]:
        """
        Search Meilisearch index.
        
        Args:
            title: Study title
            authors: List of author names
            index: Index name to search
            
        Returns:
            Search results
        """
        print(f"🔍 Meilisearch: Searching index '{index}'...")
        
        # Build query from title and authors
        query = f"{title} {' '.join(authors)}"
        
        url = f"{self.base_url}/indexes/{index}/search"
        
        payload = {
            "q": query,
            "limit": self.config.max_results,
            "attributesToRetrieve": ["*"],
            "attributesToHighlight": ["title", "abstract", "authors"]
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=self.config.timeout)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        hits = len(data.get('hits', []))
                        print(f"✅ Meilisearch: Found {hits} result(s)")
                        logger.info(f"Meilisearch returned {hits} results")
                        return data
                    else:
                        error_text = await resp.text()
                        print(f"⚠️ Meilisearch: Error {resp.status}")
                        logger.warning(f"Meilisearch error {resp.status}: {error_text}")
                        return {"hits": [], "error": error_text}
        
        except asyncio.TimeoutError:
            print(f"⚠️ Meilisearch: Request timed out")
            logger.warning("Meilisearch timeout")
            return {"hits": [], "error": "timeout"}
        except Exception as e:
            print(f"❌ Meilisearch: {e}")
            logger.error(f"Meilisearch error: {e}")
            return {"hits": [], "error": str(e)}


class SwirlClient:
    """Swirl metasearch API client."""
    
    def __init__(self, config: SearchConfig):
        self.config = config
        self.base_url = config.swirl_url
    
    async def search(self, title: str, authors: List[str]) -> Dict[str, Any]:
        """
        Search via Swirl metasearch.
        
        Args:
            title: Study title
            authors: List of author names
            
        Returns:
            Aggregated search results
        """
        print(f"🔍 Swirl: Running metasearch...")
        
        # Build query
        query = f"{title} {' '.join(authors[:3])}"  # Limit to first 3 authors
        
        url = f"{self.base_url}/api/search"
        
        payload = {
            "query": query,
            "providers": ["google", "pubmed", "arxiv"],  # Configurable
            "max_results": self.config.max_results
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.config.timeout)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        total = data.get('total_results', 0)
                        print(f"✅ Swirl: Found {total} result(s) across providers")
                        logger.info(f"Swirl returned {total} results")
                        return data
                    else:
                        error_text = await resp.text()
                        print(f"⚠️ Swirl: Error {resp.status}")
                        logger.warning(f"Swirl error {resp.status}: {error_text}")
                        return {"results": [], "error": error_text}
        
        except asyncio.TimeoutError:
            print(f"⚠️ Swirl: Request timed out")
            return {"results": [], "error": "timeout"}
        except Exception as e:
            print(f"❌ Swirl: {e}")
            logger.error(f"Swirl error: {e}")
            return {"results": [], "error": str(e)}


class OpenFDAClient:
    """OpenFDA Drug API client."""
    
    def __init__(self, config: SearchConfig):
        self.config = config
        self.base_url = "https://api.fda.gov/drug"
    
    async def search_drug_events(self, drug_name: str) -> Dict[str, Any]:
        """
        Search FDA adverse event reports for a drug.
        
        Args:
            drug_name: Drug/intervention name from trial
            
        Returns:
            Adverse event data
        """
        print(f"🔍 OpenFDA: Searching adverse events for '{drug_name}'...")
        
        # Clean drug name (remove dosage, formulation details)
        clean_name = drug_name.split(':')[-1].strip() if ':' in drug_name else drug_name
        clean_name = clean_name.split('(')[0].strip()
        
        url = f"{self.base_url}/event.json"
        
        params = {
            "search": f'patient.drug.medicinalproduct:"{clean_name}"',
            "limit": self.config.max_results
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=self.config.timeout)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results = data.get('results', [])
                        print(f"✅ OpenFDA: Found {len(results)} adverse event report(s)")
                        logger.info(f"OpenFDA returned {len(results)} events for {drug_name}")
                        return data
                    elif resp.status == 404:
                        print(f"ℹ️ OpenFDA: No adverse events found for '{drug_name}'")
                        return {"results": []}
                    else:
                        error_text = await resp.text()
                        print(f"⚠️ OpenFDA: Error {resp.status}")
                        logger.warning(f"OpenFDA error {resp.status}: {error_text}")
                        return {"results": [], "error": error_text}
        
        except asyncio.TimeoutError:
            print(f"⚠️ OpenFDA: Request timed out")
            return {"results": [], "error": "timeout"}
        except Exception as e:
            print(f"❌ OpenFDA: {e}")
            logger.error(f"OpenFDA error: {e}")
            return {"results": [], "error": str(e)}
    
    async def search_drug_labels(self, drug_name: str) -> Dict[str, Any]:
        """
        Search FDA drug labels.
        
        Args:
            drug_name: Drug/intervention name
            
        Returns:
            Label data
        """
        print(f"🔍 OpenFDA: Searching drug labels for '{drug_name}'...")
        
        clean_name = drug_name.split(':')[-1].strip() if ':' in drug_name else drug_name
        clean_name = clean_name.split('(')[0].strip()
        
        url = f"{self.base_url}/label.json"
        
        params = {
            "search": f'openfda.brand_name:"{clean_name}" OR openfda.generic_name:"{clean_name}"',
            "limit": 5
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=self.config.timeout)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results = data.get('results', [])
                        print(f"✅ OpenFDA: Found {len(results)} drug label(s)")
                        logger.info(f"OpenFDA returned {len(results)} labels for {drug_name}")
                        return data
                    elif resp.status == 404:
                        print(f"ℹ️ OpenFDA: No drug labels found for '{drug_name}'")
                        return {"results": []}
                    else:
                        print(f"⚠️ OpenFDA: Error {resp.status}")
                        return {"results": []}
        
        except Exception as e:
            print(f"❌ OpenFDA: {e}")
            return {"results": [], "error": str(e)}


class HealthCanadaClient:
    """Health Canada Clinical Trials Database API client."""
    
    def __init__(self, config: SearchConfig):
        self.config = config
        self.base_url = "https://health-products.canada.ca/api/clinical-trials"
    
    async def search(self, title: str, nct_id: str = None) -> Dict[str, Any]:
        """
        Search Health Canada clinical trials database.
        
        Args:
            title: Study title
            nct_id: NCT ID if available
            
        Returns:
            Canadian trial data
        """
        print(f"🔍 Health Canada: Searching clinical trials database...")
        
        # Build search query
        if nct_id:
            search_term = nct_id
        else:
            # Use key terms from title
            search_term = ' '.join(title.split()[:10])  # First 10 words
        
        url = f"{self.base_url}/search"
        
        params = {
            "term": search_term,
            "lang": "en",
            "limit": self.config.max_results
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=self.config.timeout)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results = data.get('results', [])
                        print(f"✅ Health Canada: Found {len(results)} trial(s)")
                        logger.info(f"Health Canada returned {len(results)} trials")
                        return data
                    else:
                        error_text = await resp.text()
                        print(f"⚠️ Health Canada: Error {resp.status}")
                        logger.warning(f"Health Canada error {resp.status}: {error_text}")
                        return {"results": [], "error": error_text}
        
        except asyncio.TimeoutError:
            print(f"⚠️ Health Canada: Request timed out")
            return {"results": [], "error": "timeout"}
        except Exception as e:
            print(f"❌ Health Canada: {e}")
            logger.error(f"Health Canada error: {e}")
            return {"results": [], "error": str(e)}


class DuckDuckGoClient:
    """DuckDuckGo search API client."""
    
    def __init__(self, config: SearchConfig):
        self.config = config
    
    async def search(self, title: str, authors: List[str]) -> Dict[str, Any]:
        """
        Search DuckDuckGo.
        
        Args:
            title: Study title
            authors: Author names
            
        Returns:
            Search results
        """
        print(f"🔍 DuckDuckGo: Searching web...")
        
        # Use duckduckgo-search library
        try:
            from duckduckgo_search import AsyncDDGS
            
            # Build query
            query = f"{title} {' '.join(authors[:2])}"
            
            async with AsyncDDGS() as ddgs:
                results = []
                async for result in ddgs.text(
                    query,
                    max_results=self.config.max_results
                ):
                    results.append(result)
                
                print(f"✅ DuckDuckGo: Found {len(results)} result(s)")
                logger.info(f"DuckDuckGo returned {len(results)} results")
                
                return {"results": results}
        
        except ImportError:
            print(f"⚠️ DuckDuckGo: duckduckgo-search not installed")
            print(f"   Install with: pip install duckduckgo-search")
            logger.warning("DuckDuckGo library not available")
            return {"results": [], "error": "library_not_installed"}
        
        except Exception as e:
            print(f"❌ DuckDuckGo: {e}")
            logger.error(f"DuckDuckGo error: {e}")
            return {"results": [], "error": str(e)}


class SERPAPIClient:
    """SERP API client for Google search results."""
    
    def __init__(self, config: SearchConfig):
        self.config = config
        self.api_key = config.serpapi_key
    
    async def search_google(self, title: str, authors: List[str]) -> Dict[str, Any]:
        """
        Search Google via SERP API.
        
        Args:
            title: Study title
            authors: Author names
            
        Returns:
            Google search results
        """
        if not self.api_key:
            print(f"⚠️ SERP API: API key not configured")
            print(f"   Set SERPAPI_KEY environment variable")
            return {"organic_results": [], "error": "no_api_key"}
        
        print(f"🔍 SERP API: Searching Google...")
        
        # Build query
        query = f'"{title}" {" ".join(authors[:2])}'
        
        url = "https://serpapi.com/search"
        
        params = {
            "q": query,
            "api_key": self.api_key,
            "engine": "google",
            "num": self.config.max_results,
            "hl": "en"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=self.config.timeout)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results = data.get('organic_results', [])
                        print(f"✅ SERP API: Found {len(results)} result(s)")
                        logger.info(f"SERP API returned {len(results)} results")
                        return data
                    else:
                        error_text = await resp.text()
                        print(f"⚠️ SERP API: Error {resp.status}")
                        logger.warning(f"SERP API error {resp.status}: {error_text}")
                        return {"organic_results": [], "error": error_text}
        
        except asyncio.TimeoutError:
            print(f"⚠️ SERP API: Request timed out")
            return {"organic_results": [], "error": "timeout"}
        except Exception as e:
            print(f"❌ SERP API: {e}")
            logger.error(f"SERP API error: {e}")
            return {"organic_results": [], "error": str(e)}
    
    async def search_google_scholar(self, title: str, authors: List[str]) -> Dict[str, Any]:
        """
        Search Google Scholar via SERP API.
        
        Args:
            title: Study title
            authors: Author names
            
        Returns:
            Scholar search results
        """
        if not self.api_key:
            print(f"⚠️ SERP API: API key not configured for Scholar")
            return {"organic_results": [], "error": "no_api_key"}
        
        print(f"🔍 SERP API: Searching Google Scholar...")
        
        # Build academic query
        query = f'"{title}"'
        if authors:
            query += f' author:"{authors[0]}"'
        
        url = "https://serpapi.com/search"
        
        params = {
            "q": query,
            "api_key": self.api_key,
            "engine": "google_scholar",
            "num": self.config.max_results
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=self.config.timeout)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results = data.get('organic_results', [])
                        print(f"✅ SERP API Scholar: Found {len(results)} result(s)")
                        logger.info(f"SERP API Scholar returned {len(results)} results")
                        return data
                    else:
                        print(f"⚠️ SERP API Scholar: Error {resp.status}")
                        return {"organic_results": []}
        
        except Exception as e:
            print(f"❌ SERP API Scholar: {e}")
            return {"organic_results": [], "error": str(e)}


# ==============================================================================
# UNIFIED API MANAGER
# ==============================================================================

class APIManager:
    """Manages all external API clients."""
    
    def __init__(self, config: Optional[SearchConfig] = None):
        self.config = config or SearchConfig()
        
        # Initialize clients
        self.meilisearch = MeilisearchClient(self.config)
        self.swirl = SwirlClient(self.config)
        self.openfda = OpenFDAClient(self.config)
        self.health_canada = HealthCanadaClient(self.config)
        self.duckduckgo = DuckDuckGoClient(self.config)
        self.serpapi = SERPAPIClient(self.config)
    
    async def search_all(
        self,
        title: str,
        authors: List[str],
        nct_id: str = None,
        interventions: List[str] = None,
        enabled_apis: List[str] = None
    ) -> Dict[str, Any]:
        """
        Search across all enabled APIs concurrently.
        
        Args:
            title: Study title
            authors: Author names
            nct_id: NCT ID
            interventions: Drug/intervention names
            enabled_apis: List of APIs to use (None = all)
            
        Returns:
            Combined results from all APIs
        """
        if enabled_apis is None:
            enabled_apis = [
                'meilisearch', 'swirl', 'openfda', 
                'health_canada', 'duckduckgo', 'serpapi'
            ]
        
        print(f"\n{'='*60}")
        print(f"🔎 Extended API Search")
        print(f"{'='*60}\n")
        
        # Build task list
        tasks = []
        task_names = []
        
        if 'meilisearch' in enabled_apis:
            tasks.append(self.meilisearch.search(title, authors))
            task_names.append('meilisearch')
        
        if 'swirl' in enabled_apis:
            tasks.append(self.swirl.search(title, authors))
            task_names.append('swirl')
        
        if 'openfda' in enabled_apis and interventions:
            # Search for each intervention
            for intervention in interventions[:3]:  # Limit to first 3
                tasks.append(self.openfda.search_drug_events(intervention))
                task_names.append(f'openfda_events_{intervention}')
                tasks.append(self.openfda.search_drug_labels(intervention))
                task_names.append(f'openfda_labels_{intervention}')
        
        if 'health_canada' in enabled_apis:
            tasks.append(self.health_canada.search(title, nct_id))
            task_names.append('health_canada')
        
        if 'duckduckgo' in enabled_apis:
            tasks.append(self.duckduckgo.search(title, authors))
            task_names.append('duckduckgo')
        
        if 'serpapi' in enabled_apis:
            tasks.append(self.serpapi.search_google(title, authors))
            task_names.append('serpapi_google')
            tasks.append(self.serpapi.search_google_scholar(title, authors))
            task_names.append('serpapi_scholar')
        
        # Execute all searches concurrently
        print(f"🚀 Running {len(tasks)} API search(es) concurrently...\n")
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Combine results
        combined = {}
        for name, result in zip(task_names, results):
            if isinstance(result, Exception):
                logger.error(f"{name} failed: {result}")
                combined[name] = {"error": str(result)}
            else:
                combined[name] = result
        
        print(f"\n{'='*60}")
        print(f"✅ Extended search complete")
        print(f"{'='*60}\n")
        
        return combined
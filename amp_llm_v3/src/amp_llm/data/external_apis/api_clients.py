"""
Unified API Manager - orchestrates all external API clients.
FIXED: Correct import paths from api_clients.extended
"""
import asyncio
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import os

from amp_llm.config import get_logger
from amp_llm.cli.async_io import aprint

logger = get_logger(__name__)


@dataclass
class SearchConfig:
    """Configuration for API searches."""
    # API Keys
    serpapi_key: Optional[str] = None
    meilisearch_url: Optional[str] = "http://localhost:7700"
    meilisearch_key: Optional[str] = None
    swirl_url: Optional[str] = "http://localhost:9000"
    semantic_scholar_key: Optional[str] = None
    
    # Search parameters
    max_results: int = 10
    timeout: int = 30
    
    def __post_init__(self):
        """Load from environment if available."""
        self.serpapi_key = self.serpapi_key or os.getenv('SERPAPI_KEY')
        self.meilisearch_key = self.meilisearch_key or os.getenv('MEILISEARCH_KEY')
        self.semantic_scholar_key = self.semantic_scholar_key or os.getenv('SEMANTIC_SCHOLAR_API_KEY')


class APIManager:
    """
    Manages all external API clients.
    Delegates to individual client implementations.
    """
    
    def __init__(self, config: Optional[SearchConfig] = None):
        self.config = config or SearchConfig()
        self._clients = {}
        self._initialize_clients()
    
    def _initialize_clients(self):
        """Lazy initialization of API clients."""
        # FIXED: Import from correct location - api_clients.extended
        from amp_llm.data.api_clients.extended.pmc_fulltext import PMCFullTextClient
        from amp_llm.data.api_clients.extended.eudract import EudraCTClient
        from amp_llm.data.api_clients.extended.who_ictrp import WHOICTRPClient
        from amp_llm.data.api_clients.extended.semantic_scholar import SemanticScholarClient
        from amp_llm.data.api_clients.extended.duckduckgo import DuckDuckGoClient
        from amp_llm.data.api_clients.extended.serpapi import SerpAPIClient
        from amp_llm.data.api_clients.extended.openfda import OpenFDAClient
        from amp_llm.data.api_clients.extended.uniprot import UniProtClient
        
        self._clients['pmc_fulltext'] = PMCFullTextClient(
            timeout=self.config.timeout,
            max_results=self.config.max_results
        )
        
        self._clients['eudract'] = EudraCTClient(
            timeout=self.config.timeout,
            max_results=self.config.max_results
        )
        
        self._clients['who_ictrp'] = WHOICTRPClient(
            timeout=self.config.timeout,
            max_results=self.config.max_results
        )
        
        self._clients['semantic_scholar'] = SemanticScholarClient(
            api_key=self.config.semantic_scholar_key,
            timeout=self.config.timeout,
            max_results=self.config.max_results
        )
        
        self._clients['duckduckgo'] = DuckDuckGoClient(
            timeout=self.config.timeout,
            max_results=self.config.max_results
        )
        
        self._clients['serpapi'] = SerpAPIClient(
            api_key=self.config.serpapi_key,
            timeout=self.config.timeout,
            max_results=self.config.max_results
        )

        self._clients['openfda'] = OpenFDAClient(
            timeout=self.config.timeout,
            max_results=self.config.max_results
        )

        self._clients['uniprot'] = UniProtClient(
            timeout=self.config.timeout,
            max_results=self.config.max_results
        )
    
    async def search_all(
        self,
        title: str,
        authors: List[str],
        nct_id: str = None,
        interventions: List[str] = None,
        conditions: List[str] = None,
        enabled_apis: List[str] = None
    ) -> Dict[str, Any]:
        """
        Search across all enabled APIs concurrently.
        
        Args:
            title: Study title
            authors: Author names
            nct_id: NCT ID
            interventions: Drug/intervention names
            conditions: Medical conditions
            enabled_apis: List of APIs to use (None = all)
            
        Returns:
            Combined results from all APIs
        """
        if enabled_apis is None:
            enabled_apis = list(self._clients.keys())
        
        await aprint(f"\n{'='*60}")
        await aprint(f"🔎 Extended API Search")
        await aprint(f"{'='*60}\n")
        
        # Build task list
        tasks = []
        task_names = []
        
        # PMC Full Text
        if 'pmc_fulltext' in enabled_apis:
            tasks.append(
                self._clients['pmc_fulltext'].search_by_clinical_trial(nct_id, title)
            )
            task_names.append('pmc_fulltext')
        
        # EudraCT
        if 'eudract' in enabled_apis and nct_id:
            tasks.append(
                self._clients['eudract'].search_by_nct(nct_id)
            )
            task_names.append('eudract')
        
        # WHO ICTRP
        if 'who_ictrp' in enabled_apis and nct_id:
            tasks.append(
                self._clients['who_ictrp'].search_by_nct(nct_id)
            )
            task_names.append('who_ictrp')
        
        # Semantic Scholar
        if 'semantic_scholar' in enabled_apis:
            condition = conditions[0] if conditions else None
            tasks.append(
                self._clients['semantic_scholar'].search_by_clinical_trial(
                    nct_id, title, condition
                )
            )
            task_names.append('semantic_scholar')
        
        # DuckDuckGo
        if 'duckduckgo' in enabled_apis:
            condition = conditions[0] if conditions else None
            tasks.append(
                self._clients['duckduckgo'].search_by_clinical_trial(
                    nct_id, title, condition
                )
            )
            task_names.append('duckduckgo')
        
        # Google (SerpAPI)
        if 'serpapi' in enabled_apis:
            condition = conditions[0] if conditions else None
            tasks.append(
                self._clients['serpapi'].search_by_clinical_trial(
                    nct_id, title, condition
                )
            )
            task_names.append('serpapi')

        # OpenFDA
        if 'openfda' in enabled_apis:
            condition = conditions[0] if conditions else None
            tasks.append(
                self._clients['openfda'].search_by_clinical_trial(
                    interventions
                )
            )
            task_names.append('openfda')

        # UniProt
        if 'uniprot' in enabled_apis:
            condition = conditions[0] if conditions else None
            tasks.append(
                self._clients['uniprot'].search_by_clinical_trial(
                    interventions
                )
            )
            task_names.append('uniprot')
        
        # Execute all searches concurrently
        await aprint(f"🚀 Running {len(tasks)} API search(es) concurrently...\n")
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Combine results
        combined = {}
        for name, result in zip(task_names, results):
            if isinstance(result, Exception):
                logger.error(f"{name} failed: {result}")
                combined[name] = {"error": str(result)}
            else:
                combined[name] = result
        
        await aprint(f"\n{'='*60}")
        await aprint(f"✅ Extended search complete")
        await aprint(f"{'='*60}\n")
        
        return combined
    
    def get_available_apis(self) -> List[str]:
        """Get list of all available APIs."""
        return list(self._clients.keys())
    
    def get_api_info(self) -> Dict[str, Dict[str, str]]:
        """Get information about each API."""
        return {
            'pmc_fulltext': {
                'name': 'PubMed Central Full Text',
                'type': 'Literature',
                'cost': 'Free',
                'auth': 'None'
            },
            'eudract': {
                'name': 'EudraCT',
                'type': 'Clinical Database (Europe)',
                'cost': 'Free',
                'auth': 'None'
            },
            'who_ictrp': {
                'name': 'WHO ICTRP',
                'type': 'Clinical Database (International)',
                'cost': 'Free',
                'auth': 'None'
            },
            'semantic_scholar': {
                'name': 'Semantic Scholar',
                'type': 'Literature (AI-Powered)',
                'cost': 'Free',
                'auth': 'Optional API Key'
            },
            'duckduckgo': {
                'name': 'DuckDuckGo',
                'type': 'Web Search',
                'cost': 'Free',
                'auth': 'None'
            },
            'serpapi': {
                'name': 'Google (SerpAPI)',
                'type': 'Web Search',
                'cost': 'Free tier: 100/month',
                'auth': 'API Key Required'
            }
            ,
            'openfda': {
                'name': 'OpenFDA',
                'type': 'FDA Drug Database',
                'cost': 'Free',
                'auth': 'None'
            }
            ,
            'uniprot': {
                'name': 'UniProt',
                'type': 'Sequence Database',
                'cost': 'Free',
                'auth': 'None'
            }
        }
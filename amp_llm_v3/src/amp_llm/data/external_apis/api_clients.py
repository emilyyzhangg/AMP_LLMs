"""
External API clients for extended clinical trial research.
Integrates all available APIs for comprehensive research.

UPDATED: Added PMC Full Text, EudraCT, WHO ICTRP, Semantic Scholar
"""
import asyncio
import aiohttp
import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from amp_llm.config import get_logger
from amp_llm.data.external_apis.pmc_fulltext import PMCFullTextClient
from amp_llm.data.external_apis.eudract import EudraCTClient
from amp_llm.data.external_apis.who_ictrp import WHOICTRPClient
from amp_llm.data.external_apis.semantic_scholar import SemanticScholarClient

logger = get_logger(__name__)


@dataclass
class SearchConfig:
    """Configuration for API searches."""
    # API Keys
    serpapi_key: Optional[str] = None
    meilisearch_url: Optional[str] = "http://localhost:7700"
    meilisearch_key: Optional[str] = None
    swirl_url: Optional[str] = "http://localhost:8000"
    semantic_scholar_key: Optional[str] = None
    
    # Search parameters
    max_results: int = 10
    timeout: int = 30  # Increased for international APIs
    
    def __post_init__(self):
        """Load from environment if available."""
        self.serpapi_key = self.serpapi_key or os.getenv('SERPAPI_KEY')
        self.meilisearch_key = self.meilisearch_key or os.getenv('MEILISEARCH_KEY')
        self.semantic_scholar_key = self.semantic_scholar_key or os.getenv('SEMANTIC_SCHOLAR_API_KEY')


# Import existing clients (keeping for backward compatibility)
from amp_llm.data.api_clients_original import (
    MeilisearchClient,
    SwirlClient,
    OpenFDAClient,
    HealthCanadaClient,
    DuckDuckGoClient,
    SERPAPIClient
)


class APIManager:
    """
    Manages all external API clients.
    
    Now includes:
    - Original APIs: Meilisearch, Swirl, OpenFDA, Health Canada, DuckDuckGo, SERP API
    - New APIs: PMC Full Text, EudraCT, WHO ICTRP, Semantic Scholar
    """
    
    def __init__(self, config: Optional[SearchConfig] = None):
        self.config = config or SearchConfig()
        
        # Initialize original clients
        self.meilisearch = MeilisearchClient(self.config)
        self.swirl = SwirlClient(self.config)
        self.openfda = OpenFDAClient(self.config)
        self.health_canada = HealthCanadaClient(self.config)
        self.duckduckgo = DuckDuckGoClient(self.config)
        self.serpapi = SERPAPIClient(self.config)
        
        # Initialize new clients
        self.pmc_fulltext = PMCFullTextClient(
            timeout=self.config.timeout,
            max_results=self.config.max_results
        )
        self.eudract = EudraCTClient(
            timeout=self.config.timeout,
            max_results=self.config.max_results
        )
        self.who_ictrp = WHOICTRPClient(
            timeout=self.config.timeout,
            max_results=self.config.max_results
        )
        self.semantic_scholar = SemanticScholarClient(
            api_key=self.config.semantic_scholar_key,
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
            enabled_apis = [
                'meilisearch', 'swirl', 'openfda', 'health_canada',
                'duckduckgo', 'serpapi', 'pmc_fulltext', 'eudract',
                'who_ictrp', 'semantic_scholar'
            ]
        
        print(f"\n{'='*60}")
        print(f"🔎 Extended API Search")
        print(f"{'='*60}\n")
        
        # Build task list
        tasks = []
        task_names = []
        
        # Original APIs
        if 'meilisearch' in enabled_apis:
            tasks.append(self.meilisearch.search(title, authors))
            task_names.append('meilisearch')
        
        if 'swirl' in enabled_apis:
            tasks.append(self.swirl.search(title, authors))
            task_names.append('swirl')
        
        if 'openfda' in enabled_apis and interventions:
            for intervention in interventions[:3]:
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
        
        # New APIs
        if 'pmc_fulltext' in enabled_apis:
            tasks.append(self.pmc_fulltext.search_by_clinical_trial(nct_id, title))
            task_names.append('pmc_fulltext')
        
        if 'eudract' in enabled_apis and nct_id:
            tasks.append(self.eudract.search_by_nct(nct_id))
            task_names.append('eudract')
        
        if 'who_ictrp' in enabled_apis and nct_id:
            tasks.append(self.who_ictrp.search_by_nct(nct_id))
            task_names.append('who_ictrp')
        
        if 'semantic_scholar' in enabled_apis:
            condition = conditions[0] if conditions else None
            tasks.append(
                self.semantic_scholar.search_by_clinical_trial(
                    nct_id, title, condition
                )
            )
            task_names.append('semantic_scholar')
        
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
    
    async def search_comprehensive(
        self,
        nct_id: str,
        title: str,
        authors: List[str],
        interventions: List[str] = None,
        conditions: List[str] = None
    ) -> Dict[str, Any]:
        """
        Comprehensive search using all available APIs.
        Best for thorough research.
        
        Args:
            nct_id: NCT number
            title: Study title
            authors: Author names
            interventions: Drug/intervention names
            conditions: Medical conditions
            
        Returns:
            Organized results from all APIs
        """
        print(f"\n{'='*70}")
        print(f"🔬 COMPREHENSIVE SEARCH: {nct_id}")
        print(f"{'='*70}\n")
        
        # Search all APIs
        all_results = await self.search_all(
            title=title,
            authors=authors,
            nct_id=nct_id,
            interventions=interventions,
            conditions=conditions,
            enabled_apis=None  # Use all
        )
        
        # Organize by category
        organized = {
            "web_search": {},
            "clinical_databases": {},
            "literature": {},
            "drug_safety": {}
        }
        
        # Categorize results
        if 'duckduckgo' in all_results:
            organized['web_search']['duckduckgo'] = all_results['duckduckgo']
        
        if 'serpapi_google' in all_results:
            organized['web_search']['google'] = all_results['serpapi_google']
        
        if 'eudract' in all_results:
            organized['clinical_databases']['eudract'] = all_results['eudract']
        
        if 'who_ictrp' in all_results:
            organized['clinical_databases']['who_ictrp'] = all_results['who_ictrp']
        
        if 'health_canada' in all_results:
            organized['clinical_databases']['health_canada'] = all_results['health_canada']
        
        if 'pmc_fulltext' in all_results:
            organized['literature']['pmc_fulltext'] = all_results['pmc_fulltext']
        
        if 'semantic_scholar' in all_results:
            organized['literature']['semantic_scholar'] = all_results['semantic_scholar']
        
        if 'serpapi_scholar' in all_results:
            organized['literature']['google_scholar'] = all_results['serpapi_scholar']
        
        # OpenFDA results
        openfda_results = {
            k: v for k, v in all_results.items()
            if k.startswith('openfda_')
        }
        if openfda_results:
            organized['drug_safety']['openfda'] = openfda_results
        
        # Print summary
        self._print_comprehensive_summary(organized)
        
        return organized
    
    def _print_comprehensive_summary(self, organized: Dict[str, Any]):
        """Print organized summary of comprehensive search."""
        print(f"\n{'='*70}")
        print(f"📊 COMPREHENSIVE SEARCH SUMMARY")
        print(f"{'='*70}\n")
        
        # Web Search
        if organized['web_search']:
            print("🌐 Web Search Results:")
            for api, data in organized['web_search'].items():
                if 'error' not in data:
                    count = len(data.get('results', data.get('organic_results', [])))
                    print(f"   {api}: {count} result(s)")
            print()
        
        # Clinical Databases
        if organized['clinical_databases']:
            print("🏥 Clinical Trial Databases:")
            for api, data in organized['clinical_databases'].items():
                if 'error' not in data:
                    count = len(data.get('results', []))
                    print(f"   {api}: {count} trial(s)")
            print()
        
        # Literature
        if organized['literature']:
            print("📚 Academic Literature:")
            for api, data in organized['literature'].items():
                if 'error' not in data:
                    if 'papers' in data:
                        count = len(data['papers'])
                    elif 'pmcids' in data:
                        count = len(data['pmcids'])
                    else:
                        count = len(data.get('results', data.get('organic_results', [])))
                    print(f"   {api}: {count} paper(s)")
            print()
        
        # Drug Safety
        if organized['drug_safety']:
            print("💊 Drug Safety Information:")
            for api, data in organized['drug_safety'].items():
                if isinstance(data, dict):
                    total_events = sum(
                        len(v.get('results', []))
                        for v in data.values()
                        if isinstance(v, dict)
                    )
                    print(f"   {api}: {total_events} report(s)")
            print()
        
        print("="*70 + "\n")
    
    def get_available_apis(self) -> List[str]:
        """Get list of all available APIs."""
        return [
            'meilisearch', 'swirl', 'openfda', 'health_canada',
            'duckduckgo', 'serpapi', 'pmc_fulltext', 'eudract',
            'who_ictrp', 'semantic_scholar'
        ]
    
    def get_api_info(self) -> Dict[str, Dict[str, str]]:
        """Get information about each API."""
        return {
            'duckduckgo': {
                'name': 'DuckDuckGo',
                'type': 'Web Search',
                'cost': 'Free',
                'auth': 'None'
            },
            'serpapi': {
                'name': 'SERP API',
                'type': 'Google Search',
                'cost': 'Paid (100 free/month)',
                'auth': 'API Key'
            },
            'openfda': {
                'name': 'OpenFDA',
                'type': 'Drug Safety',
                'cost': 'Free',
                'auth': 'None'
            },
            'health_canada': {
                'name': 'Health Canada',
                'type': 'Clinical Database',
                'cost': 'Free',
                'auth': 'None'
            },
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
            'meilisearch': {
                'name': 'Meilisearch',
                'type': 'Custom Search',
                'cost': 'Self-Hosted',
                'auth': 'Optional'
            },
            'swirl': {
                'name': 'Swirl',
                'type': 'Metasearch',
                'cost': 'Self-Hosted',
                'auth': 'None'
            }
        }
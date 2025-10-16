"""
Unified API client manager.
Replaces both fetchers/coordinator.py and external_apis/api_clients.py
"""
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from amp_llm.config import get_logger
from amp_llm.data.api_clients.base import APIConfig

logger = get_logger(__name__)


@dataclass
class FetchConfig:
    """Configuration for data fetching."""
    use_extended_apis: bool = False
    enabled_apis: Optional[List[str]] = None
    api_config: Optional[APIConfig] = None


class UnifiedAPIManager:
    """
    Manages all API clients (core + extended).
    
    Replaces:
    - data/clinical_trials/fetchers/coordinator.py
    - data/external_apis/api_clients.py
    """
    
    def __init__(self, config: Optional[FetchConfig] = None):
        self.config = config or FetchConfig()
        self.api_config = self.config.api_config or APIConfig()
        
        self._core_clients = {}
        self._extended_clients = {}
        
        self._init_core_clients()
        
        if self.config.use_extended_apis:
            self._init_extended_clients()
    
    def _init_core_clients(self):
        """Initialize core clients (always needed)."""
        from amp_llm.data.api_clients.core.clinical_trials import ClinicalTrialsClient
        from amp_llm.data.api_clients.core.pubmed import PubMedClient
        from amp_llm.data.api_clients.core.pmc_basic import PMCBasicClient
        
        self._core_clients['clinical_trials'] = ClinicalTrialsClient(self.api_config)
        self._core_clients['pubmed'] = PubMedClient(self.api_config)
        self._core_clients['pmc_basic'] = PMCBasicClient(self.api_config)
    
    def _init_extended_clients(self):
        """Initialize extended clients (optional)."""
        from amp_llm.data.api_clients.extended.pmc_fulltext import PMCFullTextClient
        from amp_llm.data.api_clients.extended.eudract import EudraCTClient
        from amp_llm.data.api_clients.extended.who_ictrp import WHOICTRPClient
        from amp_llm.data.api_clients.extended.semantic_scholar import SemanticScholarClient
        
        enabled = self.config.enabled_apis or ['pmc_fulltext', 'eudract', 'who_ictrp', 'semantic_scholar']
        
        if 'pmc_fulltext' in enabled:
            self._extended_clients['pmc_fulltext'] = PMCFullTextClient(self.api_config)
        
        if 'eudract' in enabled:
            self._extended_clients['eudract'] = EudraCTClient(self.api_config)
        
        if 'who_ictrp' in enabled:
            self._extended_clients['who_ictrp'] = WHOICTRPClient(self.api_config)
        
        if 'semantic_scholar' in enabled:
            self._extended_clients['semantic_scholar'] = SemanticScholarClient(self.api_config)
    
    async def fetch_core(self, nct_id: str) -> Dict[str, Any]:
        """
        Fetch core data (ClinicalTrials.gov + PubMed + PMC).
        
        Replaces: fetch_clinical_trial_and_pubmed_pmc()
        """
        import asyncio
        
        # Fetch clinical trial
        ct_data = await self._core_clients['clinical_trials'].fetch_by_id(nct_id)
        
        if 'error' in ct_data:
            return ct_data
        
        # Extract references
        references = self._extract_references(ct_data)
        
        # Search PubMed and PMC for each reference
        pubmed_tasks = []
        pmc_tasks = []
        
        for ref in references:
            title = ref.get('title', '')
            authors = ref.get('authors', [])
            
            # PubMed search
            pubmed_tasks.append(
                self._core_clients['pubmed'].search_by_title_authors(title, authors)
            )
            
            # PMC search
            pmc_tasks.append(
                self._core_clients['pmc_basic'].search(title)
            )
        
        # Execute concurrently
        pubmed_results = await asyncio.gather(*pubmed_tasks)
        pmc_results = await asyncio.gather(*pmc_tasks)
        
        # Fetch full metadata for found articles
        pubmed_data = []
        for pmid in pubmed_results:
            if pmid:
                data = await self._core_clients['pubmed'].fetch_by_id(pmid)
                pubmed_data.append(data)
        
        pmc_data = []
        for pmcids in pmc_results:
            for pmcid in pmcids:
                data = await self._core_clients['pmc_basic'].fetch_by_id(pmcid)
                pmc_data.append(data)
        
        return {
            "nct_id": nct_id,
            "sources": {
                "clinical_trials": ct_data,
                "pubmed": pubmed_data,
                "pmc": pmc_data
            }
        }
    
    async def fetch_extended(
        self,
        nct_id: str,
        core_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Fetch extended data from additional APIs.
        
        Args:
            nct_id: NCT number
            core_data: Result from fetch_core()
            
        Returns:
            Extended API results
        """
        import asyncio
        
        if not self._extended_clients:
            return {}
        
        tasks = {}
        
        # Extract search parameters
        params = self._extract_search_params(nct_id, core_data)
        
        # PMC Full Text
        if 'pmc_fulltext' in self._extended_clients:
            tasks['pmc_fulltext'] = self._extended_clients['pmc_fulltext'].search_by_clinical_trial(
                nct_id, params['title']
            )
        
        # EudraCT
        if 'eudract' in self._extended_clients:
            tasks['eudract'] = self._extended_clients['eudract'].search_by_nct(nct_id)
        
        # WHO ICTRP
        if 'who_ictrp' in self._extended_clients:
            tasks['who_ictrp'] = self._extended_clients['who_ictrp'].search_by_nct(nct_id)
        
        # Semantic Scholar
        if 'semantic_scholar' in self._extended_clients:
            tasks['semantic_scholar'] = self._extended_clients['semantic_scholar'].search_by_clinical_trial(
                nct_id, params['title'], params['condition']
            )
        
        # Execute concurrently
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        
        # Combine results
        extended = {}
        for (name, _), result in zip(tasks.items(), results):
            if isinstance(result, Exception):
                logger.error(f"{name} failed: {result}")
                extended[name] = {"error": str(result)}
            else:
                extended[name] = result
        
        return extended
    
    async def fetch_all(self, nct_id: str) -> Dict[str, Any]:
        """
        Fetch both core and extended data.
        
        Args:
            nct_id: NCT number
            
        Returns:
            Complete data from all sources
        """
        # Fetch core data
        core = await self.fetch_core(nct_id)
        
        if 'error' in core:
            return core
        
        # Fetch extended data if enabled
        if self.config.use_extended_apis:
            extended = await self.fetch_extended(nct_id, core)
            core['extended_apis'] = extended
        
        return core
    
    def _extract_references(self, ct_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract references from clinical trial data."""
        protocol = ct_data.get('protocolSection', {})
        refs = protocol.get('referencesModule', {}).get('referenceList', [])
        
        if not refs:
            # Fallback: use trial info
            title = protocol.get('identificationModule', {}).get('officialTitle', '')
            officials = protocol.get('contactsLocationsModule', {}).get('overallOfficials', [])
            authors = [o.get('name') for o in officials if o.get('name')]
            
            if title:
                refs = [{"title": title, "authors": authors}]
        
        return refs
    
    def _extract_search_params(
        self,
        nct_id: str,
        core_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Extract search parameters for extended APIs."""
        ct_data = core_data['sources']['clinical_trials']
        protocol = ct_data.get('protocolSection', {})
        
        ident = protocol.get('identificationModule', {})
        title = ident.get('officialTitle') or ident.get('briefTitle') or nct_id
        
        conditions = protocol.get('conditionsModule', {}).get('conditions', [])
        condition = conditions[0] if conditions else None
        
        return {
            'title': title,
            'condition': condition
        }
    
    async def close_all(self):
        """Close all client sessions."""
        for client in list(self._core_clients.values()) + list(self._extended_clients.values()):
            await client.close()
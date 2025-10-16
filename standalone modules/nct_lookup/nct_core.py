"""
NCT Core Search Engine
=====================

Core search orchestration logic for NCT lookup.
"""

import asyncio
import aiohttp
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
import os
import logging

from nct_clients import (
    ClinicalTrialsClient,
    PubMedClient,
    PMCClient,
    DuckDuckGoClient,
    SerpAPIClient,
    GoogleScholarClient,
    OpenFDAClient
)
from nct_models import SearchConfig

logger = logging.getLogger(__name__)


class NCTSearchEngine:
    """
    Core search engine orchestrating multi-database searches.
    """
    
    def __init__(self):
        self.clients = {}
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Load API keys from environment
        self.serpapi_key = os.getenv('SERPAPI_KEY')
        self.ncbi_key = os.getenv('NCBI_API_KEY')
        
        if not self.serpapi_key:
            logger.warning("SERPAPI_KEY not set - SERP API will be unavailable")
        if not self.ncbi_key:
            logger.warning("NCBI_API_KEY not set - using default rate limits")
    
    async def initialize(self):
        """Initialize search engine and clients."""
        # Create persistent session
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=60)
        )
        
        # Initialize core clients
        self.clients['clinicaltrials'] = ClinicalTrialsClient(self.session)
        self.clients['pubmed'] = PubMedClient(self.session, api_key=self.ncbi_key)
        self.clients['pmc'] = PMCClient(self.session, api_key=self.ncbi_key)
        
        # Initialize extended clients
        self.clients['duckduckgo'] = DuckDuckGoClient(self.session)
        self.clients['serpapi'] = SerpAPIClient(self.session, api_key=self.serpapi_key)
        self.clients['scholar'] = GoogleScholarClient(self.session, api_key=self.serpapi_key)
        self.clients['openfda'] = OpenFDAClient(self.session)
        
        logger.info("Search engine initialized with all clients")
    
    async def close(self):
        """Close session and cleanup."""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("Search engine session closed")
    
    async def search(
        self,
        nct_id: str,
        config: SearchConfig,
        status = None
    ) -> Dict[str, Any]:
        """
        Execute comprehensive search across databases.
        
        Args:
            nct_id: NCT number
            config: Search configuration
            status: Optional status object to update
            
        Returns:
            Complete search results
        """
        results = {
            "nct_id": nct_id,
            "timestamp": datetime.utcnow().isoformat(),
            "title": "",
            "status": "",
            "databases": {}
        }
        
        # Step 1: Fetch clinical trial data (required)
        if status:
            status.current_database = "clinicaltrials"
            status.progress = 10
        
        logger.info(f"Fetching ClinicalTrials.gov data for {nct_id}")
        ct_data = await self.clients['clinicaltrials'].fetch(nct_id)
        
        if "error" in ct_data:
            logger.error(f"Failed to fetch trial data: {ct_data['error']}")
            results["error"] = ct_data["error"]
            return results
        
        results["databases"]["clinicaltrials"] = ct_data
        
        # Extract metadata
        results["title"] = self._extract_title(ct_data)
        results["status"] = self._extract_status(ct_data)
        
        # Step 2: Search PubMed
        if status:
            status.current_database = "pubmed"
            status.progress = 30
            status.completed_databases.append("clinicaltrials")
        
        logger.info(f"Searching PubMed for {nct_id}")
        pubmed_data = await self._search_pubmed(nct_id, ct_data)
        results["databases"]["pubmed"] = pubmed_data
        
        # Step 3: Search PMC
        if status:
            status.current_database = "pmc"
            status.progress = 50
            status.completed_databases.append("pubmed")
        
        logger.info(f"Searching PMC for {nct_id}")
        pmc_data = await self._search_pmc(nct_id, ct_data)
        results["databases"]["pmc"] = pmc_data
        
        # Step 4: Extended searches (if enabled)
        if config.use_extended_apis:
            if status:
                status.completed_databases.append("pmc")
            
            extended_results = await self._search_extended(
                nct_id,
                ct_data,
                config,
                status
            )
            results["databases"].update(extended_results)
        
        if status:
            status.progress = 100
            status.current_database = None
        
        return results
    
    async def _search_pubmed(self, nct_id: str, ct_data: Dict) -> Dict[str, Any]:
        """Search PubMed for related articles."""
        try:
            # Extract references from trial
            references = self._extract_references(ct_data)
            
            results = {
                "pmids": [],
                "articles": [],
                "total_found": 0
            }
            
            # Search for each reference
            for ref in references:
                title = ref.get("title", "")
                authors = ref.get("authors", [])
                
                if not title:
                    continue
                
                pmid = await self.clients['pubmed'].search_by_title_authors(
                    title, authors
                )
                
                if pmid:
                    results["pmids"].append(pmid)
                    
                    # Fetch article metadata
                    article = await self.clients['pubmed'].fetch(pmid)
                    if article and "error" not in article:
                        results["articles"].append(article)
            
            results["total_found"] = len(results["pmids"])
            return results
            
        except Exception as e:
            logger.error(f"PubMed search error: {e}", exc_info=True)
            return {"error": str(e)}
    
    async def _search_pmc(self, nct_id: str, ct_data: Dict) -> Dict[str, Any]:
        """Search PMC for related articles."""
        try:
            title = self._extract_title(ct_data)
            
            results = {
                "pmcids": [],
                "articles": [],
                "total_found": 0
            }
            
            if not title:
                return results
            
            # Search PMC
            pmcids = await self.clients['pmc'].search(title, max_results=10)
            
            if pmcids:
                results["pmcids"] = pmcids
                
                # Fetch article metadata for each
                for pmcid in pmcids[:5]:  # Limit to 5 for performance
                    article = await self.clients['pmc'].fetch(pmcid)
                    if article and "error" not in article:
                        results["articles"].append(article)
            
            results["total_found"] = len(pmcids)
            return results
            
        except Exception as e:
            logger.error(f"PMC search error: {e}", exc_info=True)
            return {"error": str(e)}
    
    async def _search_extended(
        self,
        nct_id: str,
        ct_data: Dict,
        config: SearchConfig,
        status = None
    ) -> Dict[str, Any]:
        """Search extended databases concurrently."""
        # Determine which databases to search
        if config.enabled_databases:
            databases = config.enabled_databases
        else:
            databases = ["duckduckgo", "serpapi", "scholar", "openfda"]
        
        # Filter to available clients
        databases = [db for db in databases if db in self.clients]
        
        # Build search parameters
        title = self._extract_title(ct_data)
        condition = self._extract_condition(ct_data)
        intervention = self._extract_intervention(ct_data)
        
        # Create search tasks
        tasks = {}
        
        if "duckduckgo" in databases:
            tasks["duckduckgo"] = self.clients['duckduckgo'].search(
                nct_id, title, condition
            )
        
        if "serpapi" in databases and self.serpapi_key:
            tasks["serpapi"] = self.clients['serpapi'].search(
                nct_id, title, condition
            )
        
        if "scholar" in databases and self.serpapi_key:
            tasks["scholar"] = self.clients['scholar'].search(
                nct_id, title, condition
            )
        
        if "openfda" in databases:
            tasks["openfda"] = self.clients['openfda'].search(
                intervention or condition
            )
        
        # Execute concurrently
        logger.info(f"Executing {len(tasks)} extended searches")
        
        results = {}
        completed = 0
        
        for db_name, task in tasks.items():
            try:
                if status:
                    status.current_database = db_name
                    status.progress = 50 + int((completed / len(tasks)) * 40)
                
                result = await task
                results[db_name] = result
                
                if status:
                    status.completed_databases.append(db_name)
                
                completed += 1
                
            except Exception as e:
                logger.error(f"{db_name} search error: {e}", exc_info=True)
                results[db_name] = {"error": str(e)}
        
        return results
    
    # Helper methods for data extraction
    
    def _extract_title(self, ct_data: Dict) -> str:
        """Extract trial title from clinical trial data."""
        try:
            protocol = ct_data.get("protocolSection", {})
            ident = protocol.get("identificationModule", {})
            return (
                ident.get("officialTitle") or
                ident.get("briefTitle") or
                ""
            )
        except Exception:
            return ""
    
    def _extract_status(self, ct_data: Dict) -> str:
        """Extract trial status."""
        try:
            protocol = ct_data.get("protocolSection", {})
            status_mod = protocol.get("statusModule", {})
            return status_mod.get("overallStatus", "")
        except Exception:
            return ""
    
    def _extract_condition(self, ct_data: Dict) -> str:
        """Extract primary condition."""
        try:
            protocol = ct_data.get("protocolSection", {})
            cond_mod = protocol.get("conditionsModule", {})
            conditions = cond_mod.get("conditions", [])
            return conditions[0] if conditions else ""
        except Exception:
            return ""
    
    def _extract_intervention(self, ct_data: Dict) -> str:
        """Extract primary intervention."""
        try:
            protocol = ct_data.get("protocolSection", {})
            arms_int = protocol.get("armsInterventionsModule", {})
            interventions = arms_int.get("interventions", [])
            if interventions:
                return interventions[0].get("name", "")
            return ""
        except Exception:
            return ""
    
    def _extract_references(self, ct_data: Dict) -> List[Dict[str, Any]]:
        """Extract references from trial data."""
        try:
            protocol = ct_data.get("protocolSection", {})
            refs = protocol.get("referencesModule", {}).get("referenceList", [])
            
            if not refs:
                # Fallback: use trial title and investigators
                title = self._extract_title(ct_data)
                contacts = protocol.get("contactsLocationsModule", {})
                officials = contacts.get("overallOfficials", [])
                authors = [o.get("name") for o in officials if "name" in o]
                
                if title:
                    refs = [{"title": title, "authors": authors}]
            
            return refs
            
        except Exception:
            return []
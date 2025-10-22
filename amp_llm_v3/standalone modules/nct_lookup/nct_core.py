"""
NCT Core Search Engine
=====================

Core search orchestration logic matching the original workflow.
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
    PMCBioClient,
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
    Updated to match the original amp_llm workflow behavior.
    """
    
    def __init__(self):
        self.clients = {}
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Load API keys from environment
        self.serpapi_key = os.getenv('SERPAPI_KEY')
        self.ncbi_key = os.getenv('NCBI_API_KEY')
        
        if not self.serpapi_key:
            logger.warning("SERPAPI_KEY not set - Google/Scholar search unavailable")
        if not self.ncbi_key:
            logger.warning("NCBI_API_KEY not set - using default rate limits")
    
    async def initialize(self):
        """Initialize search engine and clients."""
        # Create persistent session with longer timeout
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=120, connect=30)
        )
        
        # Initialize core clients (always available)
        self.clients['clinicaltrials'] = ClinicalTrialsClient(self.session)
        self.clients['pubmed'] = PubMedClient(self.session, api_key=self.ncbi_key)
        self.clients['pmc'] = PMCClient(self.session, api_key=self.ncbi_key)
        self.clients['pmc_bioc'] = PMCBioClient(self.session, api_key=self.ncbi_key)
        
        # Initialize extended clients (optional)
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
        Execute comprehensive search matching original workflow.
        
        This follows the same pattern as fetch_clinical_trial_and_pubmed_pmc
        from the original amp_llm implementation.
        
        Args:
            nct_id: NCT number
            config: Search configuration
            status: Optional status object to update
            
        Returns:
            Complete search results in the same format as original
        """
        results = {
            "nct_id": nct_id,
            "timestamp": datetime.utcnow().isoformat(),
            "sources": {
                "clinical_trials": {},
                "pubmed": {},
                "pmc": {},
                "pmc_bioc": {}
            },
            "metadata": {
                "title": "",
                "status": "",
                "condition": "",
                "intervention": ""
            },
            # Include databases for backward compatibility with tests
            "databases": {}
        }
        
        # Step 1: Fetch ClinicalTrials.gov data (REQUIRED)
        if status:
            status.current_database = "clinicaltrials"
            status.progress = 10
        
        logger.info(f"Fetching ClinicalTrials.gov data for {nct_id}")
        ct_data = await self.clients['clinicaltrials'].fetch(nct_id)
        
        if "error" in ct_data:
            logger.error(f"Failed to fetch trial data: {ct_data['error']}")
            results["error"] = ct_data["error"]
            results["sources"]["clinical_trials"] = {
                "success": False,
                "error": ct_data["error"],
                "data": None
            }
            return results
        
        # Store clinical trial data
        results["sources"]["clinical_trials"] = {
            "success": True,
            "data": ct_data,
            "fetch_time": datetime.utcnow().isoformat()
        }
        
        # Extract metadata
        results["metadata"]["title"] = self._extract_title(ct_data)
        results["metadata"]["status"] = self._extract_status(ct_data)
        results["metadata"]["condition"] = self._extract_condition(ct_data)
        results["metadata"]["intervention"] = self._extract_intervention(ct_data)
        
        logger.info(f"Trial: {results['metadata']['title'][:100]}")
        
        # Step 2: Search PubMed
        if status:
            status.current_database = "pubmed"
            status.progress = 30
            status.completed_databases.append("clinicaltrials")
        
        logger.info(f"Searching PubMed for {nct_id}")
        try:
            pubmed_data = await self._search_pubmed(nct_id, ct_data)
            results["sources"]["pubmed"] = {
                "success": True,
                "data": pubmed_data,
                "fetch_time": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"PubMed search failed: {e}", exc_info=True)
            results["sources"]["pubmed"] = {
                "success": False,
                "error": str(e),
                "data": None
            }
        
        # Step 3: Search PMC
        if status:
            status.current_database = "pmc"
            status.progress = 50
            status.completed_databases.append("pubmed")
        
        logger.info(f"Searching PMC for {nct_id}")
        try:
            pmc_data = await self._search_pmc(nct_id, ct_data)
            results["sources"]["pmc"] = {
                "success": True,
                "data": pmc_data,
                "fetch_time": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"PMC search failed: {e}", exc_info=True)
            results["sources"]["pmc"] = {
                "success": False,
                "error": str(e),
                "data": None
            }
        
        # Step 4: Search PMC BioC
        if status:
            status.current_database = "pmc_bioc"
            status.progress = 60
            status.completed_databases.append("pmc")

        logger.info(f"Searching PMC BioC for {nct_id}")  # ← Should see this in logs
        try:
            pmc_bioc_data = await self._search_pmc_bioc(nct_id, ct_data, results)
            logger.info(f"PMC BioC returned: {pmc_bioc_data}")  # ← Add this to see what's returned
            results["sources"]["pmc_bioc"] = {
                "success": True,
                "data": pmc_bioc_data,
                "fetch_time": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"PMC BioC search failed: {e}", exc_info=True)
            results["sources"]["pmc_bioc"] = {
                "success": False,
                "error": str(e),
                "data": None
            }

        # Step 5: Extended searches (if enabled)
        if config.use_extended_apis:
            if status:
                status.completed_databases.append("pmc_bioc")
            
            logger.info("Starting extended database searches")
            extended_results = await self._search_extended(
                nct_id,
                ct_data,
                config,
                status
            )
            results["sources"]["extended"] = extended_results
        
        # Add backward compatibility: copy sources to databases
        results["databases"] = {
            "clinicaltrials": results["sources"]["clinical_trials"].get("data"),
            "pubmed": results["sources"]["pubmed"].get("data"),
            "pmc": results["sources"]["pmc"].get("data"),
            "pmc_bioc": results["sources"]["pmc_bioc"].get("data")
        }
        
        # Add extended to databases if present
        if "extended" in results["sources"]:
            for api_name, api_data in results["sources"]["extended"].items():
                results["databases"][api_name] = api_data.get("data")
        
        if status:
            status.progress = 100
            status.current_database = None
        
        logger.info(f"Search completed for {nct_id}")
        return results
    
    async def _search_pubmed(self, nct_id: str, ct_data: Dict) -> Dict[str, Any]:
        """
        Search PubMed matching original workflow logic.
        """
        try:
            # Extract references from trial data
            references = self._extract_references(ct_data)
            
            results = {
                "pmids": [],
                "articles": [],
                "total_found": 0,
                "search_strategy": "references",
                "search_queries": []
            }
            
            # Strategy 1: Search by references from ClinicalTrials.gov
            if references:
                logger.info(f"Searching PubMed using {len(references)} references")
                
                for ref in references[:5]:  # Limit to first 5 references
                    title = ref.get("title", "")
                    citation = ref.get("citation", "")
                    pmid = ref.get("pmid", "")
                    
                    # If we already have a PMID from reference, use it
                    if pmid and pmid not in results["pmids"]:
                        results["pmids"].append(pmid)
                        article = await self.clients['pubmed'].fetch(pmid)
                        if article and "error" not in article:
                            results["articles"].append(article)
                        continue
                    
                    # Search by title if available
                    if title or citation:
                        search_title = title or citation
                        authors = ref.get("authors", [])
                        
                        found_pmid = await self.clients['pubmed'].search_by_title_authors(
                            search_title, authors
                        )
                        
                        if found_pmid and found_pmid not in results["pmids"]:
                            results["pmids"].append(found_pmid)
                            article = await self.clients['pubmed'].fetch(found_pmid)
                            if article and "error" not in article:
                                results["articles"].append(article)
            
            # Strategy 2: Direct NCT ID search (if no references found)
            if len(results["pmids"]) == 0:
                logger.info(f"No references found, searching PubMed by NCT ID: {nct_id}")
                results["search_strategy"] = "nct_id"
                results["search_queries"].append(nct_id)
                
                pmids = await self.clients['pubmed'].search(nct_id, max_results=20)
                
                for pmid in pmids:
                    if pmid not in results["pmids"]:
                        results["pmids"].append(pmid)
                        
                        # Fetch metadata for first 10
                        if len(results["articles"]) < 10:
                            article = await self.clients['pubmed'].fetch(pmid)
                            if article and "error" not in article:
                                results["articles"].append(article)
            
            # Strategy 3: Search by trial title (if still no results)
            if len(results["pmids"]) == 0:
                title = self._extract_title(ct_data)
                if title:
                    logger.info(f"Searching PubMed by trial title")
                    results["search_strategy"] = "title"
                    # Use first 10 words of title
                    title_query = " ".join(title.split()[:10])
                    results["search_queries"].append(title_query)
                    
                    pmids = await self.clients['pubmed'].search(title_query, max_results=20)
                    
                    for pmid in pmids[:10]:
                        if pmid not in results["pmids"]:
                            results["pmids"].append(pmid)
                            article = await self.clients['pubmed'].fetch(pmid)
                            if article and "error" not in article:
                                results["articles"].append(article)
            
            results["total_found"] = len(results["pmids"])
            logger.info(f"PubMed search found {results['total_found']} results")
            return results
            
        except Exception as e:
            logger.error(f"PubMed search error: {e}", exc_info=True)
            return {"error": str(e)}
    
    async def _search_pmc(self, nct_id: str, ct_data: Dict) -> Dict[str, Any]:
        """
        Search PMC matching original workflow logic.
        """
        try:
            results = {
                "pmcids": [],
                "articles": [],
                "total_found": 0,
                "search_strategy": "nct_id",
                "search_queries": []
            }
            
            # Strategy 1: Search by NCT ID
            logger.info(f"Searching PMC by NCT ID: {nct_id}")
            results["search_queries"].append(nct_id)
            pmcids = await self.clients['pmc'].search(nct_id, max_results=20)
            
            # Strategy 2: If no results, try title search
            if not pmcids:
                title = self._extract_title(ct_data)
                if title:
                    logger.info(f"Searching PMC by trial title")
                    results["search_strategy"] = "title"
                    # Use first 10 words of title
                    title_query = " ".join(title.split()[:10])
                    results["search_queries"].append(title_query)
                    pmcids = await self.clients['pmc'].search(title_query, max_results=20)
            
            if pmcids:
                results["pmcids"] = pmcids
                
                # Fetch article metadata for first 10
                for pmcid in pmcids[:10]:
                    article = await self.clients['pmc'].fetch(pmcid)
                    if article and "error" not in article:
                        results["articles"].append(article)
            
            results["total_found"] = len(pmcids)
            logger.info(f"PMC search found {results['total_found']} results")
            return results
            
        except Exception as e:
            logger.error(f"PMC search error: {e}", exc_info=True)
            return {"error": str(e)}
        
    async def _search_pmc_bioc(
        self,
        nct_id: str,
        ct_data: Dict[str, Any],
        results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Fetch PMC BioC format for articles from Step 2 (PubMed) and Step 3 (PMC).
        Uses PMIDs returned by previous searches.
        
        Args:
            nct_id: NCT number
            ct_data: Clinical trial data
            results: Current results dict with PubMed and PMC data
            
        Returns:
            Dict containing BioC formatted articles
        """
        bioc_results = {
            "articles": [],
            "total_found": 0,
            "total_fetched": 0,
            "errors": [],
            "sources": {
                "pubmed": 0,
                "pmc": 0
            }
        }
        
        # Collect PMIDs from Step 2: PubMed search
        pmids = []
        if results["sources"]["pubmed"].get("success"):
            pubmed_data = results["sources"]["pubmed"].get("data", {})
            pubmed_pmids = pubmed_data.get("pmids", [])
            
            for pmid in pubmed_pmids:
                if pmid and pmid not in pmids:
                    pmids.append(pmid)
            
            bioc_results["sources"]["pubmed"] = len(pubmed_pmids)
            logger.info(f"Collected {len(pubmed_pmids)} PMIDs from PubMed search")
        
        # Collect PMIDs from Step 3: PMC search
        # PMC returns PMCIDs, but we can try to use them or extract PMIDs
        if results["sources"]["pmc"].get("success"):
            pmc_data = results["sources"]["pmc"].get("data", {})
            
            # Try to get PMIDs from PMC articles if available
            pmc_articles = pmc_data.get("articles", [])
            for article in pmc_articles:
                pmid = article.get("pmid")
                if pmid and pmid not in pmids:
                    pmids.append(pmid)
            
            # Also check if PMC returned PMCIDs that we can use
            pmcids = pmc_data.get("pmcids", [])
            for pmcid in pmcids:
                if pmcid and pmcid not in pmids:
                    pmids.append(pmcid)
            
            bioc_results["sources"]["pmc"] = len(pmc_articles) + len(pmcids)
            logger.info(f"Collected {len(pmc_articles) + len(pmcids)} IDs from PMC search")
        
        if not pmids:
            logger.warning(f"No PMIDs/PMCIDs found from PubMed or PMC searches for {nct_id}")
            return bioc_results
        
        bioc_results["total_found"] = len(pmids)
        logger.info(f"Fetching BioC data for {len(pmids)} total IDs from Steps 2 & 3")
        
        # Fetch BioC data for each PMID/PMCID
        for pmid in pmids:
            try:
                bioc_data = await self.clients['pmc_bioc'].fetch_pmc_bioc(
                    pmid,
                    format="json",
                    encoding="unicode"
                )
                
                if "error" not in bioc_data:
                    bioc_results["articles"].append({
                        "pmid": pmid,
                        "bioc_data": bioc_data
                    })
                    bioc_results["total_fetched"] += 1
                else:
                    # Article not in PMC Open Access
                    logger.debug(f"ID {pmid} not available in PMC OA: {bioc_data['error']}")
                    bioc_results["errors"].append({
                        "pmid": pmid,
                        "error": bioc_data["error"]
                    })
                    
            except Exception as e:
                logger.error(f"Error fetching BioC for ID {pmid}: {e}")
                bioc_results["errors"].append({
                    "pmid": pmid,
                    "error": str(e)
                })
        
        logger.info(f"BioC search complete: {bioc_results['total_fetched']}/{bioc_results['total_found']} articles fetched")
        return bioc_results
    
    async def _search_extended(
        self,
        nct_id: str,
        ct_data: Dict,
        config: SearchConfig,
        status = None
    ) -> Dict[str, Any]:
        """
        Search extended databases matching original API integration.
        """
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
        
        # Extract authors for Scholar search
        contacts = ct_data.get("protocolSection", {}).get("contactsLocationsModule", {})
        officials = contacts.get("overallOfficials", [])
        authors = [o.get("name", "") for o in officials if o.get("name")]
        
        logger.info(f"Extended search params - Title: {title[:50] if title else 'None'}, "
                   f"Condition: {condition}, Intervention: {intervention}")
        
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
            search_term = intervention or condition
            if search_term:
                tasks["openfda"] = self.clients['openfda'].search(search_term)
        
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
                results[db_name] = {
                    "success": "error" not in result,
                    "data": result,
                    "fetch_time": datetime.utcnow().isoformat()
                }
                
                if status:
                    status.completed_databases.append(db_name)
                
                completed += 1
                logger.info(f"Completed {db_name} search")
                
            except Exception as e:
                logger.error(f"{db_name} search error: {e}", exc_info=True)
                results[db_name] = {
                    "success": False,
                    "error": str(e),
                    "data": None
                }
        
        return results
    
    # Helper methods for safe data extraction from v2 API
    
    def _extract_title(self, ct_data: Dict) -> str:
        """Extract trial title from clinical trial v2 data."""
        try:
            protocol = ct_data.get("protocolSection", {})
            if not protocol:
                return ""
            
            ident = protocol.get("identificationModule", {})
            
            # Try officialTitle first, then briefTitle
            title = (
                ident.get("officialTitle") or
                ident.get("briefTitle") or
                ""
            )
            
            return title.strip()
            
        except Exception as e:
            logger.warning(f"Failed to extract title: {e}")
            return ""
    
    def _extract_status(self, ct_data: Dict) -> str:
        """Extract trial status."""
        try:
            protocol = ct_data.get("protocolSection", {})
            if not protocol:
                return ""
            
            status_mod = protocol.get("statusModule", {})
            return status_mod.get("overallStatus", "").strip()
            
        except Exception as e:
            logger.warning(f"Failed to extract status: {e}")
            return ""
    
    def _extract_condition(self, ct_data: Dict) -> str:
        """Extract primary condition."""
        try:
            protocol = ct_data.get("protocolSection", {})
            if not protocol:
                return ""
            
            cond_mod = protocol.get("conditionsModule", {})
            conditions = cond_mod.get("conditions", [])
            
            if conditions and isinstance(conditions, list):
                return conditions[0].strip()
            
            return ""
            
        except Exception as e:
            logger.warning(f"Failed to extract condition: {e}")
            return ""
    
    def _extract_intervention(self, ct_data: Dict) -> str:
        """Extract primary intervention."""
        try:
            protocol = ct_data.get("protocolSection", {})
            if not protocol:
                return ""
            
            arms_int = protocol.get("armsInterventionsModule", {})
            interventions = arms_int.get("interventions", [])
            
            if interventions and isinstance(interventions, list):
                first_int = interventions[0]
                if isinstance(first_int, dict):
                    return first_int.get("name", "").strip()
            
            return ""
            
        except Exception as e:
            logger.warning(f"Failed to extract intervention: {e}")
            return ""
    
    def _extract_references(self, ct_data: Dict) -> List[Dict[str, Any]]:
        """
        Extract references from trial data matching original logic.
        """
        try:
            protocol = ct_data.get("protocolSection", {})
            if not protocol:
                return []
            
            # Get references from referencesModule
            refs_mod = protocol.get("referencesModule", {})
            refs_list = refs_mod.get("references", [])
            
            parsed_refs = []
            
            for ref in refs_list:
                if isinstance(ref, dict):
                    # Extract all available info
                    parsed_ref = {
                        "pmid": ref.get("pmid", ""),
                        "citation": ref.get("citation", ""),
                        "title": "",
                        "authors": []
                    }
                    
                    # Try to extract title from citation
                    citation = ref.get("citation", "")
                    if citation:
                        # Simple heuristic: title is usually before the first period
                        parts = citation.split(".")
                        if parts:
                            parsed_ref["title"] = parts[0].strip()
                    
                    parsed_refs.append(parsed_ref)
            
            # If no references found, create synthetic reference from trial data
            if not parsed_refs:
                title = self._extract_title(ct_data)
                if title:
                    contacts = protocol.get("contactsLocationsModule", {})
                    officials = contacts.get("overallOfficials", [])
                    authors = [o.get("name", "") for o in officials if o.get("name")]
                    
                    parsed_refs.append({
                        "title": title,
                        "authors": authors,
                        "pmid": "",
                        "citation": ""
                    })
            
            logger.info(f"Extracted {len(parsed_refs)} references")
            return parsed_refs
            
        except Exception as e:
            logger.warning(f"Failed to extract references: {e}")
            return []
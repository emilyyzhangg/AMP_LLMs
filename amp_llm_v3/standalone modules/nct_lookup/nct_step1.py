"""
NCT Step 1: Core API Search
============================

Orchestrates Step 1 searches across core APIs with multiple search strategies.
Each API performs multiple targeted searches to maximize result coverage.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
import asyncio

logger = logging.getLogger(__name__)


class NCTStep1Searcher:
    """
    Manages Step 1 searches across core APIs.
    
    Core APIs:
    - Clinical Trials.gov
    - PubMed
    - PMC
    - PMC BioC
    
    Each API performs multiple searches with different strategies.
    """
    
    def __init__(self, clients: Dict[str, Any]):
        """
        Initialize Step 1 searcher.
        
        Args:
            clients: Dictionary of initialized API clients
        """
        self.clients = clients
    
    async def execute_step1(
        self,
        nct_id: str,
        status_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Execute complete Step 1 search workflow.
        
        Args:
            nct_id: NCT identifier
            status_callback: Optional callback for progress updates
        
        Returns:
            Complete Step 1 results with metadata and all core API results
        """
        logger.info(f"=" * 60)
        logger.info(f"STEP 1: Core API Search for {nct_id}")
        logger.info(f"=" * 60)
        
        results = {
            "nct_id": nct_id,
            "step": 1,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": {},
            "core_apis": {}
        }
        
        # Step 1.1: ClinicalTrials.gov (REQUIRED - foundation for other searches)
        if status_callback:
            status_callback("Searching ClinicalTrials.gov", 10)
        
        ct_results = await self._search_clinicaltrials(nct_id)
        results["core_apis"]["clinicaltrials"] = ct_results
        
        if "error" in ct_results:
            logger.error(f"ClinicalTrials.gov search failed: {ct_results['error']}")
            results["error"] = "Failed to fetch clinical trial data"
            return results
        
        # Extract metadata for subsequent searches
        ct_data = ct_results.get("data", {})
        results["metadata"] = self._extract_metadata(ct_data)
        
        logger.info(f"✓ ClinicalTrials.gov: {results['metadata'].get('title', 'No title')[:100]}")
        
        # Step 1.2: PubMed (multiple search strategies)
        if status_callback:
            status_callback("Searching PubMed", 30)
        
        pubmed_results = await self._search_pubmed(nct_id, ct_data)
        results["core_apis"]["pubmed"] = pubmed_results
        
        # Step 1.3: PMC (independent of PubMed)
        if status_callback:
            status_callback("Searching PMC", 60)
        
        pmc_results = await self._search_pmc(nct_id, ct_data)
        results["core_apis"]["pmc"] = pmc_results
        
        # Step 1.4: PMC BioC (using PMIDs from PubMed)
        if status_callback:
            status_callback("Fetching full-text from PMC BioC", 80)
        
        pmc_bioc_results = await self._search_pmc_bioc(nct_id, results)
        results["core_apis"]["pmc_bioc"] = pmc_bioc_results
        
        if status_callback:
            status_callback("Step 1 Complete", 100)
        
        # Generate summary
        results["summary"] = self._generate_summary(results)
        
        logger.info(f"=" * 60)
        logger.info(f"STEP 1 COMPLETE: {results['summary']['total_results']} total results")
        logger.info(f"=" * 60)
        
        return results
    
    async def _search_clinicaltrials(self, nct_id: str) -> Dict[str, Any]:
        """
        Search ClinicalTrials.gov by NCT ID.
        
        Single search strategy: Direct NCT lookup
        """
        logger.info(f"🔍 ClinicalTrials.gov: Fetching {nct_id}")
        
        searches = []
        
        try:
            search_record = {
                "search_type": "nct_id",
                "query": nct_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            data = await self.clients['clinicaltrials'].fetch(nct_id)
            
            if "error" in data:
                search_record["status"] = "error"
                search_record["error"] = data["error"]
                search_record["results_count"] = 0
                return {
                    "success": False,
                    "error": data["error"],
                    "searches": [search_record]
                }
            
            search_record["status"] = "success"
            search_record["results_count"] = 1
            search_record["data"] = data
            searches.append(search_record)
            
            logger.info(f"✓ ClinicalTrials.gov: Found trial data")
            
            return {
                "success": True,
                "searches": searches,
                "data": data,
                "total_results": 1
            }
            
        except Exception as e:
            logger.error(f"✗ ClinicalTrials.gov error: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "searches": searches
            }
    
    async def _search_pubmed(
        self,
        nct_id: str,
        ct_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Search PubMed with multiple strategies.
        
        Strategies (in order):
        1. References from ClinicalTrials.gov
        2. Direct NCT ID search
        3. Trial title search
        4. Author + title search (if available)
        """
        logger.info(f"🔍 PubMed: Multiple search strategies")
        
        searches = []
        pmids = set()
        articles = []
        
        try:
            # Strategy 1: Search by references
            references = self._extract_references(ct_data)
            if references:
                logger.info(f"  → Strategy 1: Searching {len(references)} references")
                
                for ref in references[:5]:  # Limit to first 5
                    search_record = {
                        "search_type": "reference",
                        "query": ref.get("title", ref.get("citation", "")),
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    
                    title = ref.get("title", "")
                    citation = ref.get("citation", "")
                    pmid = ref.get("pmid", "")
                    
                    if pmid:
                        pmids.add(pmid)
                        article = await self.clients['pubmed'].fetch(pmid)
                        if article and "error" not in article:
                            articles.append(article)
                        search_record["results_count"] = 1
                    elif title or citation:
                        search_title = title or citation
                        authors = ref.get("authors", [])
                        found_pmid = await self.clients['pubmed'].search_by_title_authors(
                            search_title, authors
                        )
                        if found_pmid:
                            pmids.add(found_pmid)
                            search_record["results_count"] = 1
                        else:
                            search_record["results_count"] = 0
                    
                    search_record["status"] = "success"
                    searches.append(search_record)
            
            # Strategy 2: Direct NCT ID search
            logger.info(f"  → Strategy 2: NCT ID search")
            search_record = {
                "search_type": "nct_id",
                "query": nct_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            nct_pmids = await self.clients['pubmed'].search(nct_id, max_results=20)
            new_pmids = [p for p in nct_pmids if p not in pmids]
            pmids.update(new_pmids)
            
            # Fetch metadata for new PMIDs
            for pmid in new_pmids[:10]:  # Limit to 10
                article = await self.clients['pubmed'].fetch(pmid)
                if article and "error" not in article:
                    articles.append(article)
            
            search_record["status"] = "success"
            search_record["results_count"] = len(new_pmids)
            searches.append(search_record)
            
            # Strategy 3: Title search (if still no results)
            if len(pmids) == 0:
                title = self._extract_title(ct_data)
                if title:
                    logger.info(f"  → Strategy 3: Title search")
                    search_record = {
                        "search_type": "title",
                        "query": " ".join(title.split()[:10]),  # First 10 words
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    
                    title_pmids = await self.clients['pubmed'].search(
                        search_record["query"],
                        max_results=20
                    )
                    new_pmids = [p for p in title_pmids if p not in pmids]
                    pmids.update(new_pmids)
                    
                    for pmid in new_pmids[:10]:
                        article = await self.clients['pubmed'].fetch(pmid)
                        if article and "error" not in article:
                            articles.append(article)
                    
                    search_record["status"] = "success"
                    search_record["results_count"] = len(new_pmids)
                    searches.append(search_record)
            
            logger.info(f"✓ PubMed: {len(searches)} searches, {len(pmids)} unique PMIDs found")
            
            return {
                "success": True,
                "searches": searches,
                "data": {
                    "pmids": list(pmids),
                    "articles": articles,
                    "total_found": len(pmids)
                },
                "total_results": len(pmids)
            }
            
        except Exception as e:
            logger.error(f"✗ PubMed error: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "searches": searches
            }
    
    async def _search_pmc(
        self,
        nct_id: str,
        ct_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Search PMC with multiple strategies (independent of PubMed).
        
        Strategies:
        1. Direct NCT ID search
        2. Title search (if NCT search yields no results)
        """
        logger.info(f"🔍 PMC: Multiple search strategies")
        
        searches = []
        pmcids = set()
        articles = []
        
        try:
            # Strategy 1: NCT ID search
            logger.info(f"  → Strategy 1: NCT ID search")
            search_record = {
                "search_type": "nct_id",
                "query": nct_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            nct_pmcids = await self.clients['pmc'].search(nct_id, max_results=20)
            pmcids.update(nct_pmcids)
            
            # Fetch metadata for PMCIDs
            for pmcid in list(pmcids)[:10]:  # Limit to 10
                article = await self.clients['pmc'].fetch(pmcid)
                if article and "error" not in article:
                    articles.append(article)
            
            search_record["status"] = "success"
            search_record["results_count"] = len(nct_pmcids)
            searches.append(search_record)
            
            # Strategy 2: Title search (if no results)
            if len(pmcids) == 0:
                title = self._extract_title(ct_data)
                if title:
                    logger.info(f"  → Strategy 2: Title search")
                    search_record = {
                        "search_type": "title",
                        "query": " ".join(title.split()[:10]),  # First 10 words
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    
                    title_pmcids = await self.clients['pmc'].search(
                        search_record["query"],
                        max_results=20
                    )
                    new_pmcids = [p for p in title_pmcids if p not in pmcids]
                    pmcids.update(new_pmcids)
                    
                    for pmcid in new_pmcids[:10]:
                        article = await self.clients['pmc'].fetch(pmcid)
                        if article and "error" not in article:
                            articles.append(article)
                    
                    search_record["status"] = "success"
                    search_record["results_count"] = len(new_pmcids)
                    searches.append(search_record)
            
            logger.info(f"✓ PMC: {len(searches)} searches, {len(pmcids)} PMCIDs found")
            
            return {
                "success": True,
                "searches": searches,
                "data": {
                    "pmcids": list(pmcids),
                    "articles": articles,
                    "total_found": len(pmcids)
                },
                "total_results": len(pmcids)
            }
            
        except Exception as e:
            logger.error(f"✗ PMC error: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "searches": searches
            }
    
    async def _search_pmc_bioc(
        self,
        nct_id: str,
        step1_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Fetch full-text from PMC BioC using PMIDs/PMCIDs.
        
        Strategies:
        1. Use PMIDs from PubMed results
        2. Convert PMCIDs to PMIDs if needed
        3. Fetch BioC format full text
        """
        logger.info(f"🔍 PMC BioC: Fetching full-text articles")
        
        searches = []
        articles = []
        pmids_used = []
        
        try:
            # Get PMIDs from PubMed results
            pubmed_data = step1_results.get("core_apis", {}).get("pubmed", {}).get("data", {})
            pmids = pubmed_data.get("pmids", [])
            
            if pmids:
                logger.info(f"  → Using {len(pmids)} PMIDs from PubMed")
            else:
                # Try to convert PMCIDs to PMIDs
                pmc_data = step1_results.get("core_apis", {}).get("pmc", {}).get("data", {})
                pmcids = pmc_data.get("pmcids", [])
                
                if pmcids:
                    logger.info(f"  → Converting {len(pmcids)} PMCIDs to PMIDs")
                    pmcid_to_pmid = await self.clients['pmc_bioc'].convert_pmcids_to_pmids(pmcids)
                    pmids = list(pmcid_to_pmid.values())
            
            # Fetch BioC data for each PMID
            for pmid in pmids[:10]:  # Limit to 10 articles
                search_record = {
                    "search_type": "pmid_fetch",
                    "query": pmid,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                bioc_data = await self.clients['pmc_bioc'].fetch_pmc_bioc(pmid)
                
                if bioc_data and "error" not in bioc_data:
                    articles.append(bioc_data)
                    pmids_used.append(pmid)
                    search_record["status"] = "success"
                    search_record["results_count"] = 1
                else:
                    search_record["status"] = "error"
                    search_record["error"] = bioc_data.get("error", "Unknown error")
                    search_record["results_count"] = 0
                
                searches.append(search_record)
            
            logger.info(f"✓ PMC BioC: {len(searches)} fetches, {len(articles)} full-text articles retrieved")
            
            return {
                "success": True,
                "searches": searches,
                "data": {
                    "articles": articles,
                    "pmids_used": pmids_used,
                    "total_found": len(articles)
                },
                "total_results": len(articles)
            }
            
        except Exception as e:
            logger.error(f"✗ PMC BioC error: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "searches": searches
            }
    
    def _extract_metadata(self, ct_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract key metadata from clinical trial data"""
        protocol = ct_data.get("protocolSection", {})
        ident = protocol.get("identificationModule", {})
        status_module = protocol.get("statusModule", {})
        conditions_module = protocol.get("conditionsModule", {})
        interventions_module = protocol.get("armsInterventionsModule", {})
        
        # Extract intervention names
        interventions = interventions_module.get("interventions", [])
        intervention_names = [
            i.get("name", "") 
            for i in interventions 
            if i.get("name")
        ]
        
        return {
            "title": ident.get("briefTitle", ""),
            "status": status_module.get("overallStatus", ""),
            "condition": conditions_module.get("conditions", []),
            "intervention": intervention_names,
            "description": ident.get("briefSummary", {}).get("text", "")
        }
    
    def _extract_title(self, ct_data: Dict[str, Any]) -> str:
        """Extract trial title"""
        return ct_data.get("protocolSection", {}).get(
            "identificationModule", {}
        ).get("briefTitle", "")
    
    def _extract_references(self, ct_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract references from clinical trial data"""
        protocol = ct_data.get("protocolSection", {})
        refs_module = protocol.get("referencesModule", {})
        return refs_module.get("references", [])
    
    def _generate_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate summary statistics for Step 1"""
        summary = {
            "nct_id": results.get("nct_id"),
            "title": results.get("metadata", {}).get("title", ""),
            "core_apis_searched": [],
            "results_per_api": {},
            "total_results": 0,
            "total_searches": 0
        }
        
        for api_name, api_results in results.get("core_apis", {}).items():
            if api_results.get("success"):
                summary["core_apis_searched"].append(api_name)
                count = api_results.get("total_results", 0)
                summary["results_per_api"][api_name] = count
                summary["total_results"] += count
                summary["total_searches"] += len(api_results.get("searches", []))
        
        return summary


__all__ = ['NCTStep1Searcher']
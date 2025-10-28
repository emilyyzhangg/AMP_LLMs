"""
NCT Core Search Engine - UPDATED
=====================

Enhanced search orchestration with improved data structure and search strategies.
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
    OpenFDAClient,
    UniProtClient
)
from nct_models import SearchConfig

logger = logging.getLogger(__name__)


class NCTSearchEngine:
    """
    Core search engine orchestrating multi-database searches.
    Updated with improved search strategies and data structure.
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
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=120, connect=30)
        )
        
        # Initialize core clients
        self.clients['clinicaltrials'] = ClinicalTrialsClient(self.session)
        self.clients['pubmed'] = PubMedClient(self.session, api_key=self.ncbi_key)
        self.clients['pmc'] = PMCClient(self.session, api_key=self.ncbi_key)
        self.clients['pmc_bioc'] = PMCBioClient(self.session, api_key=self.ncbi_key)
        
        # Initialize extended clients
        self.clients['duckduckgo'] = DuckDuckGoClient(self.session)
        self.clients['serpapi'] = SerpAPIClient(self.session, api_key=self.serpapi_key)
        self.clients['scholar'] = GoogleScholarClient(self.session, api_key=self.serpapi_key)
        self.clients['openfda'] = OpenFDAClient(self.session)
        self.clients['uniprot'] = UniProtClient(self.session)
        
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
        Execute comprehensive search with improved data structure.
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
                "intervention": "",
                "abstract": ""  # NEW: Store abstract
            },
            "databases": {}
        }
        
        # Step 1: Fetch ClinicalTrials.gov data
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
        
        # Store clinical trial data with enhanced metadata
        results["sources"]["clinical_trials"] = {
            "success": True,
            "data": ct_data,
            "fetch_time": datetime.utcnow().isoformat()
        }
        
        # Extract enhanced metadata including abstract
        results["metadata"]["title"] = self._extract_title(ct_data)
        results["metadata"]["status"] = self._extract_status(ct_data)
        results["metadata"]["condition"] = self._extract_condition(ct_data)
        results["metadata"]["intervention"] = self._extract_intervention(ct_data)
        results["metadata"]["abstract"] = self._extract_abstract(ct_data)  # NEW
        
        logger.info(f"Trial: {results['metadata']['title'][:100]}")
        
        # Step 2: Search PubMed with enhanced query tracking
        if status:
            status.current_database = "pubmed"
            status.progress = 30
            status.completed_databases.append("clinicaltrials")
        
        logger.info(f"Searching PubMed for {nct_id}")
        try:
            pubmed_data = await self._search_pubmed_enhanced(nct_id, ct_data)
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
        
        # Step 3: Search PMC with query grouping
        if status:
            status.current_database = "pmc"
            status.progress = 50
            status.completed_databases.append("pubmed")
        
        logger.info(f"Searching PMC for {nct_id}")
        try:
            pmc_data = await self._search_pmc_enhanced(nct_id, ct_data)
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
        
        # Step 4: Search PMC BioC with enhanced metadata
        if status:
            status.current_database = "pmc_bioc"
            status.progress = 60
            status.completed_databases.append("pmc")

        logger.info(f"Searching PMC BioC for {nct_id} using PubTator3")
        try:
            pmc_bioc_data = await self._search_pmc_bioc_enhanced(nct_id, ct_data, results)
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

        # Step 5: Extended searches
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
        
        # Backward compatibility
        results["databases"] = {
            "clinicaltrials": results["sources"]["clinical_trials"].get("data"),
            "pubmed": results["sources"]["pubmed"].get("data"),
            "pmc": results["sources"]["pmc"].get("data"),
            "pmc_bioc": results["sources"]["pmc_bioc"].get("data")
        }
        
        if "extended" in results["sources"]:
            for api_name, api_data in results["sources"]["extended"].items():
                results["databases"][api_name] = api_data.get("data")
        
        if status:
            status.progress = 100
            status.current_database = None
        
        logger.info(f"Search completed for {nct_id}")
        return results
    
    async def _search_pubmed_enhanced(self, nct_id: str, ct_data: Dict) -> Dict[str, Any]:
        """
        Enhanced PubMed search with query tracking.
        """
        try:
            references = self._extract_references(ct_data)
            
            results = {
                "pmids": [],
                "articles": [],
                "total_found": 0,
                "search_strategy": "references",
                "queries_used": []  # NEW: Track all queries used
            }
            
            # Strategy 1: Search by references
            if references:
                logger.info(f"Searching PubMed using {len(references)} references")
                
                for ref in references[:5]:
                    title = ref.get("title", "")
                    citation = ref.get("citation", "")
                    pmid = ref.get("pmid", "")
                    
                    if pmid and pmid not in results["pmids"]:
                        results["pmids"].append(pmid)
                        article = await self.clients['pubmed'].fetch(pmid)
                        if article and "error" not in article:
                            results["articles"].append(article)
                        continue
                    
                    if title or citation:
                        search_title = title or citation
                        authors = ref.get("authors", [])
                        
                        # Track the query
                        query = f"{search_title[:50]}..."
                        if authors:
                            query += f" AND {authors[0]}"
                        results["queries_used"].append(query)
                        
                        found_pmid = await self.clients['pubmed'].search_by_title_authors(
                            search_title, authors
                        )
                        
                        if found_pmid and found_pmid not in results["pmids"]:
                            results["pmids"].append(found_pmid)
                            article = await self.clients['pubmed'].fetch(found_pmid)
                            if article and "error" not in article:
                                results["articles"].append(article)
            
            # Strategy 2: Direct NCT ID search
            if len(results["pmids"]) == 0:
                logger.info(f"No references found, searching PubMed by NCT ID: {nct_id}")
                results["search_strategy"] = "nct_id"
                results["queries_used"].append(nct_id)
                
                pmids = await self.clients['pubmed'].search(nct_id, max_results=20)
                
                for pmid in pmids:
                    if pmid not in results["pmids"]:
                        results["pmids"].append(pmid)
                        
                        if len(results["articles"]) < 10:
                            article = await self.clients['pubmed'].fetch(pmid)
                            if article and "error" not in article:
                                results["articles"].append(article)
            
            # Strategy 3: Search by trial title
            if len(results["pmids"]) == 0:
                title = self._extract_title(ct_data)
                if title:
                    logger.info(f"Searching PubMed by trial title")
                    results["search_strategy"] = "title"
                    title_query = " ".join(title.split()[:10])
                    results["queries_used"].append(title_query)
                    
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
        
    async def _search_pmc_bioc_enhanced(
        self,
        nct_id: str,
        ct_data: Dict,
        results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Search PMC BioC using PubTator3 API with enhanced tracking and error details.
        """
        try:
            bioc_results = {
                "articles": [],
                "total_fetched": 0,
                "errors": [],
                "pmids_used": [],
                "pmids_attempted": [],
                "conversion_performed": False,
                "error_summary": {
                    "not_found": [],
                    "timeout": [],
                    "http_error": [],
                    "other": []
                }
            }
            
            # Strategy 1: Try to get PMIDs from PubMed results
            pubmed_data = results.get("sources", {}).get("pubmed", {})
            pmids = []
            
            if pubmed_data and isinstance(pubmed_data, dict):
                pubmed_actual_data = pubmed_data.get("data", {})
                pmids = pubmed_actual_data.get("pmids", [])
                logger.info(f"Found {len(pmids)} PMIDs from PubMed results")
            
            # Strategy 2: If no PMIDs, try to convert PMCIDs to PMIDs
            if not pmids:
                logger.info("No PMIDs found, attempting PMCID to PMID conversion")
                
                pmc_data = results.get("sources", {}).get("pmc", {})
                if pmc_data and isinstance(pmc_data, dict):
                    pmc_actual_data = pmc_data.get("data", {})
                    pmcids = pmc_actual_data.get("pmcids", [])
                    
                    if pmcids:
                        logger.info(f"Found {len(pmcids)} PMCIDs, converting to PMIDs")
                        
                        # Convert PMCIDs to PMIDs
                        pmcid_to_pmid = await self.clients['pmc_bioc'].convert_pmcids_to_pmids(pmcids)
                        
                        if pmcid_to_pmid:
                            pmids = list(pmcid_to_pmid.values())
                            bioc_results["conversion_performed"] = True
                            bioc_results["pmcid_to_pmid_map"] = pmcid_to_pmid
                            logger.info(f"Successfully converted {len(pmids)} PMCIDs to PMIDs")
                        else:
                            logger.warning("PMCID to PMID conversion returned no results")
            
            # If still no PMIDs, return empty results
            if not pmids:
                logger.warning(f"No PMIDs available for BioC fetch")
                return bioc_results
            
            bioc_results["pmids_used"] = pmids[:5]
            bioc_results["pmids_attempted"] = pmids[:5]
            
            logger.info(f"Fetching BioC data for {len(pmids[:5])} PMIDs using PubTator3")
            
            # Fetch BioC data for each PMID (limit to first 5)
            for pmid in pmids[:5]:
                try:
                    bioc_data = await self.clients['pmc_bioc'].fetch_pmc_bioc(pmid, format="biocjson")
                    
                    if "error" not in bioc_data:
                        bioc_results["articles"].append({
                            "pmid": pmid,
                            "data": bioc_data
                        })
                        bioc_results["total_fetched"] += 1
                        logger.info(f"Successfully fetched BioC data for PMID {pmid}")
                    else:
                        # Categorize the error
                        error_type = bioc_data.get("error_type", "other")
                        error_msg = bioc_data.get("error", "Unknown error")
                        note = bioc_data.get("note", "")
                        
                        error_detail = {
                            "pmid": pmid,
                            "error": error_msg,
                            "type": error_type
                        }
                        
                        if note:
                            error_detail["note"] = note
                        
                        bioc_results["errors"].append(error_detail)
                        
                        # Add to error summary
                        if error_type in bioc_results["error_summary"]:
                            bioc_results["error_summary"][error_type].append(pmid)
                        else:
                            bioc_results["error_summary"]["other"].append(pmid)
                        
                        logger.warning(f"BioC fetch failed for PMID {pmid}: {error_msg}")
                        
                except Exception as e:
                    logger.error(f"Error fetching BioC for PMID {pmid}: {e}")
                    bioc_results["errors"].append({
                        "pmid": pmid,
                        "error": str(e),
                        "type": "exception"
                    })
                    bioc_results["error_summary"]["other"].append(pmid)
            
            logger.info(f"BioC fetch complete: {bioc_results['total_fetched']} successful, "
                    f"{len(bioc_results['errors'])} errors")
            
            # Log error breakdown
            if bioc_results["errors"]:
                logger.info(f"BioC error breakdown:")
                for error_type, pmid_list in bioc_results["error_summary"].items():
                    if pmid_list:
                        logger.info(f"  {error_type}: {len(pmid_list)} article(s)")
            
            return bioc_results
            
        except Exception as e:
            logger.error(f"PMC BioC search error: {e}", exc_info=True)
            return {
                "error": str(e),
                "articles": [],
                "total_fetched": 0,
                "errors": []
            }

    async def _search_pmc_enhanced(self, nct_id: str, ct_data: Dict) -> Dict[str, Any]:
        """
        Enhanced PMC search with query grouping and results by query.
        """
        try:
            results = {
                "pmcids": [],
                "articles": [],
                "total_found": 0,
                "results_by_query": [],  # NEW: Group results by query
                "search_strategy": "nct_id"
            }
            
            # Strategy 1: Search by NCT ID
            logger.info(f"Searching PMC by NCT ID: {nct_id}")
            nct_pmcids = await self.clients['pmc'].search(nct_id, max_results=20)
            
            if nct_pmcids:
                results["results_by_query"].append({
                    "query": nct_id,
                    "query_type": "NCT ID",
                    "pmcids": nct_pmcids,
                    "count": len(nct_pmcids)
                })
                results["pmcids"].extend(nct_pmcids)
            
            # Strategy 2: Search by title if no NCT results
            if not nct_pmcids:
                title = self._extract_title(ct_data)
                if title:
                    logger.info(f"Searching PMC by trial title")
                    results["search_strategy"] = "title"
                    title_query = " ".join(title.split()[:10])
                    title_pmcids = await self.clients['pmc'].search(title_query, max_results=20)
                    
                    if title_pmcids:
                        results["results_by_query"].append({
                            "query": title_query,
                            "query_type": "Trial Title",
                            "pmcids": title_pmcids,
                            "count": len(title_pmcids)
                        })
                        results["pmcids"].extend(title_pmcids)
            
            # Fetch article metadata for first 10
            if results["pmcids"]:
                for pmcid in results["pmcids"][:10]:
                    article = await self.clients['pmc'].fetch(pmcid)
                    if article and "error" not in article:
                        results["articles"].append(article)
            
            results["total_found"] = len(results["pmcids"])
            logger.info(f"PMC search found {results['total_found']} results")
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
        """
        Search extended databases with enhanced OpenFDA integration.
        All extended APIs use standardized (nct_id, trial_data) interface.
        """
        # Determine which databases to search
        if config.enabled_databases:
            databases = config.enabled_databases
        else:
            databases = ["duckduckgo", "serpapi", "scholar", "openfda", "uniprot"]
        
        # Filter to available clients
        databases = [db for db in databases if db in self.clients]
        
        logger.info(f"Extended search params for {nct_id}")
        logger.info(f"Databases to search: {databases}")
        
        # Create search tasks - ALL use (nct_id, ct_data) interface
        tasks = {}
        
        for db_name in databases:
            tasks[db_name] = self.clients[db_name].search(nct_id, ct_data)
        
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
                
                # Enhanced error detection and logging
                has_error = "error" in result
                
                if has_error:
                    error_msg = result.get("error", "Unknown error")
                    logger.error(f"❌ {db_name} API error: {error_msg}")
                else:
                    total = result.get("total_found", 0)
                    logger.info(f"✅ {db_name} completed: {total} results found")
                
                results[db_name] = {
                    "success": not has_error,
                    "data": result,
                    "error": result.get("error") if has_error else None,
                    "fetch_time": datetime.utcnow().isoformat()
                }
                
                if status:
                    status.completed_databases.append(db_name)
                
                completed += 1
                
            except Exception as e:
                logger.error(f"💥 {db_name} search exception: {e}", exc_info=True)
                results[db_name] = {
                    "success": False,
                    "error": str(e),
                    "data": {"error": str(e), "results": [], "total_found": 0}
                }
        
        return results
    
    def _extract_all_identifiers(self, ct_data: Dict, trial_results: Dict) -> Dict[str, List[str]]:
        """
        Extract all identifiers (PMIDs, PMCIDs, DOIs) from trial data.
        """
        identifiers = {
            "pmids": [],
            "pmcids": [],
            "dois": []
        }
        
        # Get PMIDs from PubMed results
        pubmed_data = trial_results.get("sources", {}).get("pubmed", {}).get("data", {})
        if pubmed_data:
            identifiers["pmids"] = pubmed_data.get("pmids", [])[:5]
        
        # Get PMCIDs from PMC results
        pmc_data = trial_results.get("sources", {}).get("pmc", {}).get("data", {})
        if pmc_data:
            identifiers["pmcids"] = pmc_data.get("pmcids", [])[:5]
        
        # Extract DOIs from references
        try:
            protocol = ct_data.get("protocolSection", {})
            refs_mod = protocol.get("referencesModule", {})
            refs_list = refs_mod.get("references", [])
            
            for ref in refs_list[:5]:
                if isinstance(ref, dict):
                    citation = ref.get("citation", "")
                    # Simple DOI extraction
                    if "doi" in citation.lower():
                        # Extract DOI pattern
                        import re
                        doi_match = re.search(r'10\.\d{4,}/[^\s]+', citation)
                        if doi_match:
                            identifiers["dois"].append(doi_match.group(0))
        except Exception as e:
            logger.warning(f"Failed to extract DOIs: {e}")
        
        return identifiers
    
    def _extract_abstract(self, ct_data: Dict) -> str:
        """Extract trial abstract/summary."""
        try:
            protocol = ct_data.get("protocolSection", {})
            if not protocol:
                return ""
            
            desc_mod = protocol.get("descriptionModule", {})
            
            # Try detailed description first, then brief summary
            abstract = (
                desc_mod.get("detailedDescription") or
                desc_mod.get("briefSummary") or
                ""
            )
            
            return abstract.strip()
            
        except Exception as e:
            logger.warning(f"Failed to extract abstract: {e}")
            return ""
    
    def _extract_title(self, ct_data: Dict) -> str:
        """Extract trial title."""
        try:
            protocol = ct_data.get("protocolSection", {})
            if not protocol:
                return ""
            
            ident = protocol.get("identificationModule", {})
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
        """Extract references from trial data."""
        try:
            protocol = ct_data.get("protocolSection", {})
            if not protocol:
                return []
            
            refs_mod = protocol.get("referencesModule", {})
            refs_list = refs_mod.get("references", [])
            
            parsed_refs = []
            
            for ref in refs_list:
                if isinstance(ref, dict):
                    parsed_ref = {
                        "pmid": ref.get("pmid", ""),
                        "citation": ref.get("citation", ""),
                        "title": "",
                        "authors": []
                    }
                    
                    citation = ref.get("citation", "")
                    if citation:
                        parts = citation.split(".")
                        if parts:
                            parsed_ref["title"] = parts[0].strip()
                    
                    parsed_refs.append(parsed_ref)
            
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
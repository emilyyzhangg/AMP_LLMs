"""
NCT Step 2: Extended API Search
================================

Orchestrates Step 2 searches across extended APIs using user-selected
data fields from Step 1 results. Handles search combinations and tracks
all queries made.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
import asyncio

from nct_search_combinations import SearchCombinationGenerator

logger = logging.getLogger(__name__)


class NCTStep2Searcher:
    """
    Manages Step 2 searches across extended APIs.
    
    Extended APIs:
    - DuckDuckGo
    - SERP API (Google Search)
    - Google Scholar
    - OpenFDA
    
    Each API searches using combinations of user-selected fields from Step 1.
    """
    
    def __init__(self, clients: Dict[str, Any], config: Any):
        """
        Initialize Step 2 searcher.
        
        Args:
            clients: Dictionary of initialized API clients
            config: Configuration object with blacklist and settings
        """
        self.clients = clients
        self.config = config
        self.combination_generator = SearchCombinationGenerator()
    
    async def execute_step2(
        self,
        nct_id: str,
        step1_results: Dict[str, Any],
        selected_apis: List[str],
        field_selections: Dict[str, List[str]],
        status_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Execute complete Step 2 search workflow.
        
        Args:
            nct_id: NCT identifier
            step1_results: Complete Step 1 results
            selected_apis: List of API IDs to search (e.g., ['duckduckgo', 'openfda'])
            field_selections: Dict mapping API IDs to field names
                Example: {
                    'duckduckgo': ['title', 'condition'],
                    'openfda': ['intervention']
                }
            status_callback: Optional callback for progress updates
        
        Returns:
            Complete Step 2 results with all extended API results
        """
        logger.info(f"=" * 60)
        logger.info(f"STEP 2: Extended API Search for {nct_id}")
        logger.info(f"Selected APIs: {selected_apis}")
        logger.info(f"Field selections: {field_selections}")
        logger.info(f"=" * 60)
        
        results = {
            "nct_id": nct_id,
            "step": 2,
            "timestamp": datetime.utcnow().isoformat(),
            "step1_reference": step1_results.get("timestamp"),
            "selected_apis": selected_apis,
            "field_selections": field_selections,
            "extended_apis": {}
        }
        
        # Generate search plan
        if status_callback:
            status_callback("Generating search combinations", 5)
        
        search_plan = self.combination_generator.create_api_search_plan(
            step1_results,
            selected_apis,
            field_selections
        )
        
        logger.info(f"Generated search plan for {len(search_plan)} APIs")
        
        # Execute searches for each API
        total_apis = len(search_plan)
        completed = 0
        
        for api_id, search_configs in search_plan.items():
            if status_callback:
                progress = 10 + int((completed / total_apis) * 80)
                status_callback(f"Searching {api_id}", progress)
            
            logger.info(f"🔍 {api_id}: Executing {len(search_configs)} searches")
            
            api_results = await self._search_extended_api(
                api_id,
                nct_id,
                search_configs,
                step1_results
            )
            
            results["extended_apis"][api_id] = api_results
            completed += 1
        
        if status_callback:
            status_callback("Step 2 Complete", 100)
        
        # Generate summary
        results["summary"] = self._generate_summary(results)
        
        logger.info(f"=" * 60)
        logger.info(f"STEP 2 COMPLETE: {results['summary']['total_results']} total results")
        logger.info(f"=" * 60)
        
        return results
    
    async def _search_extended_api(
        self,
        api_id: str,
        nct_id: str,
        search_configs: List[Dict[str, Any]],
        step1_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute all searches for a specific extended API.
        
        Args:
            api_id: API identifier (e.g., 'duckduckgo')
            nct_id: NCT identifier
            search_configs: List of search configurations to execute
            step1_results: Step 1 results for context
        
        Returns:
            API results with all searches tracked
        """
        searches = []
        all_results = []
        
        try:
            if api_id not in self.clients:
                logger.error(f"Client not available for {api_id}")
                return {
                    "success": False,
                    "error": f"Client not available for {api_id}",
                    "searches": []
                }
            
            client = self.clients[api_id]
            
            # Execute each search configuration
            for i, config in enumerate(search_configs):
                search_record = {
                    "search_number": i + 1,
                    "fields_used": config['fields'],
                    "query": config['query'],
                    "description": config['description'],
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                logger.info(f"  → Search {i+1}/{len(search_configs)}: {config['description']}")
                
                try:
                    # Call appropriate search method based on API
                    if api_id == 'duckduckgo':
                        result = await self._search_duckduckgo(client, nct_id, config, step1_results)
                    elif api_id == 'serpapi':
                        result = await self._search_serpapi(client, nct_id, config, step1_results)
                    elif api_id == 'scholar':
                        result = await self._search_scholar(client, nct_id, config, step1_results)
                    elif api_id == 'openfda':
                        result = await self._search_openfda(client, nct_id, config, step1_results)
                    else:
                        result = {"error": f"Unknown API: {api_id}"}
                    
                    if "error" in result:
                        search_record["status"] = "error"
                        search_record["error"] = result["error"]
                        search_record["results_count"] = 0
                    else:
                        search_record["status"] = "success"
                        search_record["results_count"] = result.get("total_found", 0)
                        search_record["data"] = result
                        all_results.extend(result.get("results", []))
                    
                except Exception as e:
                    logger.error(f"Search {i+1} failed: {e}", exc_info=True)
                    search_record["status"] = "error"
                    search_record["error"] = str(e)
                    search_record["results_count"] = 0
                
                searches.append(search_record)
                
                # Small delay between searches to avoid rate limiting
                await asyncio.sleep(0.5)
            
            # Deduplicate results
            unique_results = self._deduplicate_results(all_results)
            
            total_searches = len(searches)
            successful_searches = len([s for s in searches if s["status"] == "success"])
            
            logger.info(f"✓ {api_id}: {successful_searches}/{total_searches} searches successful, {len(unique_results)} unique results")
            
            return {
                "success": successful_searches > 0,
                "searches": searches,
                "data": {
                    "results": unique_results,
                    "total_found": len(unique_results),
                    "total_searches": total_searches,
                    "successful_searches": successful_searches
                },
                "total_results": len(unique_results)
            }
            
        except Exception as e:
            logger.error(f"✗ {api_id} error: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "searches": searches
            }
    
    async def _search_duckduckgo(
        self,
        client: Any,
        nct_id: str,
        config: Dict[str, Any],
        step1_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute DuckDuckGo search with query"""
        query = config['query']
        
        # Add NCT ID to query if not already present
        if nct_id not in query:
            query = f"{nct_id} {query}"
        
        title = step1_results.get("metadata", {}).get("title", "")
        condition = step1_results.get("metadata", {}).get("condition", "")
        
        # Use condition as list or string
        if isinstance(condition, list):
            condition = condition[0] if condition else ""
        
        return await client.search(nct_id, title, condition)
    
    async def _search_serpapi(
        self,
        client: Any,
        nct_id: str,
        config: Dict[str, Any],
        step1_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute SERP API (Google) search"""
        query = config['query']
        
        if nct_id not in query:
            query = f"{nct_id} {query}"
        
        title = step1_results.get("metadata", {}).get("title", "")
        condition = step1_results.get("metadata", {}).get("condition", "")
        
        if isinstance(condition, list):
            condition = condition[0] if condition else ""
        
        return await client.search(nct_id, title, condition)
    
    async def _search_scholar(
        self,
        client: Any,
        nct_id: str,
        config: Dict[str, Any],
        step1_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute Google Scholar search"""
        query = config['query']
        
        if nct_id not in query:
            query = f"{nct_id} {query}"
        
        title = step1_results.get("metadata", {}).get("title", "")
        condition = step1_results.get("metadata", {}).get("condition", "")
        
        if isinstance(condition, list):
            condition = condition[0] if condition else ""
        
        return await client.search(nct_id, title, condition)
    
    async def _search_openfda(
        self,
        client: Any,
        nct_id: str,
        config: Dict[str, Any],
        step1_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute OpenFDA search with blacklist filtering.
        
        Filters out blacklisted terms before searching.
        """
        # Get intervention terms from the search config
        fields = config.get('fields', {})
        intervention_terms = []
        
        # Extract intervention-related terms
        for field_name, field_value in fields.items():
            if 'intervention' in field_name.lower():
                if isinstance(field_value, list):
                    intervention_terms.extend(field_value)
                else:
                    intervention_terms.append(field_value)
        
        # Apply blacklist filter
        filtered_terms = self.config.filter_blacklisted_terms(intervention_terms)
        
        if not filtered_terms:
            logger.warning(f"All intervention terms were blacklisted for OpenFDA")
            return {
                "error": "All terms were blacklisted",
                "blacklisted_terms": intervention_terms,
                "results": [],
                "total_found": 0
            }
        
        logger.info(f"OpenFDA: Searching with filtered terms: {filtered_terms}")
        
        # Get full trial data for comprehensive OpenFDA search
        ct_data = step1_results.get("core_apis", {}).get("clinicaltrials", {}).get("data", {})
        
        # Execute OpenFDA search
        result = await client.search(nct_id, ct_data)
        
        # Add blacklist info to result
        if "search_terms_used" in result:
            result["blacklisted_terms"] = [
                t for t in intervention_terms if t not in filtered_terms
            ]
        
        return result
    
    def _deduplicate_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Remove duplicate results based on URL or title.
        
        Args:
            results: List of result dictionaries
        
        Returns:
            Deduplicated list of results
        """
        seen_urls = set()
        seen_titles = set()
        unique_results = []
        
        for result in results:
            url = result.get('url', '')
            title = result.get('title', '')
            
            # Create unique key
            key = url or title
            
            if key and key not in seen_urls and key not in seen_titles:
                unique_results.append(result)
                if url:
                    seen_urls.add(url)
                if title:
                    seen_titles.add(title)
        
        return unique_results
    
    def _generate_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate summary statistics for Step 2"""
        summary = {
            "nct_id": results.get("nct_id"),
            "extended_apis_searched": [],
            "results_per_api": {},
            "searches_per_api": {},
            "total_results": 0,
            "total_searches": 0,
            "successful_searches": 0
        }
        
        for api_name, api_results in results.get("extended_apis", {}).items():
            if api_results.get("success"):
                summary["extended_apis_searched"].append(api_name)
                
                data = api_results.get("data", {})
                count = data.get("total_found", 0)
                total_searches = data.get("total_searches", 0)
                successful = data.get("successful_searches", 0)
                
                summary["results_per_api"][api_name] = count
                summary["searches_per_api"][api_name] = {
                    "total": total_searches,
                    "successful": successful
                }
                summary["total_results"] += count
                summary["total_searches"] += total_searches
                summary["successful_searches"] += successful
        
        return summary


__all__ = ['NCTStep2Searcher']
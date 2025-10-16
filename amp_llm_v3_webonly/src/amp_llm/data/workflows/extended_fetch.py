"""
Extended fetching workflow - adds supplementary APIs.

Builds on core_fetch by adding:
- PMC Full Text (Open Access)
- EudraCT (European trials)
- WHO ICTRP (International registry)
- Semantic Scholar (AI-powered literature)
"""
import asyncio
from typing import Dict, Any, List, Optional

from amp_llm.config import get_logger
from amp_llm.cli.async_io import aprint
from colorama import Fore

from .core_fetch import fetch_clinical_trial_and_pubmed_pmc

logger = get_logger(__name__)


async def fetch_with_extended_apis(
    nct_id: str,
    enabled_apis: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Fetch clinical trial data with extended API sources.
    
    Args:
        nct_id: NCT number
        enabled_apis: List of APIs to use (None = all available)
        
    Returns:
        Combined result with core + extended data
    """
    # Step 1: Fetch core data
    await aprint(Fore.CYAN + f"🔍 Fetching core data for {nct_id}...")
    
    result = await fetch_clinical_trial_and_pubmed_pmc(nct_id)
    
    if "error" in result:
        return result
    
    await aprint(Fore.GREEN + f"✅ Core data retrieved for {nct_id}")
    
    # Step 2: Fetch extended data if requested
    if enabled_apis is not None and len(enabled_apis) == 0:
        # Empty list = skip extended search
        logger.info(f"Skipping extended APIs for {nct_id}")
        return result
    
    await aprint(Fore.CYAN + f"🔎 Running extended API search for {nct_id}...")
    
    extended_results = await _fetch_extended_sources(nct_id, result, enabled_apis)
    
    result['extended_apis'] = extended_results
    
    await aprint(Fore.GREEN + f"✅ Extended search complete for {nct_id}")
    
    return result


async def _fetch_extended_sources(
    nct_id: str,
    core_result: Dict[str, Any],
    enabled_apis: Optional[List[str]]
) -> Dict[str, Any]:
    """
    Fetch data from extended API sources.
    
    Args:
        nct_id: NCT number
        core_result: Result from core fetch
        enabled_apis: List of APIs to use (None = all)
        
    Returns:
        Dictionary with extended API results
    """
    from amp_llm.data.external_apis.api_clients import APIManager, SearchConfig
    
    # Extract search parameters from core result
    params = _extract_search_params(nct_id, core_result)
    
    # Initialize API manager
    api_config = SearchConfig()
    api_manager = APIManager(api_config)
    
    # Run extended search
    try:
        extended = await api_manager.search_all(
            title=params['title'],
            authors=params['authors'],
            nct_id=nct_id,
            interventions=params['interventions'],
            conditions=params['conditions'],
            enabled_apis=enabled_apis
        )
        
        logger.info(f"Extended search completed for {nct_id}")
        return extended
        
    except Exception as e:
        logger.error(f"Extended API search error for {nct_id}: {e}", exc_info=True)
        await aprint(Fore.RED + f"⚠️ Extended API search failed: {e}")
        return {'error': str(e)}


def _extract_search_params(
    nct_id: str, 
    core_result: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Extract search parameters from core result.
    
    Args:
        nct_id: NCT number
        core_result: Result from core fetch
        
    Returns:
        Dictionary with search parameters
    """
    ct_data = core_result['sources']['clinical_trials']['data']
    protocol = ct_data.get('protocolSection', {})
    
    # Get title
    ident = protocol.get('identificationModule', {})
    title = (
        ident.get('officialTitle') or 
        ident.get('briefTitle') or 
        nct_id
    )
    
    # Get authors
    contacts = protocol.get('contactsLocationsModule', {})
    officials = contacts.get('overallOfficials', [])
    authors = [o.get('name', '') for o in officials if o.get('name')]
    
    # Get interventions
    arms_int = protocol.get('armsInterventionsModule', {})
    interventions_list = arms_int.get('interventions', [])
    intervention_names = [
        i.get('name', '') for i in interventions_list if i.get('name')
    ]
    
    # Get conditions
    cond_mod = protocol.get('conditionsModule', {})
    conditions = cond_mod.get('conditions', [])
    
    return {
        'title': title,
        'authors': authors,
        'interventions': intervention_names,
        'conditions': conditions,
    }


async def batch_fetch_with_extended(
    nct_ids: List[str],
    enabled_apis: Optional[List[str]] = None,
    max_concurrent: int = 5
) -> List[Dict[str, Any]]:
    """
    Fetch multiple NCT trials with extended APIs concurrently.
    
    Args:
        nct_ids: List of NCT numbers
        enabled_apis: List of APIs to use (None = all)
        max_concurrent: Maximum concurrent fetches
        
    Returns:
        List of combined results
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def fetch_with_limit(nct_id: str):
        async with semaphore:
            return await fetch_with_extended_apis(nct_id, enabled_apis)
    
    logger.info(f"Batch fetching {len(nct_ids)} trials (max {max_concurrent} concurrent)")
    
    tasks = [fetch_with_limit(nct_id) for nct_id in nct_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Filter out exceptions
    valid_results = []
    for nct_id, result in zip(nct_ids, results):
        if isinstance(result, Exception):
            logger.error(f"Failed to fetch {nct_id}: {result}")
            await aprint(Fore.RED + f"❌ {nct_id}: {result}")
        elif result is not None:
            valid_results.append(result)
    
    logger.info(f"Batch fetch complete: {len(valid_results)}/{len(nct_ids)} successful")
    
    return valid_results
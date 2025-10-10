"""
Extended API search integration for NCT lookup.
UPDATED: Now includes DuckDuckGo and Google/SerpAPI.
"""
from typing import List, Dict, Any, Optional

from amp_llm.cli.async_io import ainput, aprint
from amp_llm.config import get_logger
from colorama import Fore

logger = get_logger(__name__)


async def get_api_selection() -> List[str]:
    """
    Ask user which APIs to use for extended search.
    UPDATED: Now includes DuckDuckGo and Google options.
    
    Returns:
        List of enabled API names (empty list = no extended search)
    """
    use_extended = await ainput(
        Fore.CYAN + 
        "Use extended API search? (y/n) [y]: "
    )
    use_extended = use_extended.strip().lower() in ('y', 'yes', '')
    
    if not use_extended:
        return []  # Empty list = skip extended search
    
    # Show API collections
    await aprint(Fore.CYAN + "\n📊 Available API Collections:")
    await aprint(Fore.WHITE + "  [1] All APIs (Comprehensive - 6 APIs)")
    await aprint(Fore.WHITE + "  [2] Literature Only (PMC Full Text, Semantic Scholar)")
    await aprint(Fore.WHITE + "  [3] Clinical Databases (EudraCT, WHO ICTRP)")
    await aprint(Fore.WHITE + "  [4] Web Search (DuckDuckGo, Google)")
    await aprint(Fore.WHITE + "  [5] Custom Selection")
    
    api_choice = await ainput(Fore.CYAN + "Select [1-5] or Enter for all [1]: ")
    api_choice = api_choice.strip() or "1"
    
    # Determine enabled APIs
    if api_choice == "1":
        return None  # None = All APIs
    elif api_choice == "2":
        return ['pmc_fulltext', 'semantic_scholar']
    elif api_choice == "3":
        return ['eudract', 'who_ictrp']
    elif api_choice == "4":
        return ['duckduckgo', 'serpapi']
    elif api_choice == "5":
        await aprint(Fore.CYAN + "\n📋 Available APIs:")
        await aprint(Fore.WHITE + "  • pmc_fulltext - PMC Full Text (free)")
        await aprint(Fore.WHITE + "  • semantic_scholar - AI-powered papers (free)")
        await aprint(Fore.WHITE + "  • eudract - European trials (free)")
        await aprint(Fore.WHITE + "  • who_ictrp - International trials (free)")
        await aprint(Fore.WHITE + "  • duckduckgo - Web search (free)")
        await aprint(Fore.WHITE + "  • serpapi - Google search (requires API key)")
        
        custom = await ainput(Fore.CYAN + "Enter APIs (comma-separated): ")
        return [api.strip() for api in custom.split(',') if api.strip()]
    else:
        return None  # Default to all


async def run_extended_api_search(
    nct: str, 
    trial_result: Dict[str, Any],
    enabled_apis: Optional[List[str]]
) -> Dict[str, Any]:
    """
    Run extended API search for a trial.
    
    Args:
        nct: NCT number
        trial_result: Result from fetch_clinical_trial_and_pubmed_pmc
        enabled_apis: List of APIs to use (None = all)
        
    Returns:
        Dictionary with extended API results
    """
    await aprint(Fore.CYAN + f"\n🔎 Running extended API search...")
    
    # Extract search parameters from trial data
    search_params = _extract_search_params(nct, trial_result)
    
    # Initialize API manager
    from amp_llm.data.external_apis.api_clients import APIManager, SearchConfig
    
    api_config = SearchConfig()
    api_manager = APIManager(api_config)
    
    # Run extended search
    try:
        extended_results = await api_manager.search_all(
            title=search_params['title'],
            authors=search_params['authors'],
            nct_id=nct,
            interventions=search_params['interventions'],
            conditions=search_params['conditions'],
            enabled_apis=enabled_apis
        )
        
        return extended_results
        
    except Exception as e:
        await aprint(Fore.RED + f"⚠️ Extended API search failed: {e}")
        logger.error(f"Extended API search error for {nct}: {e}", exc_info=True)
        return {'error': str(e)}


def _extract_search_params(nct: str, trial_result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract search parameters from trial result."""
    ct_data = trial_result['sources']['clinical_trials']['data']
    protocol = ct_data.get('protocolSection', {})
    
    # Get title
    ident = protocol.get('identificationModule', {})
    title = (
        ident.get('officialTitle') or 
        ident.get('briefTitle') or 
        nct
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
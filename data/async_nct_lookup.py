"""
Async NCT (ClinicalTrials.gov) lookup module.
ENHANCED: Now includes extended API searches (Meilisearch, Swirl, OpenFDA, etc.)
"""
import asyncio
from typing import List, Dict, Any
from colorama import Fore, Style
from config import get_logger

try:
    from aioconsole import ainput, aprint
except ImportError:
    async def ainput(prompt):
        return input(prompt)
    async def aprint(*args, **kwargs):
        print(*args, **kwargs)

from data.data_fetchers import (
    fetch_clinical_trial_and_pubmed_pmc,
    print_study_summary,
    save_results,
    summarize_result
)

# Import new API clients
from data.api_clients import APIManager, SearchConfig

logger = get_logger(__name__)


async def run_nct_lookup():
    """
    Main NCT lookup workflow with extended API search.
    ENHANCED: Now includes Meilisearch, Swirl, OpenFDA, Health Canada, DDG, SERP API.
    """
    await aprint(
        Fore.YELLOW + Style.BRIGHT + 
        "\n=== 🔬 NCT Clinical Trial Lookup ==="
    )
    await aprint(
        Fore.WHITE + 
        "Search for clinical trials by NCT number and find related publications.\n"
    )
    
    # Initialize API manager
    api_config = SearchConfig()
    api_manager = APIManager(api_config)
    
    while True:
        try:
            # Get NCT input
            nct_input = await ainput(
                Fore.CYAN + 
                "\nEnter NCT number(s), comma-separated (or 'main menu' to go back): "
            )
            nct_input = nct_input.strip()
            
            # Check for exit commands
            if nct_input.lower() in ('main menu', 'exit', 'quit', 'back', ''):
                await aprint(Fore.YELLOW + "Returning to main menu...")
                logger.info("User returned to main menu from NCT lookup")
                return
            
            # Parse NCT numbers
            ncts = [n.strip().upper() for n in nct_input.split(',') if n.strip()]
            
            if not ncts:
                await aprint(Fore.RED + "No valid NCT numbers provided.")
                continue
            
            # Basic validation
            for nct in ncts:
                if not nct.startswith('NCT'):
                    await aprint(
                        Fore.YELLOW + 
                        f"'{nct}' doesn't look like a valid NCT number, but will try..."
                    )
            
            # Ask about extended API search
            use_extended = await ainput(
                Fore.CYAN + 
                "Use extended API search (Meilisearch, OpenFDA, etc.)? (y/n) [n]: "
            )
            use_extended = use_extended.strip().lower() in ('y', 'yes')
            
            if use_extended:
                # Ask which APIs to use
                await aprint(Fore.CYAN + "\nAvailable APIs:")
                await aprint(Fore.WHITE + "  1) All (default)")
                await aprint(Fore.WHITE + "  2) Meilisearch only")
                await aprint(Fore.WHITE + "  3) OpenFDA only")
                await aprint(Fore.WHITE + "  4) SERP API (Google) only")
                await aprint(Fore.WHITE + "  5) DuckDuckGo only")
                await aprint(Fore.WHITE + "  6) Custom selection")
                
                api_choice = await ainput(Fore.CYAN + "Select [1]: ")
                api_choice = api_choice.strip() or "1"
                
                # Determine enabled APIs
                if api_choice == "1":
                    enabled_apis = None  # All
                elif api_choice == "2":
                    enabled_apis = ['meilisearch']
                elif api_choice == "3":
                    enabled_apis = ['openfda']
                elif api_choice == "4":
                    enabled_apis = ['serpapi']
                elif api_choice == "5":
                    enabled_apis = ['duckduckgo']
                elif api_choice == "6":
                    await aprint(Fore.CYAN + "Enter APIs (comma-separated):")
                    await aprint(Fore.WHITE + "  meilisearch, swirl, openfda, health_canada, duckduckgo, serpapi")
                    custom = await ainput(Fore.CYAN + "APIs: ")
                    enabled_apis = [api.strip() for api in custom.split(',')]
                else:
                    enabled_apis = None
            else:
                enabled_apis = []
            
            # Fetch data concurrently
            await aprint(Fore.CYAN + f"\n🔍 Processing {len(ncts)} NCT number(s)...")
            logger.info(f"Fetching data for: {', '.join(ncts)}")
            
            # Create tasks for concurrent fetching
            tasks = [_fetch_single_nct_extended(nct, api_manager, enabled_apis) for nct in ncts]
            results_with_status = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Filter valid results
            results = []
            for i, result in enumerate(results_with_status):
                if isinstance(result, Exception):
                    await aprint(Fore.RED + f"Exception for {ncts[i]}: {result}")
                    logger.error(f"Exception for {ncts[i]}", exc_info=result)
                elif result is not None:
                    results.append(result)
            
            if not results:
                await aprint(Fore.RED + "No results found for any NCT numbers.")
                continue
            
            # Show summary
            await aprint(Fore.CYAN + f"\n📊 Summary of {len(results)} result(s):")
            for r in results:
                summary = summarize_result(r)
                await aprint(
                    Fore.GREEN +
                    f"  • {summary['NCT']}: " +
                    f"{summary['PubMed Count']} PubMed, " +
                    f"{summary['PMC Count']} PMC"
                )
                
                # Show extended API results summary
                if 'extended_apis' in r:
                    ext = r['extended_apis']
                    api_counts = []
                    
                    if 'meilisearch' in ext and ext['meilisearch'].get('hits'):
                        api_counts.append(f"{len(ext['meilisearch']['hits'])} Meilisearch")
                    
                    if 'openfda_events' in ' '.join(ext.keys()):
                        openfda_count = sum(
                            len(v.get('results', [])) 
                            for k, v in ext.items() 
                            if k.startswith('openfda')
                        )
                        if openfda_count:
                            api_counts.append(f"{openfda_count} OpenFDA")
                    
                    if 'serpapi_google' in ext and ext['serpapi_google'].get('organic_results'):
                        api_counts.append(f"{len(ext['serpapi_google']['organic_results'])} Google")
                    
                    if 'duckduckgo' in ext and ext['duckduckgo'].get('results'):
                        api_counts.append(f"{len(ext['duckduckgo']['results'])} DuckDuckGo")
                    
                    if 'health_canada' in ext and ext['health_canada'].get('results'):
                        api_counts.append(f"{len(ext['health_canada']['results'])} Health Canada")
                    
                    if api_counts:
                        await aprint(Fore.CYAN + f"    Extended: {', '.join(api_counts)}")
            
            # Offer to save
            save_choice = await ainput(
                Fore.CYAN + "\nSave results? (txt/csv/json/none): "
            )
            save_choice = save_choice.strip().lower()
            
            if save_choice in ('txt', 'csv', 'json'):
                # Get filename
                default_filename = f"nct_results_{len(results)}_studies"
                filename = await ainput(
                    Fore.CYAN + f"Enter filename (without extension) [{default_filename}]: "
                )
                filename = filename.strip() or default_filename
                
                # Save results
                try:
                    save_results(results, filename, fmt=save_choice)
                    await aprint(Fore.GREEN + f"Results saved successfully!")
                    logger.info(f"Saved {len(results)} results to {filename}.{save_choice}")
                except Exception as e:
                    await aprint(Fore.RED + f"Error saving results: {e}")
                    logger.error(f"Error saving results: {e}", exc_info=True)
            else:
                await aprint(Fore.YELLOW + "Results not saved.")
            
            # Ask to continue
            choice = await ainput(Fore.CYAN + "\nLookup more NCTs? (y/n): ")
            if choice.strip().lower() not in ('y', 'yes'):
                await aprint(Fore.YELLOW + "Returning to main menu...")
                return
                
        except KeyboardInterrupt:
            await aprint(Fore.YELLOW + "\n\nInterrupted. Returning to main menu...")
            return
        except Exception as e:
            await aprint(Fore.RED + f"Unexpected error: {e}")
            logger.error(f"Error in NCT lookup: {e}", exc_info=True)
            
            # Ask if user wants to continue despite error
            retry = await ainput(Fore.CYAN + "Try again? (y/n): ")
            if retry.strip().lower() not in ('y', 'yes'):
                return


async def _fetch_single_nct_extended(
    nct: str, 
    api_manager: APIManager, 
    enabled_apis: List[str]
) -> Dict[str, Any]:
    """
    Fetch data for a single NCT number with extended API search.
    
    Args:
        nct: NCT number
        api_manager: API manager instance
        enabled_apis: List of enabled APIs (empty list = none, None = all)
        
    Returns:
        Combined result with clinical trial data and extended API results
    """
    await aprint(Fore.YELLOW + f"\n{'='*60}")
    await aprint(Fore.YELLOW + f"Fetching data for {nct}...")
    await aprint(Fore.YELLOW + f"{'='*60}\n")
    
    try:
        # Step 1: Fetch clinical trial data (includes PubMed and PMC)
        result = await fetch_clinical_trial_and_pubmed_pmc(nct)
        
        if 'error' in result:
            error_msg = result.get('error', 'Unknown error')
            await aprint(Fore.RED + f"{nct}: {error_msg}")
            logger.warning(f"Failed to fetch {nct}: {error_msg}")
            return None
        
        # Print standard summary
        await aprint(Fore.GREEN + f"✅ Successfully fetched {nct}")
        print_study_summary(result)
        
        # Step 2: Extended API search (if enabled)
        if enabled_apis is not None and len(enabled_apis) > 0:
            await aprint(Fore.CYAN + f"\n🔎 Running extended API search...")
            
            # Extract search parameters from clinical trial data
            ct_data = result['sources']['clinical_trials']['data']
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
            
            # Get interventions/drugs
            arms_int = protocol.get('armsInterventionsModule', {})
            interventions_list = arms_int.get('interventions', [])
            intervention_names = [
                i.get('name', '') for i in interventions_list if i.get('name')
            ]
            
            # Run extended search
            try:
                extended_results = await api_manager.search_all(
                    title=title,
                    authors=authors,
                    nct_id=nct,
                    interventions=intervention_names,
                    enabled_apis=enabled_apis
                )
                
                # Add to result
                result['extended_apis'] = extended_results
                
                # Print summary of extended results
                await aprint(Fore.GREEN + f"\n✅ Extended API search complete for {nct}")
                await _print_extended_summary(extended_results)
                
            except Exception as e:
                await aprint(Fore.RED + f"⚠️ Extended API search failed: {e}")
                logger.error(f"Extended API search error for {nct}: {e}", exc_info=True)
                result['extended_apis'] = {'error': str(e)}
        
        logger.info(f"Successfully fetched complete data for {nct}")
        return result
        
    except Exception as e:
        await aprint(Fore.RED + f"{nct}: Unexpected error: {e}")
        logger.error(f"Error fetching {nct}: {e}", exc_info=True)
        return None


async def _print_extended_summary(extended_results: Dict[str, Any]):
    """Print summary of extended API results."""
    
    summary_lines = []
    
    # Meilisearch
    if 'meilisearch' in extended_results:
        ms = extended_results['meilisearch']
        if 'hits' in ms:
            count = len(ms['hits'])
            summary_lines.append(f"  📊 Meilisearch: {count} hit(s)")
    
    # Swirl
    if 'swirl' in extended_results:
        sw = extended_results['swirl']
        if 'results' in sw:
            count = len(sw['results'])
            summary_lines.append(f"  🔄 Swirl: {count} result(s)")
    
    # OpenFDA
    openfda_events = 0
    openfda_labels = 0
    for key, value in extended_results.items():
        if key.startswith('openfda_events'):
            openfda_events += len(value.get('results', []))
        elif key.startswith('openfda_labels'):
            openfda_labels += len(value.get('results', []))
    
    if openfda_events or openfda_labels:
        summary_lines.append(f"  💊 OpenFDA: {openfda_events} event(s), {openfda_labels} label(s)")
    
    # Health Canada
    if 'health_canada' in extended_results:
        hc = extended_results['health_canada']
        if 'results' in hc:
            count = len(hc['results'])
            summary_lines.append(f"  🍁 Health Canada: {count} trial(s)")
    
    # DuckDuckGo
    if 'duckduckgo' in extended_results:
        ddg = extended_results['duckduckgo']
        if 'results' in ddg:
            count = len(ddg['results'])
            summary_lines.append(f"  🦆 DuckDuckGo: {count} result(s)")
    
    # SERP API Google
    if 'serpapi_google' in extended_results:
        serp = extended_results['serpapi_google']
        if 'organic_results' in serp:
            count = len(serp['organic_results'])
            summary_lines.append(f"  🔍 Google: {count} result(s)")
    
    # SERP API Scholar
    if 'serpapi_scholar' in extended_results:
        scholar = extended_results['serpapi_scholar']
        if 'organic_results' in scholar:
            count = len(scholar['organic_results'])
            summary_lines.append(f"  🎓 Google Scholar: {count} result(s)")
    
    if summary_lines:
        await aprint(Fore.CYAN + "\n📈 Extended API Results:")
        for line in summary_lines:
            await aprint(Fore.WHITE + line)
    else:
        await aprint(Fore.YELLOW + "\n⚠️ No results from extended APIs")
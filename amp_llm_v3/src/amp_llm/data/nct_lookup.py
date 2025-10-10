"""
Async NCT (ClinicalTrials.gov) lookup module.
ENHANCED: Now includes all APIs including PMC Full Text, EudraCT, WHO ICTRP, Semantic Scholar
"""
import asyncio
from typing import List, Dict, Any
from colorama import Fore, Style
from amp_llm.config import get_logger

try:
    from aioconsole import ainput, aprint
except ImportError:
    async def ainput(prompt):
        return input(prompt)
    async def aprint(*args, **kwargs):
        print(*args, **kwargs)

from amp_llm.data.clinical_trials.fetchers import (
    fetch_clinical_trial_and_pubmed_pmc,
    print_study_summary,
    save_results,
    summarize_result
)

# Import API manager with all APIs
from amp_llm.data.external_apis.api_clients import APIManager, SearchConfig

logger = get_logger(__name__)


async def run_nct_lookup():
    """
    Main NCT lookup workflow with ALL extended APIs.
    NOW INCLUDES: PMC Full Text, EudraCT, WHO ICTRP, Semantic Scholar
    """
    await aprint(
        Fore.YELLOW + Style.BRIGHT + 
        "\n=== 🔬 NCT Clinical Trial Lookup ==="
    )
    await aprint(
        Fore.WHITE + 
        "Search for clinical trials by NCT number and find related publications.\n"
    )
    
    # Initialize API manager with ALL APIs
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
                "Use extended API search? (y/n) [y]: "
            )
            use_extended = use_extended.strip().lower() in ('y', 'yes', '')
            
            # Initialize enabled_apis
            # None = all APIs, [] = no APIs, [list] = specific APIs
            if not use_extended:
                enabled_apis = []  # Empty list means skip extended search
            else:
                enabled_apis = None  # Start with None (will be set by menu choice)
            
            if use_extended:
                # Show ALL available APIs
                await aprint(Fore.CYAN + "\n📊 Available API Collections:")
                await aprint(Fore.WHITE + "  [1] All APIs (Comprehensive)")
                await aprint(Fore.WHITE + "  [2] Literature Only (PubMed, PMC Full Text, Semantic Scholar)")
                await aprint(Fore.WHITE + "  [3] Clinical Databases (EudraCT, WHO ICTRP, Health Canada)")
                await aprint(Fore.WHITE + "  [4] Drug Safety (OpenFDA)")
                await aprint(Fore.WHITE + "  [5] Web Search (Google, DuckDuckGo)")
                await aprint(Fore.WHITE + "  [6] Custom Selection")
                
                api_choice = await ainput(Fore.CYAN + "Select [1-6] or Enter for all [1]: ")
                api_choice = api_choice.strip() or "1"
                
                # Determine enabled APIs (NOW INCLUDING NEW ONES)
                if api_choice == "1":
                    enabled_apis = None  # All APIs
                elif api_choice == "2":
                    enabled_apis = ['pmc_fulltext', 'semantic_scholar', 'serpapi_scholar']
                elif api_choice == "3":
                    enabled_apis = ['eudract', 'who_ictrp', 'health_canada']
                elif api_choice == "4":
                    enabled_apis = ['openfda']
                elif api_choice == "5":
                    enabled_apis = ['duckduckgo', 'serpapi']
                elif api_choice == "6":
                    await aprint(Fore.CYAN + "\n📋 Available APIs:")
                    await aprint(Fore.WHITE + "  Original: meilisearch, swirl, openfda, health_canada, duckduckgo, serpapi")
                    await aprint(Fore.WHITE + "  NEW: pmc_fulltext, eudract, who_ictrp, semantic_scholar")
                    custom = await ainput(Fore.CYAN + "Enter APIs (comma-separated): ")
                    enabled_apis = [api.strip() for api in custom.split(',') if api.strip()]
                else:
                    enabled_apis = None
            
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
            
            # Show summary with NEW API results
            await aprint(Fore.CYAN + f"\n📊 Summary of {len(results)} result(s):")
            for r in results:
                summary = summarize_result(r)
                await aprint(
                    Fore.GREEN +
                    f"  • {summary['NCT']}: " +
                    f"{summary['PubMed Count']} PubMed, " +
                    f"{summary['PMC Count']} PMC"
                )
                
                # Show extended API results summary (INCLUDING NEW APIS)
                if 'extended_apis' in r:
                    ext = r['extended_apis']
                    api_counts = []
                    
                    # Original APIs
                    if 'meilisearch' in ext and ext['meilisearch'].get('hits'):
                        api_counts.append(f"{len(ext['meilisearch']['hits'])} Meilisearch")
                    
                    if any(k.startswith('openfda') for k in ext.keys()):
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
                    
                    # NEW APIs
                    if 'pmc_fulltext' in ext and ext['pmc_fulltext'].get('pmcids'):
                        api_counts.append(f"{len(ext['pmc_fulltext']['pmcids'])} PMC Full Text")
                    
                    if 'eudract' in ext and ext['eudract'].get('results'):
                        api_counts.append(f"{len(ext['eudract']['results'])} EudraCT")
                    
                    if 'who_ictrp' in ext and ext['who_ictrp'].get('results'):
                        api_counts.append(f"{len(ext['who_ictrp']['results'])} WHO ICTRP")
                    
                    if 'semantic_scholar' in ext and ext['semantic_scholar'].get('papers'):
                        api_counts.append(f"{len(ext['semantic_scholar']['papers'])} Semantic Scholar")
                    
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
            await aprint(Fore.YELLOW + "\n\n⚠️ Interrupted (Ctrl+C). Returning to main menu...")
            logger.info("NCT lookup interrupted by user (Ctrl+C)")
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
    Fetch data for a single NCT number with ALL extended APIs.
    NOW INCLUDES: PMC Full Text, EudraCT, WHO ICTRP, Semantic Scholar
    """
    await aprint(Fore.YELLOW + f"\n{'='*60}")
    await aprint(Fore.YELLOW + f"Fetching data for {nct}...")
    await aprint(Fore.YELLOW + f"{'='*60}\n")
    
    try:
        # Step 1: Fetch clinical trial data
        result = await fetch_clinical_trial_and_pubmed_pmc(nct)
        
        if 'error' in result:
            error_msg = result.get('error', 'Unknown error')
            await aprint(Fore.RED + f"{nct}: {error_msg}")
            logger.warning(f"Failed to fetch {nct}: {error_msg}")
            return None
        
        # Print standard summary
        await aprint(Fore.GREEN + f"✅ Successfully fetched {nct}")
        print_study_summary(result)
        
        # Step 2: Extended API search (INCLUDING NEW APIS)
        # enabled_apis = None means "use all APIs"
        # enabled_apis = [] means "skip extended search"
        # Check if we should run extended search
        should_run_extended = (
            enabled_apis is None or  # All APIs selected
            (isinstance(enabled_apis, list) and len(enabled_apis) > 0)  # Some APIs selected
        )
        
        if should_run_extended:
            await aprint(Fore.CYAN + f"\n🔎 Running extended API search...")
            
            # Extract search parameters
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
            
            # Get interventions
            arms_int = protocol.get('armsInterventionsModule', {})
            interventions_list = arms_int.get('interventions', [])
            intervention_names = [
                i.get('name', '') for i in interventions_list if i.get('name')
            ]
            
            # Get conditions
            cond_mod = protocol.get('conditionsModule', {})
            conditions = cond_mod.get('conditions', [])
            
            # Run extended search with ALL APIs
            try:
                extended_results = await api_manager.search_all(
                    title=title,
                    authors=authors,
                    nct_id=nct,
                    interventions=intervention_names,
                    conditions=conditions,
                    enabled_apis=enabled_apis
                )
                
                result['extended_apis'] = extended_results
                
                # Print summary
                await aprint(Fore.GREEN + f"\n✅ Extended API search complete for {nct}")
                await _print_extended_summary(extended_results)
                
            except Exception as e:
                await aprint(Fore.RED + f"⚠️ Extended API search failed: {e}")
                logger.error(f"Extended API search error for {nct}: {e}", exc_info=True)
                result['extended_apis'] = {'error': str(e)}
        
        logger.info(f"Successfully fetched complete data for {nct}")
        return result
        
    except KeyboardInterrupt:
        await aprint(Fore.YELLOW + f"\n⚠️ Fetch cancelled for {nct}")
        raise
    except Exception as e:
        await aprint(Fore.RED + f"{nct}: Unexpected error: {e}")
        logger.error(f"Error fetching {nct}: {e}", exc_info=True)
        return None


async def _print_extended_summary(extended_results: Dict[str, Any]):
    """Print summary of ALL extended API results (including new APIs)."""
    
    summary_lines = []
    
    # Original APIs
    if 'meilisearch' in extended_results:
        ms = extended_results['meilisearch']
        if 'hits' in ms:
            count = len(ms['hits'])
            summary_lines.append(f"  📊 Meilisearch: {count} hit(s)")
    
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
    
    if 'health_canada' in extended_results:
        hc = extended_results['health_canada']
        if 'results' in hc:
            count = len(hc['results'])
            summary_lines.append(f"  🍁 Health Canada: {count} trial(s)")
    
    if 'duckduckgo' in extended_results:
        ddg = extended_results['duckduckgo']
        if 'results' in ddg:
            count = len(ddg['results'])
            summary_lines.append(f"  🦆 DuckDuckGo: {count} result(s)")
    
    if 'serpapi_google' in extended_results:
        serp = extended_results['serpapi_google']
        if 'organic_results' in serp:
            count = len(serp['organic_results'])
            summary_lines.append(f"  🔍 Google: {count} result(s)")
    
    if 'serpapi_scholar' in extended_results:
        scholar = extended_results['serpapi_scholar']
        if 'organic_results' in scholar:
            count = len(scholar['organic_results'])
            summary_lines.append(f"  🎓 Google Scholar: {count} result(s)")
    
    # NEW APIs
    if 'pmc_fulltext' in extended_results:
        pmc = extended_results['pmc_fulltext']
        if 'pmcids' in pmc:
            count = len(pmc['pmcids'])
            summary_lines.append(f"  📄 PMC Full Text: {count} article(s)")
    
    if 'eudract' in extended_results:
        eu = extended_results['eudract']
        if 'results' in eu:
            count = len(eu['results'])
            summary_lines.append(f"  🇪🇺 EudraCT: {count} trial(s)")
    
    if 'who_ictrp' in extended_results:
        who = extended_results['who_ictrp']
        if 'results' in who:
            count = len(who['results'])
            summary_lines.append(f"  🌍 WHO ICTRP: {count} trial(s)")
    
    if 'semantic_scholar' in extended_results:
        ss = extended_results['semantic_scholar']
        if 'papers' in ss:
            count = len(ss['papers'])
            summary_lines.append(f"  🤖 Semantic Scholar: {count} paper(s)")
    
    if summary_lines:
        await aprint(Fore.CYAN + "\n📈 Extended API Results:")
        for line in summary_lines:
            await aprint(Fore.WHITE + line)
    else:
        await aprint(Fore.YELLOW + "\n⚠️ No results from extended APIs")
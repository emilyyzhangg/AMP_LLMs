# src/amp_llm/data/nct_lookup.py
"""
Enhanced NCT lookup with automatic database storage.
UPDATED: Now saves all results to ct_database/
"""
import asyncio
from typing import List, Dict, Any
from pathlib import Path
from colorama import Fore, Style

from amp_llm.config import get_logger, get_config

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
    summarize_result
)
from amp_llm.data.api_clients import APIManager, SearchConfig
from amp_llm.data.database.manager import DatabaseManager

logger = get_logger(__name__)
config = get_config()


async def run_nct_lookup():
    """
    Main NCT lookup workflow with automatic database storage.
    
    Features:
    - Fetches clinical trial data
    - Extended API search (optional)
    - Automatic save to ct_database/
    - Export options
    """
    await aprint(
        Fore.YELLOW + Style.BRIGHT + 
        "\n=== 🔬 NCT Clinical Trial Lookup ==="
    )
    await aprint(
        Fore.WHITE + 
        "Search for clinical trials and automatically save to database.\n"
    )
    
    # Initialize database
    db_path = Path("ct_database")
    db = DatabaseManager(db_path)
    
    await aprint(Fore.CYAN + f"📁 Database: {db_path.absolute()}")
    
    stats = db.get_statistics()
    await aprint(
        Fore.CYAN + 
        f"   Existing trials: {stats['total_trials']}, "
        f"Size: {stats['database_size_mb']:.1f} MB"
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
            
            # Check which trials already exist
            existing = [nct for nct in ncts if db.exists(nct)]
            new_trials = [nct for nct in ncts if not db.exists(nct)]
            
            if existing:
                await aprint(
                    Fore.YELLOW + 
                    f"\n⚠️  {len(existing)} trial(s) already in database: "
                    f"{', '.join(existing)}"
                )
                
                overwrite = await ainput(Fore.CYAN + "Overwrite existing? (y/n) [n]: ")
                
                if overwrite.strip().lower() in ('y', 'yes'):
                    new_trials.extend(existing)
                else:
                    await aprint(Fore.CYAN + "Will only fetch new trials.")
            
            if not new_trials:
                await aprint(Fore.YELLOW + "No new trials to fetch.")
                continue
            
            # Ask about extended API search
            use_extended = await ainput(
                Fore.CYAN + 
                "Use extended API search (Meilisearch, OpenFDA, etc.)? (y/n) [n]: "
            )
            use_extended = use_extended.strip().lower() in ('y', 'yes')
            
            enabled_apis = []
            if use_extended:
                # Ask which APIs
                await aprint(Fore.CYAN + "\nAvailable APIs:")
                await aprint(Fore.WHITE + "  1) All (default)")
                await aprint(Fore.WHITE + "  2) Core only (OpenFDA, DuckDuckGo)")
                await aprint(Fore.WHITE + "  3) Custom selection")
                
                api_choice = await ainput(Fore.CYAN + "Select [1]: ")
                api_choice = api_choice.strip() or "1"
                
                if api_choice == "1":
                    enabled_apis = None  # All
                elif api_choice == "2":
                    enabled_apis = ['openfda', 'duckduckgo']
                elif api_choice == "3":
                    await aprint(Fore.CYAN + "Enter APIs (comma-separated):")
                    await aprint(
                        Fore.WHITE + 
                        "  meilisearch, swirl, openfda, health_canada, duckduckgo, serpapi"
                    )
                    custom = await ainput(Fore.CYAN + "APIs: ")
                    enabled_apis = [api.strip() for api in custom.split(',')]
            
            # Fetch data
            await aprint(
                Fore.CYAN + 
                f"\n🔍 Processing {len(new_trials)} NCT number(s)..."
            )
            logger.info(f"Fetching data for: {', '.join(new_trials)}")
            
            # Fetch concurrently
            tasks = [
                _fetch_and_save_trial(nct, db, api_manager, enabled_apis) 
                for nct in new_trials
            ]
            results_with_status = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            results = []
            saved_count = 0
            
            for i, result in enumerate(results_with_status):
                if isinstance(result, Exception):
                    await aprint(Fore.RED + f"Exception for {new_trials[i]}: {result}")
                    logger.error(f"Exception for {new_trials[i]}", exc_info=result)
                elif result is not None:
                    results.append(result)
                    if result.get('saved', False):
                        saved_count += 1
            
            if not results:
                await aprint(Fore.RED + "No results obtained.")
                continue
            
            # Show summary
            await aprint(
                Fore.GREEN + 
                f"\n✅ Successfully saved {saved_count}/{len(new_trials)} trials to database"
            )
            
            await aprint(Fore.CYAN + f"\n📊 Summary of {len(results)} result(s):")
            for r in results:
                summary = summarize_result(r)
                await aprint(
                    Fore.GREEN +
                    f"  • {summary['NCT']}: " +
                    f"{summary['PubMed Count']} PubMed, " +
                    f"{summary['PMC Count']} PMC"
                )
                
                # Show extended API summary
                if 'extended_apis' in r:
                    await _print_extended_api_summary(r['extended_apis'])
            
            # Updated database stats
            stats = db.get_statistics()
            await aprint(
                Fore.CYAN + 
                f"\n📈 Database now contains {stats['total_trials']} trials "
                f"({stats['database_size_mb']:.1f} MB)"
            )
            
            # Offer additional export
            export_choice = await ainput(
                Fore.CYAN + 
                "\nExport to additional location? (txt/csv/json/none): "
            )
            export_choice = export_choice.strip().lower()
            
            if export_choice in ('txt', 'csv', 'json'):
                from amp_llm.data.clinical_trials.fetchers import save_results
                
                default_filename = f"nct_export_{len(results)}_trials"
                filename = await ainput(
                    Fore.CYAN + 
                    f"Enter filename (without extension) [{default_filename}]: "
                )
                filename = filename.strip() or default_filename
                
                try:
                    save_results(results, filename, fmt=export_choice)
                    await aprint(Fore.GREEN + f"Exported to output/{filename}.{export_choice}")
                except Exception as e:
                    await aprint(Fore.RED + f"Export error: {e}")
                    logger.error(f"Export error: {e}", exc_info=True)
            
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
            
            retry = await ainput(Fore.CYAN + "Try again? (y/n): ")
            if retry.strip().lower() not in ('y', 'yes'):
                return


async def _fetch_and_save_trial(
    nct: str,
    db: DatabaseManager,
    api_manager: APIManager,
    enabled_apis: List[str]
) -> Dict[str, Any]:
    """
    Fetch trial data and save to database.
    
    Args:
        nct: NCT number
        db: Database manager
        api_manager: API manager
        enabled_apis: List of enabled APIs
        
    Returns:
        Result dictionary with 'saved' status
    """
    await aprint(Fore.YELLOW + f"\n{'='*60}")
    await aprint(Fore.YELLOW + f"Fetching data for {nct}...")
    await aprint(Fore.YELLOW + f"{'='*60}\n")
    
    try:
        # Fetch clinical trial data
        result = await fetch_clinical_trial_and_pubmed_pmc(nct)
        
        if 'error' in result:
            error_msg = result.get('error', 'Unknown error')
            await aprint(Fore.RED + f"{nct}: {error_msg}")
            logger.warning(f"Failed to fetch {nct}: {error_msg}")
            return None
        
        # Print summary
        await aprint(Fore.GREEN + f"✅ Successfully fetched {nct}")
        print_study_summary(result)
        
        # Extended API search
        if enabled_apis is not None and len(enabled_apis) > 0:
            await aprint(Fore.CYAN + f"\n🔎 Running extended API search...")
            
            # Extract search parameters
            ct_data = result['sources']['clinical_trials']['data']
            protocol = ct_data.get('protocolSection', {})
            
            ident = protocol.get('identificationModule', {})
            title = (
                ident.get('officialTitle') or 
                ident.get('briefTitle') or 
                nct
            )
            
            contacts = protocol.get('contactsLocationsModule', {})
            officials = contacts.get('overallOfficials', [])
            authors = [o.get('name', '') for o in officials if o.get('name')]
            
            arms_int = protocol.get('armsInterventionsModule', {})
            interventions_list = arms_int.get('interventions', [])
            intervention_names = [
                i.get('name', '') for i in interventions_list if i.get('name')
            ]
            
            try:
                extended_results = await api_manager.search_all(
                    title=title,
                    authors=authors,
                    nct_id=nct,
                    interventions=intervention_names,
                    enabled_apis=enabled_apis
                )
                
                result['extended_apis'] = extended_results
                await aprint(Fore.GREEN + f"✅ Extended API search complete")
                
            except Exception as e:
                await aprint(Fore.RED + f"⚠️ Extended API search failed: {e}")
                logger.error(f"Extended API error for {nct}: {e}", exc_info=True)
                result['extended_apis'] = {'error': str(e)}
        
        # Save to database
        try:
            db.save_trial(nct, result, overwrite=True, backup=True)
            result['saved'] = True
            await aprint(Fore.GREEN + f"💾 Saved {nct} to ct_database/")
            logger.info(f"Saved {nct} to database")
            
        except Exception as e:
            await aprint(Fore.RED + f"⚠️ Failed to save {nct} to database: {e}")
            logger.error(f"Database save error for {nct}: {e}", exc_info=True)
            result['saved'] = False
        
        return result
        
    except Exception as e:
        await aprint(Fore.RED + f"{nct}: Unexpected error: {e}")
        logger.error(f"Error processing {nct}: {e}", exc_info=True)
        return None


async def _print_extended_api_summary(extended_results: Dict[str, Any]):
    """Print summary of extended API results."""
    summary_lines = []
    
    # Meilisearch
    if 'meilisearch' in extended_results:
        ms = extended_results['meilisearch']
        if 'hits' in ms:
            count = len(ms['hits'])
            summary_lines.append(f"    📊 Meilisearch: {count} hit(s)")
    
    # Swirl
    if 'swirl' in extended_results:
        sw = extended_results['swirl']
        if 'results' in sw:
            count = len(sw['results'])
            summary_lines.append(f"    🔄 Swirl: {count} result(s)")
    
    # OpenFDA
    openfda_events = 0
    openfda_labels = 0
    for key, value in extended_results.items():
        if key.startswith('openfda_events'):
            openfda_events += len(value.get('results', []))
        elif key.startswith('openfda_labels'):
            openfda_labels += len(value.get('results', []))
    
    if openfda_events or openfda_labels:
        summary_lines.append(
            f"    💊 OpenFDA: {openfda_events} event(s), {openfda_labels} label(s)"
        )
    
    # Health Canada
    if 'health_canada' in extended_results:
        hc = extended_results['health_canada']
        if 'results' in hc:
            count = len(hc['results'])
            summary_lines.append(f"    🍁 Health Canada: {count} trial(s)")
    
    # DuckDuckGo
    if 'duckduckgo' in extended_results:
        ddg = extended_results['duckduckgo']
        if 'results' in ddg:
            count = len(ddg['results'])
            summary_lines.append(f"    🦆 DuckDuckGo: {count} result(s)")
    
    # SERP API
    if 'serpapi_google' in extended_results:
        serp = extended_results['serpapi_google']
        if 'organic_results' in serp:
            count = len(serp['organic_results'])
            summary_lines.append(f"    🔍 Google: {count} result(s)")
    
    if 'serpapi_scholar' in extended_results:
        scholar = extended_results['serpapi_scholar']
        if 'organic_results' in scholar:
            count = len(scholar['organic_results'])
            summary_lines.append(f"    🎓 Scholar: {count} result(s)")
    
    if summary_lines:
        for line in summary_lines:
            await aprint(Fore.CYAN + line)
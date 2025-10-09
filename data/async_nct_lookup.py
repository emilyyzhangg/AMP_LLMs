"""
Async NCT (ClinicalTrials.gov) lookup module.
Uses aioconsole for non-blocking input and proper async data fetching.
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

logger = get_logger(__name__)


async def run_nct_lookup():
    """Main NCT lookup workflow with async input and concurrent fetching."""
    await aprint(
        Fore.YELLOW + Style.BRIGHT + 
        "\n=== 🔬 NCT Clinical Trial Lookup ==="
    )
    await aprint(
        Fore.WHITE + 
        "Search for clinical trials by NCT number and find related publications.\n"
    )
    
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
            
            # Fetch data concurrently
            await aprint(Fore.CYAN + f"\nProcessing {len(ncts)} NCT number(s)...")
            logger.info(f"Fetching data for: {', '.join(ncts)}")
            
            # Create tasks for concurrent fetching
            tasks = [_fetch_single_nct(nct) for nct in ncts]
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
            await aprint(Fore.CYAN + f"\nSummary of {len(results)} result(s):")
            for r in results:
                summary = summarize_result(r)
                await aprint(
                    Fore.GREEN +
                    f"  • {summary['NCT']}: " +
                    f"{summary['PubMed Count']} PubMed, " +
                    f"{summary['PMC Count']} PMC"
                )
            
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


async def _fetch_single_nct(nct: str) -> Dict[str, Any]:
    """Fetch data for a single NCT number with error handling."""
    try:
        from aioconsole import aprint
    except ImportError:
        async def aprint(*args, **kwargs):
            print(*args, **kwargs)
    
    await aprint(Fore.YELLOW + f"Fetching data for {nct}...")
    
    try:
        result = await fetch_clinical_trial_and_pubmed_pmc(nct)
        
        if 'error' in result:
            error_msg = result.get('error', 'Unknown error')
            await aprint(Fore.RED + f"{nct}: {error_msg}")
            logger.warning(f"Failed to fetch {nct}: {error_msg}")
            return None
        
        # Print summary
        await aprint(Fore.GREEN + f"Successfully fetched {nct}")
        print_study_summary(result)
        
        logger.info(f"Successfully fetched data for {nct}")
        return result
        
    except Exception as e:
        await aprint(Fore.RED + f"{nct}: Unexpected error: {e}")
        logger.error(f"Error fetching {nct}: {e}", exc_info=True)
        return None
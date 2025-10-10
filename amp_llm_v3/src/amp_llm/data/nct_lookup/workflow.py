"""
NCT Lookup workflow orchestration.
Main entry point and user interaction logic.
"""
import asyncio
from typing import List, Dict, Any
from colorama import Fore, Style

from amp_llm.cli.async_io import ainput, aprint
from amp_llm.config import get_logger
from amp_llm.data.workflows.core_fetch import (
       fetch_clinical_trial_and_pubmed_pmc,
       save_results,
)
from .api_search import run_extended_api_search, get_api_selection
from .display import (
    print_workflow_header,
    print_results_summary,
    print_extended_api_summary,
)

logger = get_logger(__name__)


async def run_nct_lookup():
    """
    Main NCT lookup workflow with ALL extended APIs.
    
    Features:
    - Fetch from ClinicalTrials.gov, PubMed, PMC
    - Optional extended API search (10+ APIs)
    - Batch processing
    - Multiple output formats
    """
    await print_workflow_header()
    
    while True:
        try:
            # Get NCT input
            nct_input = await ainput(
                Fore.CYAN + 
                "\nEnter NCT number(s), comma-separated (or 'main menu' to go back): "
            )
            nct_input = nct_input.strip()
            
            # Check for exit commands
            if await _should_exit(nct_input):
                return
            
            # Parse NCT numbers
            ncts = _parse_nct_input(nct_input)
            
            if not ncts:
                await aprint(Fore.RED + "No valid NCT numbers provided.")
                continue
            
            # Validate NCT format
            await _validate_nct_format(ncts)
            
            # Ask about extended API search
            enabled_apis = await get_api_selection()
            
            # Fetch data concurrently
            await aprint(Fore.CYAN + f"\n🔍 Processing {len(ncts)} NCT number(s)...")
            logger.info(f"Fetching data for: {', '.join(ncts)}")
            
            # Create tasks for concurrent fetching
            tasks = [
                _fetch_single_nct(nct, enabled_apis) 
                for nct in ncts
            ]
            results_with_status = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Filter valid results
            results = await _filter_valid_results(results_with_status, ncts)
            
            if not results:
                await aprint(Fore.RED + "No results found for any NCT numbers.")
                continue
            
            # Show summary
            await print_results_summary(results, enabled_apis)
            
            # Offer to save
            await _handle_save_results(results)
            
            # Ask to continue
            if not await _should_continue():
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


async def _should_exit(user_input: str) -> bool:
    """Check if user wants to exit."""
    if user_input.lower() in ('main menu', 'exit', 'quit', 'back', ''):
        await aprint(Fore.YELLOW + "Returning to main menu...")
        logger.info("User returned to main menu from NCT lookup")
        return True
    return False


def _parse_nct_input(nct_input: str) -> List[str]:
    """Parse comma-separated NCT numbers."""
    return [n.strip().upper() for n in nct_input.split(',') if n.strip()]


async def _validate_nct_format(ncts: List[str]) -> None:
    """Validate NCT number format."""
    for nct in ncts:
        if not nct.startswith('NCT'):
            await aprint(
                Fore.YELLOW + 
                f"'{nct}' doesn't look like a valid NCT number, but will try..."
            )


async def _fetch_single_nct(nct: str, enabled_apis: List[str]) -> Dict[str, Any]:
    """
    Fetch data for a single NCT number with optional extended APIs.
    
    Args:
        nct: NCT number
        enabled_apis: List of APIs to use (empty = no extended search)
        
    Returns:
        Combined result dictionary
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
        
        await aprint(Fore.GREEN + f"✅ Successfully fetched {nct}")
        
        # Step 2: Extended API search (if enabled)
        if enabled_apis:
            extended_results = await run_extended_api_search(nct, result, enabled_apis)
            result['extended_apis'] = extended_results
            
            await aprint(Fore.GREEN + f"\n✅ Extended API search complete for {nct}")
            await print_extended_api_summary(extended_results)
        
        logger.info(f"Successfully fetched complete data for {nct}")
        return result
        
    except KeyboardInterrupt:
        await aprint(Fore.YELLOW + f"\n⚠️ Fetch cancelled for {nct}")
        raise
    except Exception as e:
        await aprint(Fore.RED + f"{nct}: Unexpected error: {e}")
        logger.error(f"Error fetching {nct}: {e}", exc_info=True)
        return None


async def _filter_valid_results(
    results_with_status: List[Any], 
    ncts: List[str]
) -> List[Dict[str, Any]]:
    """Filter out exceptions and invalid results."""
    results = []
    
    for i, result in enumerate(results_with_status):
        if isinstance(result, Exception):
            await aprint(Fore.RED + f"Exception for {ncts[i]}: {result}")
            logger.error(f"Exception for {ncts[i]}", exc_info=result)
        elif result is not None:
            results.append(result)
    
    return results


async def _handle_save_results(results: List[Dict[str, Any]]) -> None:
    """Handle saving results to file."""
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


async def _should_continue() -> bool:
    """Ask if user wants to continue with more lookups."""
    choice = await ainput(Fore.CYAN + "\nLookup more NCTs? (y/n): ")
    return choice.strip().lower() in ('y', 'yes')
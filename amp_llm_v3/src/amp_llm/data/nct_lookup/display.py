"""
Display and formatting utilities for NCT lookup results.
FIXED: Corrected import path for summarize_result
"""
from typing import List, Dict, Any
from colorama import Fore, Style

from amp_llm.cli.async_io import aprint
# FIXED: Import from workflows.core_fetch instead of clinical_trials.fetchers
from amp_llm.data.workflows.core_fetch import summarize_result


async def print_workflow_header():
    """Print NCT lookup workflow header."""
    await aprint(
        Fore.YELLOW + Style.BRIGHT + 
        "\n=== 🔬 NCT Clinical Trial Lookup ==="
    )
    await aprint(
        Fore.WHITE + 
        "Search for clinical trials by NCT number and find related publications.\n"
    )


async def print_results_summary(
    results: List[Dict[str, Any]], 
    enabled_apis: List[str]
):
    """
    Print summary of all fetched results.
    
    Args:
        results: List of trial results
        enabled_apis: List of enabled APIs (empty = no extended search)
    """
    await aprint(Fore.CYAN + f"\n📊 Summary of {len(results)} result(s):")
    
    for r in results:
        summary = summarize_result(r)
        
        # Basic summary
        await aprint(
            Fore.GREEN +
            f"  • {summary['NCT']}: " +
            f"{summary['PubMed Count']} PubMed, " +
            f"{summary['PMC Count']} PMC"
        )
        
        # Extended API summary
        if enabled_apis and 'extended_apis' in r:
            ext = r['extended_apis']
            api_counts = _count_extended_results(ext)
            
            if api_counts:
                await aprint(Fore.CYAN + f"    Extended: {', '.join(api_counts)}")


async def print_extended_api_summary(extended_results: Dict[str, Any]):
    """
    Print summary of extended API results.
    
    Args:
        extended_results: Results from APIManager.search_all()
    """
    summary_lines = []
    
    # PMC Full Text
    if 'pmc_fulltext' in extended_results:
        pmc = extended_results['pmc_fulltext']
        if 'pmcids' in pmc:
            count = len(pmc['pmcids'])
            summary_lines.append(f"  📄 PMC Full Text: {count} article(s)")
    
    # EudraCT
    if 'eudract' in extended_results:
        eu = extended_results['eudract']
        if 'results' in eu:
            count = len(eu['results'])
            summary_lines.append(f"  🇪🇺 EudraCT: {count} trial(s)")
    
    # WHO ICTRP
    if 'who_ictrp' in extended_results:
        who = extended_results['who_ictrp']
        if 'results' in who:
            count = len(who['results'])
            summary_lines.append(f"  🌍 WHO ICTRP: {count} trial(s)")
    
    # Semantic Scholar
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


def _count_extended_results(extended: Dict[str, Any]) -> List[str]:
    """
    Count results from each extended API.
    
    Returns:
        List of formatted count strings
    """
    api_counts = []
    
    # PMC Full Text
    if 'pmc_fulltext' in extended and extended['pmc_fulltext'].get('pmcids'):
        count = len(extended['pmc_fulltext']['pmcids'])
        api_counts.append(f"{count} PMC Full Text")
    
    # EudraCT
    if 'eudract' in extended and extended['eudract'].get('results'):
        count = len(extended['eudract']['results'])
        api_counts.append(f"{count} EudraCT")
    
    # WHO ICTRP
    if 'who_ictrp' in extended and extended['who_ictrp'].get('results'):
        count = len(extended['who_ictrp']['results'])
        api_counts.append(f"{count} WHO ICTRP")
    
    # Semantic Scholar
    if 'semantic_scholar' in extended and extended['semantic_scholar'].get('papers'):
        count = len(extended['semantic_scholar']['papers'])
        api_counts.append(f"{count} Semantic Scholar")
    
    return api_counts
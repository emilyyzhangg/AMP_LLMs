"""
Clinical trial data fetching coordinator.

DEPRECATED: This module is maintained for backward compatibility.
New code should use: amp_llm.data.workflows.core_fetch

Orchestrates fetching from multiple sources:
- ClinicalTrials.gov API
- PubMed (NCBI E-utilities)
- PubMed Central (PMC)
"""
import warnings
from typing import Dict, List, Any

# Import individual fetchers
from .clinical_trials import fetch_clinical_trial_data
from .pubmed import (
    fetch_pubmed_by_pmid,
    search_pubmed_esearch,
    search_pubmed_by_title_authors,
)
from .pmc import (
    search_pmc,
    fetch_pmc_esummary,
    convert_pmc_summary_to_metadata,
)

# Import new workflow functions
from amp_llm.data.workflows.core_fetch import (
    fetch_clinical_trial_and_pubmed_pmc as _new_fetch,
    print_study_summary as _new_print,
    summarize_result as _new_summarize,
    save_results as _new_save,
)

# Show deprecation warning
warnings.warn(
    "amp_llm.data.clinical_trials.fetchers.coordinator is deprecated. "
    "Use amp_llm.data.workflows.core_fetch instead.",
    DeprecationWarning,
    stacklevel=2
)


# Re-export new functions for backward compatibility
async def fetch_clinical_trial_and_pubmed_pmc(nct_id: str) -> Dict[str, Any]:
    """
    DEPRECATED: Use amp_llm.data.workflows.core_fetch.fetch_clinical_trial_and_pubmed_pmc
    
    This function is maintained for backward compatibility only.
    """
    return await _new_fetch(nct_id)


def print_study_summary(result: Dict[str, Any]) -> None:
    """
    DEPRECATED: Use amp_llm.data.workflows.core_fetch.print_study_summary
    
    This function is maintained for backward compatibility only.
    """
    return _new_print(result)


def summarize_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    DEPRECATED: Use amp_llm.data.workflows.core_fetch.summarize_result
    
    This function is maintained for backward compatibility only.
    """
    return _new_summarize(result)


def save_results(results: List[Dict[str, Any]], filename: str, fmt: str = 'txt') -> None:
    """
    DEPRECATED: Use amp_llm.data.workflows.core_fetch.save_results
    
    This function is maintained for backward compatibility only.
    """
    return _new_save(results, filename, fmt)
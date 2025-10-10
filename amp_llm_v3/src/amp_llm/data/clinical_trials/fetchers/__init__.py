"""
Clinical trial data fetchers package.

UPDATED: Now delegates to workflows package for orchestration.
Individual fetchers remain here for direct API access.
"""

# Individual fetchers (still here for direct use)
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

# Coordinator functions (now from workflows)
from amp_llm.data.workflows.core_fetch import (
    fetch_clinical_trial_and_pubmed_pmc,
    print_study_summary,
    summarize_result,
    save_results,
)

__all__ = [
    # Individual fetchers
    'fetch_clinical_trial_data',
    'fetch_pubmed_by_pmid',
    'search_pubmed_esearch',
    'search_pubmed_by_title_authors',
    'search_pmc',
    'fetch_pmc_esummary',
    'convert_pmc_summary_to_metadata',
    
    # Coordinator functions (delegated to workflows)
    'fetch_clinical_trial_and_pubmed_pmc',
    'print_study_summary',
    'summarize_result',
    'save_results',
]

__version__ = '3.0.0'
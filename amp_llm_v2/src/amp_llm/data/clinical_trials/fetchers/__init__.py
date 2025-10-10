"""
Clinical trial data fetchers package.

Modularized fetchers for:
- ClinicalTrials.gov API
- PubMed (NCBI E-utilities)
- PubMed Central (PMC)
- Coordination and result aggregation
"""

# Import from individual modules
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
from .coordinator import (
    fetch_clinical_trial_and_pubmed_pmc,
    print_study_summary,
    summarize_result,
    save_results,
)

__all__ = [
    # ClinicalTrials.gov
    'fetch_clinical_trial_data',
    
    # PubMed
    'fetch_pubmed_by_pmid',
    'search_pubmed_esearch',
    'search_pubmed_by_title_authors',
    
    # PMC
    'search_pmc',
    'fetch_pmc_esummary',
    'convert_pmc_summary_to_metadata',
    
    # Coordinator (main entry point)
    'fetch_clinical_trial_and_pubmed_pmc',
    'print_study_summary',
    'summarize_result',
    'save_results',
]

__version__ = '3.0.0'
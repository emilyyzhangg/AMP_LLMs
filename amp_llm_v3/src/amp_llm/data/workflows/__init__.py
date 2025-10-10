"""
Clinical trial data fetching workflows.

Provides high-level workflows that orchestrate API clients:
- core_fetch: Basic trial data (ClinicalTrials.gov + PubMed + PMC)
- extended_fetch: Enhanced with additional APIs (EudraCT, WHO, etc.)
"""
from .core_fetch import fetch_clinical_trial_and_pubmed_pmc
from .extended_fetch import fetch_with_extended_apis

__all__ = [
    'fetch_clinical_trial_and_pubmed_pmc',
    'fetch_with_extended_apis',
]
"""
High-level workflows for data fetching.

Workflows orchestrate multiple API clients to complete complex tasks.
"""
from .core_fetch import (
    fetch_clinical_trial_and_pubmed_pmc,
    print_study_summary,
    summarize_result,
    save_results,
)

try:
    from .extended_fetch import (
        fetch_with_extended_apis,
        batch_fetch_with_extended,
    )
    HAS_EXTENDED_WORKFLOWS = True
except ImportError:
    HAS_EXTENDED_WORKFLOWS = False

__all__ = [
    # Core workflow
    'fetch_clinical_trial_and_pubmed_pmc',
    'print_study_summary',
    'summarize_result',
    'save_results',
    # Extended (conditional)
    'fetch_with_extended_apis',
    'batch_fetch_with_extended',
    'HAS_EXTENDED_WORKFLOWS',
]
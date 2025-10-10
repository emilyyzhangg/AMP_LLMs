"""
API clients for external data sources.

Architecture:
- core/: Essential APIs (ClinicalTrials.gov, PubMed, PMC)
- extended/: Optional APIs (Semantic Scholar, EudraCT, etc.)
"""
from .base import BaseAPIClient

# Core clients
from .core.clinical_trials import ClinicalTrialsClient
from .core.pubmed import PubMedClient
from .core.pmc_basic import PMCBasicClient

# Extended clients (optional)
try:
    from .extended.pmc_fulltext import PMCFullTextClient
    from .extended.eudract import EudraCTClient
    from .extended.who_ictrp import WHOICTRPClient
    from .extended.semantic_scholar import SemanticScholarClient
    HAS_EXTENDED = True
except ImportError:
    HAS_EXTENDED = False

__all__ = [
    'BaseAPIClient',
    # Core
    'ClinicalTrialsClient',
    'PubMedClient',
    'PMCBasicClient',
    # Extended (conditional)
    'PMCFullTextClient',
    'EudraCTClient',
    'WHOICTRPClient',
    'SemanticScholarClient',
    'HAS_EXTENDED',
]
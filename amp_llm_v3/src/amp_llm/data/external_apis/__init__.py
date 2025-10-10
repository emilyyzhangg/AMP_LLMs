"""
External APIs package for clinical trial research.
"""

# New modular API clients
from .pmc_fulltext import PMCFullTextClient
from .eudract import EudraCTClient
from .who_ictrp import WHOICTRPClient
from .semantic_scholar import SemanticScholarClient

__all__ = [
    'PMCFullTextClient',
    'EudraCTClient',
    'WHOICTRPClient',
    'SemanticScholarClient',
]

__version__ = '1.0.0'
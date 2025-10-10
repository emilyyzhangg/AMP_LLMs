"""
External APIs package for clinical trial research.
FIXED: Correct import paths from api_clients.extended
"""

# Import from the correct location: api_clients.extended
from amp_llm.data.api_clients.extended.pmc_fulltext import PMCFullTextClient
from amp_llm.data.api_clients.extended.eudract import EudraCTClient
from amp_llm.data.api_clients.extended.who_ictrp import WHOICTRPClient
from amp_llm.data.api_clients.extended.semantic_scholar import SemanticScholarClient


__all__ = [
    'PMCFullTextClient',
    'EudraCTClient',
    'WHOICTRPClient',
    'SemanticScholarClient',
]

__version__ = '1.0.0'
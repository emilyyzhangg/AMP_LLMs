"""
Abstract base classes for research and annotation agents.
"""

from abc import ABC, abstractmethod
from typing import Optional

from app.models.research import ResearchResult, SourceCitation
from app.models.annotation import FieldAnnotation

# Source reliability weights - used to compute quality scores
SOURCE_WEIGHTS = {
    "clinicaltrials_gov": 0.95,
    "openfda": 0.85,
    "pubmed": 0.90,
    "pmc": 0.85,
    "pmc_bioc": 0.80,
    "uniprot": 0.95,
    "dramp": 0.80,
    "duckduckgo": 0.40,
    "serpapi": 0.50,
    "scholar": 0.70,
}

# How relevant each research agent is to each annotation field (0-1)
FIELD_RELEVANCE = {
    "classification": {
        "clinical_protocol": 0.95,
        "literature": 0.80,
        "peptide_identity": 0.30,
        "web_context": 0.50,
    },
    "delivery_mode": {
        "clinical_protocol": 0.90,
        "literature": 0.85,
        "peptide_identity": 0.40,
        "web_context": 0.45,
    },
    "outcome": {
        "clinical_protocol": 0.90,
        "literature": 0.75,
        "peptide_identity": 0.20,
        "web_context": 0.60,
    },
    "reason_for_failure": {
        "clinical_protocol": 0.60,
        "literature": 0.70,
        "peptide_identity": 0.15,
        "web_context": 0.80,
    },
    "peptide": {
        "clinical_protocol": 0.50,
        "literature": 0.75,
        "peptide_identity": 0.95,
        "web_context": 0.40,
    },
}


class BaseResearchAgent(ABC):
    """Abstract base class for all research agents."""

    agent_name: str = "base"
    sources: list[str] = []

    @abstractmethod
    async def research(self, nct_id: str, metadata: Optional[dict] = None) -> ResearchResult:
        """Execute research for a given NCT ID and return structured results."""
        ...

    def compute_quality_score(self, source_name: str, has_content: bool = True) -> float:
        """Compute a quality score for a citation based on source reliability."""
        base = SOURCE_WEIGHTS.get(source_name, 0.5)
        if not has_content:
            base *= 0.5
        return round(min(base, 1.0), 3)


class BaseAnnotationAgent(ABC):
    """Abstract base class for annotation agents (LLM-driven field annotators)."""

    field_name: str = "base"

    @abstractmethod
    async def annotate(
        self,
        nct_id: str,
        research_results: list[ResearchResult],
        metadata: Optional[dict] = None,
    ) -> FieldAnnotation:
        """Produce an annotation for self.field_name using gathered research."""
        ...

    def relevance_weight(self, agent_name: str) -> float:
        """How relevant a given research agent is to this annotation field."""
        return FIELD_RELEVANCE.get(self.field_name, {}).get(agent_name, 0.5)

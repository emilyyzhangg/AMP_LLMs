"""
Models for research agent outputs.
"""

from typing import Optional
from pydantic import BaseModel


class SourceCitation(BaseModel):
    """A single piece of evidence from one source."""
    source_name: str           # e.g. "clinicaltrials_gov", "pubmed"
    source_url: Optional[str] = None
    identifier: Optional[str] = None   # PMID, NCT ID, UniProt accession, etc.
    title: Optional[str] = None
    snippet: str = ""          # Relevant excerpt
    quality_score: float = 0.0  # 0.0 - 1.0, set by the research agent
    retrieved_at: Optional[str] = None


class ResearchResult(BaseModel):
    """Aggregated output from one research agent for one trial."""
    agent_name: str            # e.g. "clinical_protocol"
    nct_id: str
    citations: list[SourceCitation] = []
    raw_data: dict = {}        # Full API response for auditing
    error: Optional[str] = None

"""
Models for multi-model verification consensus.
"""

from typing import Optional
from pydantic import BaseModel


class ModelOpinion(BaseModel):
    """One verifier model's opinion on a field annotation."""
    model_name: str
    agrees: bool
    suggested_value: Optional[str] = None
    reasoning: str = ""
    confidence: float = 0.0


class ConsensusResult(BaseModel):
    """Consensus outcome for a single field."""
    field_name: str
    original_value: str
    final_value: str
    consensus_reached: bool
    agreement_ratio: float = 0.0   # e.g. 3/3 = 1.0
    opinions: list[ModelOpinion] = []
    reconciler_used: bool = False
    reconciler_reasoning: Optional[str] = None
    flag_reason: Optional[str] = None


class VerifiedAnnotation(BaseModel):
    """Fully verified annotation for one trial."""
    nct_id: str
    fields: list[ConsensusResult] = []
    overall_consensus: bool = True
    flagged_for_review: bool = False
    flag_reason: Optional[str] = None

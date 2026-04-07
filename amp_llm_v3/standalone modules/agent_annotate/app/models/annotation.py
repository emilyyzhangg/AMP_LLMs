"""
Models for annotation outputs (per-field LLM decisions).
"""

from typing import Optional
from pydantic import BaseModel
from app.models.research import SourceCitation


class FieldAnnotation(BaseModel):
    """One LLM-generated annotation for a single field."""
    field_name: str            # e.g. "classification", "delivery_mode"
    value: str                 # The annotation value
    confidence: float = 0.0   # Model self-reported confidence 0-1
    reasoning: str = ""        # Chain-of-thought explanation
    evidence: list[SourceCitation] = []
    model_name: str = ""       # Which model produced this
    skip_verification: bool = False  # v9: deterministic pre-classifiers set True to bypass blind verification
    evidence_grade: str = "llm"  # v31: "deterministic", "db_confirmed", or "llm"


class TrialMetadata(BaseModel):
    """Basic metadata about the trial being annotated."""
    nct_id: str
    title: Optional[str] = None
    phase: Optional[str] = None
    status: Optional[str] = None
    conditions: list[str] = []
    interventions: list[str] = []


class AnnotationResult(BaseModel):
    """Complete annotation output for one trial, before verification."""
    metadata: TrialMetadata
    annotations: list[FieldAnnotation] = []
    research_used: list[str] = []  # Names of research agents that contributed

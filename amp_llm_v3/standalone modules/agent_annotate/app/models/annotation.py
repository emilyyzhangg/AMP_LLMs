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
    # v31: original 3-tier grading.
    # v42.7.1 (2026-04-26): extended to 5-tier per roadmap §11 calibrated-decline
    # phase 1. In ranked confidence order:
    #   "db_confirmed"        — annotation backed by an authoritative database
    #                            (UniProt/DRAMP/DBAASP/ChEMBL/APD/RCSB/SEC EDGAR/
    #                            FDA Drugs) citation in evidence list.
    #   "deterministic"       — set by skip_verification=True paths (cascade,
    #                            registry-status mapping, known-sequence lookup).
    #   "pub_trial_specific"  — LLM-driven annotation with ≥2 trial-specific
    #                            publication citations supporting it.
    #   "llm"                 — LLM-driven annotation with verifier consensus
    #                            but fewer than 2 pub citations (default).
    #   "inconclusive"        — empty value or no reasoning; downstream
    #                            consumers should filter these out.
    # Only metadata — does NOT change annotation value. For commit_accuracy
    # scoring, downstream filters by grade ≥ "pub_trial_specific" or
    # ≥ "deterministic" depending on the precision/recall trade-off needed.
    evidence_grade: str = "llm"


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

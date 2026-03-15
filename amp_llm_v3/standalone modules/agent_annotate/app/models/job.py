"""
Models for annotation pipeline jobs.
"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class JobProgress(BaseModel):
    """Progress tracking within a running job."""
    total_trials: int = 0
    completed_trials: int = 0
    current_nct_id: Optional[str] = None
    current_stage: str = "queued"  # queued | researching | annotating | verifying | done | error
    errors: list[str] = []
    elapsed_seconds: float = 0.0           # Total wall time so far
    avg_seconds_per_trial: float = 0.0     # Running average per completed trial
    estimated_remaining_seconds: float = 0.0  # Estimated time left
    researched_trials: int = 0             # Phase 1 counter
    current_phase: str = ""                # "research" | "annotation" | ""


class AnnotationJob(BaseModel):
    """A single annotation pipeline run."""
    job_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "queued"  # queued | running | completed | failed | cancelled
    nct_ids: list[str] = []
    config_snapshot: dict = {}  # Frozen copy of config at job start
    progress: JobProgress = Field(default_factory=JobProgress)
    results: list[dict] = []  # List of VerifiedAnnotation dicts
    error: Optional[str] = None
    resumed: bool = False
    resumed_at: Optional[datetime] = None


class JobSummary(BaseModel):
    """Lightweight job info for listing."""
    job_id: str
    status: str
    created_at: datetime
    total_trials: int = 0
    completed_trials: int = 0
    researched_trials: int = 0


class ReviewItem(BaseModel):
    """A single field flagged for human review."""
    job_id: str
    nct_id: str
    field_name: str
    original_value: str
    suggested_values: list[str] = []
    opinions: list[dict] = []
    status: str = "pending"  # pending | approved | overridden | skipped
    reviewer_value: Optional[str] = None
    reviewer_note: Optional[str] = None

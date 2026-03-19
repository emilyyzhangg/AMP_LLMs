"""
Models for annotation pipeline jobs.
"""

from typing import Optional
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel, Field

# Pacific timezone (America/Los_Angeles)
# Using a fixed UTC-8 / UTC-7 via zoneinfo when available, else fallback.
try:
    from zoneinfo import ZoneInfo
    PACIFIC_TZ = ZoneInfo("America/Los_Angeles")
except ImportError:
    # Fallback for older Python without zoneinfo
    PACIFIC_TZ = timezone(timedelta(hours=-8))


def now_pacific() -> datetime:
    """Return the current datetime in Pacific time (America/Los_Angeles)."""
    return datetime.now(PACIFIC_TZ)


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
    created_at: datetime = Field(default_factory=now_pacific)
    updated_at: datetime = Field(default_factory=now_pacific)
    status: str = "queued"  # queued | running | completed | failed | cancelled
    nct_ids: list[str] = []
    config_snapshot: dict = {}  # Frozen copy of config at job start
    progress: JobProgress = Field(default_factory=JobProgress)
    results: list[dict] = []  # List of VerifiedAnnotation dicts
    error: Optional[str] = None
    resumed: bool = False
    resumed_at: Optional[datetime] = None
    # Timing metadata
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    commit_hash: str = ""
    timezone: str = "America/Los_Angeles"


class JobSummary(BaseModel):
    """Lightweight job info for listing."""
    job_id: str
    status: str
    created_at: datetime
    total_trials: int = 0
    completed_trials: int = 0
    researched_trials: int = 0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    elapsed_seconds: float = 0.0
    avg_seconds_per_trial: float = 0.0
    commit_hash: str = ""


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
    primary_reasoning: str = ""
    primary_confidence: float = 0.0
    created_at: Optional[str] = None
    commit_hash: str = ""

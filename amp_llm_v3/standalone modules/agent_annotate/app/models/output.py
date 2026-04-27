"""
Models for final output, versioning, and audit trail.
"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field

from app.models.job import now_pacific


class VersionInfo(BaseModel):
    """Build / version metadata stamped on every output.

    ``git_commit_*`` reflects the on-disk HEAD at the moment this struct
    was built — it changes the instant the autoupdater pulls.
    ``boot_commit_*`` is the commit the running Python process was
    loaded from; it does not change until the process is restarted.
    A divergence (``code_in_sync = False``) means a smoke validation
    is running against stale in-memory code despite the new commit
    being on disk.
    """
    semantic_version: str
    git_commit_short: str
    git_commit_full: str
    boot_commit_short: str = ""
    boot_commit_full: str = ""
    code_in_sync: bool = True
    config_hash: str = ""


class AuditEntry(BaseModel):
    """One step in the audit trail for a trial's annotation."""
    timestamp: datetime = Field(default_factory=now_pacific)
    stage: str  # "research" | "annotation" | "verification" | "review"
    agent_or_model: str
    action: str
    detail: str = ""


class JobOutput(BaseModel):
    """Final output package for one job."""
    job_id: str
    version: VersionInfo
    completed_at: datetime = Field(default_factory=now_pacific)
    trials: list[dict] = []  # List of VerifiedAnnotation dicts
    audit_trail: list[AuditEntry] = []


class CSVExportRequest(BaseModel):
    """Request body for CSV export."""
    job_id: str
    format: str = "standard"  # "standard" | "full"
    include_evidence: bool = False

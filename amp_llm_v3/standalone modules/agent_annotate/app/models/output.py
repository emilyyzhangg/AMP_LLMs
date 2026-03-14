"""
Models for final output, versioning, and audit trail.
"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class VersionInfo(BaseModel):
    """Build / version metadata stamped on every output."""
    semantic_version: str
    git_commit_short: str
    git_commit_full: str
    config_hash: str = ""


class AuditEntry(BaseModel):
    """One step in the audit trail for a trial's annotation."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    stage: str  # "research" | "annotation" | "verification" | "review"
    agent_or_model: str
    action: str
    detail: str = ""


class JobOutput(BaseModel):
    """Final output package for one job."""
    job_id: str
    version: VersionInfo
    completed_at: datetime = Field(default_factory=datetime.utcnow)
    trials: list[dict] = []  # List of VerifiedAnnotation dicts
    audit_trail: list[AuditEntry] = []


class CSVExportRequest(BaseModel):
    """Request body for CSV export."""
    job_id: str
    format: str = "standard"  # "standard" | "full"
    include_evidence: bool = False

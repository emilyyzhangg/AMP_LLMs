"""
Models for job resume validation.
"""

from pydantic import BaseModel


class ResumeValidation(BaseModel):
    """Result of validating whether a job can be resumed."""
    can_resume: bool
    commit_match: bool
    original_commit: str
    current_commit: str
    config_match: bool
    research_completed: int
    research_total: int
    annotations_completed: int
    warnings: list[str] = []

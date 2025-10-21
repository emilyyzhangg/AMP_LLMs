"""
NCT API Data Models
==================

Pydantic models for request/response validation.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class SearchRequest(BaseModel):
    """Request model for NCT search."""
    
    include_extended: bool = Field(
        default=False,
        description="Include extended databases (DuckDuckGo, SERP, Scholar, OpenFDA)"
    )
    
    databases: Optional[List[str]] = Field(
        default=None,
        description="Specific databases to search (if None, searches all available)"
    )
    
    @field_validator('databases')
    @classmethod
    def validate_databases(cls, v):
        """Validate database names."""
        if v is not None:
            valid_databases = [
                'duckduckgo', 'serpapi', 'scholar', 'openfda'
            ]
            invalid = [db for db in v if db not in valid_databases]
            if invalid:
                raise ValueError(
                    f"Invalid databases: {invalid}. "
                    f"Valid options: {valid_databases}"
                )
        return v


class SearchResponse(BaseModel):
    """Response model for search initiation."""
    
    job_id: str = Field(description="NCT number used as job ID")
    status: str = Field(description="Current status (queued, running, completed, failed)")
    message: str = Field(description="Human-readable status message")
    created_at: datetime = Field(description="Search creation timestamp")


class SearchStatus(BaseModel):
    """Model for tracking search status."""
    
    job_id: str
    status: str  # queued, running, completed, failed
    progress: int = Field(default=0, ge=0, le=100)
    current_database: Optional[str] = None
    completed_databases: List[str] = Field(default_factory=list)
    databases_to_search: List[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: Optional[datetime] = None
    error: Optional[str] = None


class SearchSummary(BaseModel):
    """Summary statistics for search results."""
    
    nct_id: str
    title: str
    status: str
    databases_searched: List[str]
    total_results: int
    results_by_database: Dict[str, int]
    search_timestamp: str
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "nct_id": "NCT12345678",
                "title": "Study of Drug X in Disease Y",
                "status": "RECRUITING",
                "databases_searched": [
                    "clinicaltrials",
                    "pubmed",
                    "pmc",
                    "duckduckgo"
                ],
                "total_results": 15,
                "results_by_database": {
                    "clinicaltrials": 1,
                    "pubmed": 5,
                    "pmc": 3,
                    "duckduckgo": 6
                },
                "search_timestamp": "2025-01-15T10:30:00"
            }
        }
    }


class SearchConfig(BaseModel):
    """Configuration for search execution."""
    
    use_extended_apis: bool = False
    enabled_databases: Optional[List[str]] = None
    max_results_per_db: int = Field(default=10, ge=1, le=100)
    timeout: int = Field(default=60, ge=10, le=300)
    
    model_config = {
        "use_enum_values": True
    }
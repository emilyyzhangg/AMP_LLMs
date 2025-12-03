"""
NCT API Extended Data Models
============================

Pydantic models for 2-step NCT lookup workflow.
Extends the existing models with Step 1 and Step 2 specific structures.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# ============================================================================
# Step 1 Models
# ============================================================================

class Step1Request(BaseModel):
    """Request model for Step 1 search."""
    
    # No additional parameters needed - just the NCT ID from URL
    pass


class SearchRecord(BaseModel):
    """Detailed record of a single search operation."""
    
    search_type: str = Field(description="Type of search (e.g., 'nct_id', 'title', 'reference')")
    query: str = Field(description="Actual query string used")
    timestamp: str = Field(description="ISO timestamp of search")
    status: str = Field(description="Status: 'success' or 'error'")
    results_count: int = Field(description="Number of results found")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Result data if successful")


class CoreAPIResult(BaseModel):
    """Result from a core API search."""
    
    success: bool = Field(description="Whether search was successful")
    searches: List[SearchRecord] = Field(description="List of all searches performed")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Combined data from all searches")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    total_results: int = Field(default=0, description="Total number of results")


class Step1Response(BaseModel):
    """Response model for Step 1 search."""
    
    nct_id: str = Field(description="NCT identifier")
    step: int = Field(default=1, description="Step number")
    timestamp: str = Field(description="ISO timestamp")
    metadata: Dict[str, Any] = Field(description="Extracted metadata (title, condition, intervention, etc.)")
    core_apis: Dict[str, CoreAPIResult] = Field(description="Results from each core API")
    summary: Dict[str, Any] = Field(description="Summary statistics")
    error: Optional[str] = Field(default=None, description="Error message if Step 1 failed")


# ============================================================================
# Step 2 Models
# ============================================================================

class Step2Request(BaseModel):
    """Request model for Step 2 search."""
    
    selected_apis: List[str] = Field(
        description="List of extended API IDs to search",
        examples=[["duckduckgo", "openfda"]]
    )
    
    field_selections: Dict[str, List[str]] = Field(
        description="Map of API ID to list of field names to search",
        examples=[{
            "duckduckgo": ["title", "condition"],
            "openfda": ["intervention"]
        }]
    )
    
    @field_validator('selected_apis')
    @classmethod
    def validate_apis(cls, v):
        """Validate API names."""
        valid_apis = ['duckduckgo', 'serpapi', 'scholar', 'openfda']
        invalid = [api for api in v if api not in valid_apis]
        if invalid:
            raise ValueError(
                f"Invalid APIs: {invalid}. "
                f"Valid options: {valid_apis}"
            )
        return v
    
    @field_validator('field_selections')
    @classmethod
    def validate_field_selections(cls, v):
        """Validate field selections."""
        valid_fields = [
            'title', 'nct_id', 'condition', 'intervention', 
            'intervention_names', 'authors', 'pmid', 'pmids'
        ]
        
        for api_id, fields in v.items():
            invalid_fields = [f for f in fields if f not in valid_fields]
            if invalid_fields:
                raise ValueError(
                    f"Invalid fields for {api_id}: {invalid_fields}. "
                    f"Valid options: {valid_fields}"
                )
        
        return v


class ExtendedSearchRecord(BaseModel):
    """Detailed record of an extended API search."""
    
    search_number: int = Field(description="Sequential search number")
    fields_used: Dict[str, str] = Field(description="Fields and values used in this search")
    query: str = Field(description="Combined query string")
    description: str = Field(description="Human-readable search description")
    timestamp: str = Field(description="ISO timestamp")
    status: str = Field(description="Status: 'success' or 'error'")
    results_count: int = Field(description="Number of results found")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Result data")


class ExtendedAPIResult(BaseModel):
    """Result from an extended API search."""
    
    success: bool = Field(description="Whether any search was successful")
    searches: List[ExtendedSearchRecord] = Field(description="List of all searches performed")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Combined and deduplicated data")
    error: Optional[str] = Field(default=None, description="Error message if all failed")
    total_results: int = Field(default=0, description="Total unique results")


class Step2Response(BaseModel):
    """Response model for Step 2 search."""
    
    nct_id: str = Field(description="NCT identifier")
    step: int = Field(default=2, description="Step number")
    timestamp: str = Field(description="ISO timestamp")
    step1_reference: Optional[str] = Field(description="Timestamp of Step 1 results used")
    selected_apis: List[str] = Field(description="APIs that were searched")
    field_selections: Dict[str, List[str]] = Field(description="Fields used for each API")
    extended_apis: Dict[str, ExtendedAPIResult] = Field(description="Results from each extended API")
    summary: Dict[str, Any] = Field(description="Summary statistics")


# ============================================================================
# Combined Results Model
# ============================================================================

class CombinedNCTResults(BaseModel):
    """Combined results from both Step 1 and Step 2."""
    
    nct_id: str = Field(description="NCT identifier")
    timestamp: str = Field(description="ISO timestamp")
    step1: Step1Response = Field(description="Step 1 core API results")
    step2: Optional[Step2Response] = Field(default=None, description="Step 2 extended API results (if executed)")
    
    combined_summary: Dict[str, Any] = Field(description="Combined summary statistics")


# ============================================================================
# Status Models
# ============================================================================

class SearchStepStatus(str, Enum):
    """Status of a search step."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Step1Status(BaseModel):
    """Status model for Step 1 search."""
    
    nct_id: str = Field(description="NCT identifier")
    status: SearchStepStatus = Field(description="Current status")
    progress: int = Field(default=0, ge=0, le=100, description="Progress percentage")
    current_api: Optional[str] = Field(default=None, description="Currently searching API")
    completed_apis: List[str] = Field(default_factory=list, description="Completed APIs")
    message: str = Field(default="", description="Status message")
    created_at: datetime = Field(description="Creation timestamp")
    updated_at: Optional[datetime] = Field(default=None, description="Last update timestamp")
    error: Optional[str] = Field(default=None, description="Error message if failed")


class Step2Status(BaseModel):
    """Status model for Step 2 search."""
    
    nct_id: str = Field(description="NCT identifier")
    status: SearchStepStatus = Field(description="Current status")
    progress: int = Field(default=0, ge=0, le=100, description="Progress percentage")
    current_api: Optional[str] = Field(default=None, description="Currently searching API")
    current_search: Optional[str] = Field(default=None, description="Current search description")
    completed_apis: List[str] = Field(default_factory=list, description="Completed APIs")
    total_searches: int = Field(default=0, description="Total searches planned")
    completed_searches: int = Field(default=0, description="Completed searches")
    message: str = Field(default="", description="Status message")
    created_at: datetime = Field(description="Creation timestamp")
    updated_at: Optional[datetime] = Field(default=None, description="Last update timestamp")
    error: Optional[str] = Field(default=None, description="Error message if failed")


# ============================================================================
# Backward Compatibility Models (keep existing)
# ============================================================================

class SearchRequest(BaseModel):
    """Legacy request model for backward compatibility."""
    
    include_extended: bool = Field(
        default=False,
        description="Include extended databases (DuckDuckGo, SERP, Scholar, OpenFDA)"
    )
    
    databases: Optional[List[str]] = Field(
        default=None,
        description="Specific databases to search (if None, searches all available)"
    )


class SearchResponse(BaseModel):
    """Legacy response model for search initiation."""
    
    job_id: str = Field(description="NCT number used as job ID")
    status: str = Field(description="Current status (queued, running, completed, failed)")
    message: str = Field(description="Human-readable status message")
    created_at: datetime = Field(description="Search creation timestamp")


class SearchStatus(BaseModel):
    """Legacy model for tracking search status."""
    
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
    """Legacy summary statistics for search results."""
    
    nct_id: str
    title: str
    status: str
    databases_searched: List[str]
    results_by_database: Dict[str, int]
    total_results: int
    search_timestamp: str


class SearchConfig(BaseModel):
    """Legacy search configuration."""
    
    use_extended_apis: bool = Field(default=False)
    enabled_databases: Optional[List[str]] = Field(default=None)
    max_results_per_api: int = Field(default=50)


# ============================================================================
# Helper Models
# ============================================================================

class FieldValue(BaseModel):
    """A field and its extracted values."""
    
    field_name: str = Field(description="Name of the field")
    values: List[str] = Field(description="Extracted values")
    source_api: str = Field(description="API that provided these values")


class SearchCombination(BaseModel):
    """A specific combination of field values for searching."""
    
    fields: Dict[str, str] = Field(description="Field name to value mapping")
    query: str = Field(description="Combined query string")
    description: str = Field(description="Human-readable description")


class SearchPlan(BaseModel):
    """Complete search plan for Step 2."""
    
    api_id: str = Field(description="API identifier")
    combinations: List[SearchCombination] = Field(description="All search combinations to execute")
    total_searches: int = Field(description="Total number of searches planned")


# Export all models
__all__ = [
    # Step 1
    'Step1Request',
    'Step1Response',
    'Step1Status',
    'SearchRecord',
    'CoreAPIResult',
    
    # Step 2
    'Step2Request',
    'Step2Response',
    'Step2Status',
    'ExtendedSearchRecord',
    'ExtendedAPIResult',
    
    # Combined
    'CombinedNCTResults',
    
    # Status
    'SearchStepStatus',
    
    # Backward compatibility
    'SearchRequest',
    'SearchResponse',
    'SearchStatus',
    'SearchSummary',
    'SearchConfig',
    
    # Helper models
    'FieldValue',
    'SearchCombination',
    'SearchPlan'
]
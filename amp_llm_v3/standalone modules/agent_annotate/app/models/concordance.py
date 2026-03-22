"""
Pydantic models for concordance analysis results.

Covers per-field concordance metrics, job-level summaries,
inter-version comparisons, and historical trend data.
"""

from typing import Optional
from pydantic import BaseModel, Field


class CategoryMetrics(BaseModel):
    """Per-category precision, recall, and F1 for a single value in a field."""
    value: str
    count_a: int = Field(description="How many times annotator A assigned this value")
    count_b: int = Field(description="How many times annotator B assigned this value")
    precision: Optional[float] = Field(
        default=None,
        description="TP / (TP + FP) — when A says this value, how often does B agree?",
    )
    recall: Optional[float] = Field(
        default=None,
        description="TP / (TP + FN) — when B says this value, how often does A agree?",
    )
    f1: Optional[float] = Field(
        default=None,
        description="2 * precision * recall / (precision + recall)",
    )


class Disagreement(BaseModel):
    """A single instance where two annotators disagree on a field."""
    nct_id: str
    field: str
    value_a: str
    value_b: str


class ConcordanceResult(BaseModel):
    """Per-field concordance metrics between two annotators."""
    field_name: str
    n: int = Field(description="Number of trials compared (after blank exclusions)")
    skipped: int = Field(description="Trials skipped due to blank values")
    agree_count: int
    agree_pct: float = Field(description="Raw agreement percentage (0-100)")
    kappa: Optional[float] = Field(
        default=None,
        description="Cohen's kappa (-1 to 1). None if no data.",
    )
    kappa_ci_lower: Optional[float] = Field(
        default=None,
        description="Lower bound of 95% CI for Cohen's kappa.",
    )
    kappa_ci_upper: Optional[float] = Field(
        default=None,
        description="Upper bound of 95% CI for Cohen's kappa.",
    )
    ac1: Optional[float] = Field(
        default=None,
        description="Gwet's AC1 — bias-corrected agreement coefficient.",
    )
    ac1_ci_lower: Optional[float] = Field(
        default=None,
        description="Lower bound of 95% CI for AC1.",
    )
    ac1_ci_upper: Optional[float] = Field(
        default=None,
        description="Upper bound of 95% CI for AC1.",
    )
    prevalence_idx: Optional[float] = Field(
        default=None,
        description="Prevalence index — high values suggest kappa may underestimate agreement.",
    )
    bias_idx: Optional[float] = Field(
        default=None,
        description="Bias index — measures systematic disagreement between raters.",
    )
    interpretation: str = Field(
        description="Landis & Koch interpretation based on AC1 (primary metric)",
    )
    category_metrics: list[CategoryMetrics] = Field(
        default_factory=list,
        description="Per-category precision, recall, and F1 scores",
    )
    confusion_matrix: dict[str, dict[str, int]] = Field(
        default_factory=dict,
        description="Confusion matrix: {value_a: {value_b: count}}",
    )
    value_distribution: dict[str, dict[str, int]] = Field(
        default_factory=dict,
        description="Value frequency counts per annotator: {'annotator_a': {val: count}, 'annotator_b': {val: count}}",
    )
    disagreements: list[Disagreement] = Field(default_factory=list)


class JobConcordance(BaseModel):
    """Full concordance results for a single comparison (e.g. agent vs R1)."""
    job_id: str = Field(
        description="Job ID for agent comparisons, or 'human' for R1 vs R2",
    )
    comparison_label: str = Field(
        description="Human-readable label, e.g. 'Agent vs R1'",
    )
    timestamp: Optional[str] = None
    n_overlapping: int = Field(
        default=0,
        description="Number of NCT IDs common to both annotators",
    )
    fields: list[ConcordanceResult] = Field(default_factory=list)
    overall_agree_pct: float = Field(
        default=0.0,
        description="Weighted average agreement across all fields",
    )


class ComparisonFieldDelta(BaseModel):
    """Per-field kappa comparison between two jobs."""
    field_name: str
    kappa_a: Optional[float] = None
    kappa_b: Optional[float] = None
    delta: Optional[float] = Field(
        default=None,
        description="kappa_b - kappa_a (positive = improvement)",
    )
    improved: bool = False


class ComparisonResult(BaseModel):
    """Inter-version comparison: how two agent jobs differ."""
    job_id_a: str
    job_id_b: str
    fields: list[ComparisonFieldDelta] = Field(default_factory=list)
    improved_count: int = 0
    regressed_count: int = 0
    unchanged_count: int = 0


class ConcordanceHistoryEntry(BaseModel):
    """Concordance snapshot for a single job."""
    job_id: str
    timestamp: Optional[str] = None
    field_kappas: dict[str, Optional[float]] = Field(
        default_factory=dict,
        description="Field name -> kappa value for agent vs R1",
    )
    n_trials: int = Field(default=0, description="Number of trials in this job")


class ConcordanceHistory(BaseModel):
    """Kappa trends across all completed jobs."""
    history: list[ConcordanceHistoryEntry] = Field(default_factory=list)


class FullJobConcordanceResponse(BaseModel):
    """Response for GET /api/concordance/job/{job_id} - all three comparisons."""
    agent_vs_r1: JobConcordance
    agent_vs_r2: JobConcordance
    r1_vs_r2: JobConcordance


class AnnotatorInfo(BaseModel):
    """Summary info about a single human annotator."""
    name: str
    replicate: str = Field(description="'r1' or 'r2'")
    nct_count: int = Field(description="Number of NCTs annotated by this person")


class AnnotatorListResponse(BaseModel):
    """Response for GET /api/concordance/annotators."""
    annotators: list[AnnotatorInfo] = Field(default_factory=list)

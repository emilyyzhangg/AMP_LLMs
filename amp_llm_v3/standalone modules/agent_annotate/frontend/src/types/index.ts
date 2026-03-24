/**
 * Shared TypeScript types for Agent Annotate UI.
 */

export interface JobSummary {
  job_id: string;
  status: string;
  created_at: string;
  total_trials: number;
  completed_trials: number;
}

export interface PipelineProgress {
  total_trials: number;
  completed_trials: number;
  current_nct_id: string | null;
  current_stage: string;
  errors: string[];
  // v11: Enhanced progress
  current_field: string | null;
  current_agent: string | null;
  current_model: string | null;
  field_timings: Record<string, number>;
  verification_progress: string | null;
}

export interface PipelineStatus {
  job_id: string;
  status: string;
  progress: PipelineProgress;
}

export interface ModelOpinion {
  model_name: string;
  agrees: boolean;
  suggested_value: string;
  reasoning: string;
  confidence: number;
}

export interface ReviewItem {
  job_id: string;
  nct_id: string;
  field_name: string;
  original_value: string;
  suggested_values: string[];
  opinions: ModelOpinion[];
  status: string;
  reviewer_value: string | null;
  reviewer_note: string | null;
  primary_reasoning?: string;
  primary_confidence?: number;
  primary_model?: string;
  created_at?: string;
  commit_hash?: string;
}

export interface ReviewStats {
  total: number;
  pending: number;
  decided: number;
  skipped: number;
}

export interface VersionInfo {
  semantic_version: string;
  git_commit_short: string;
  git_commit_full: string;
  config_hash: string;
}

export interface HealthStatus {
  status: string;
  version: VersionInfo;
  ollama: boolean;
}

export interface TimingInfo {
  started_at: string | null;
  finished_at: string | null;
  elapsed_seconds: number;
  avg_seconds_per_trial: number;
  commit_hash: string;
  timezone: string;
}

export interface ResultListItem {
  job_id: string;
  version: string;
  git_commit: string;
  timestamp: string;
  total_trials: number;
  successful: number;
  failed: number;
  manual_review: number;
  timing?: TimingInfo;
}

export interface ResultSummary {
  job_id: string;
  total_trials: number;
  successful: number;
  failed: number;
  manual_review: number;
  version?: Record<string, string>;
  status?: string;
  completed_trials?: number;
  timing?: TimingInfo;
}

// Concordance types

export interface CategoryMetrics {
  value: string;
  count_a: number;
  count_b: number;
  precision: number | null;
  recall: number | null;
  f1: number | null;
}

export interface ConcordanceField {
  field_name: string;
  n: number;
  skipped: number;
  agree_count: number;
  agree_pct: number;
  kappa: number | null;
  ac1: number | null;
  interpretation: string;
  category_metrics: CategoryMetrics[];
  confusion_matrix: Record<string, Record<string, number>>;
  value_distribution: Record<string, Record<string, number>>;
  disagreements: Array<{ nct_id: string; field: string; value_a: string; value_b: string }>;
}

export interface JobConcordance {
  job_id: string;
  timestamp: string;
  comparison_label: string;
  n_overlapping: number;
  fields: ConcordanceField[];
  overall_agree_pct: number;
}

export interface ComparisonField {
  field_name: string;
  kappa_a: number | null;
  kappa_b: number | null;
  delta: number | null;
  improved: boolean;
}

export interface ComparisonResult {
  job_id_a: string;
  job_id_b: string;
  fields: ComparisonField[];
}

export interface ConcordanceHistoryEntry {
  job_id: string;
  timestamp: string;
  field_kappas: Record<string, number>;
  field_ac1s: Record<string, number>;
  field_agreements: Record<string, number>;
  n_trials: number;
}

// Partial results for pipeline view
export interface PartialTrial {
  nct_id: string;
  status: string;
}

export interface PartialResults {
  job_id: string;
  trials: PartialTrial[];
  count: { completed: number; total: number };
  status: string;
}

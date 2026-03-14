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

export interface ResultListItem {
  job_id: string;
  version: string;
  git_commit: string;
  timestamp: string;
  total_trials: number;
  successful: number;
  failed: number;
  manual_review: number;
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
}

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

export interface ReviewItem {
  job_id: string;
  nct_id: string;
  field_name: string;
  original_value: string;
  suggested_values: string[];
  opinions: object[];
  status: string;
  reviewer_value: string | null;
  reviewer_note: string | null;
}

export interface VersionInfo {
  semantic_version: string;
  git_commit_short: string;
  git_commit_full: string;
  config_hash: string;
}

export interface HealthStatus {
  status: string;
  ollama: string;
  version: VersionInfo;
}

/**
 * API client for Agent Annotate backend.
 */

import type {
  JobSummary,
  PipelineStatus,
  ReviewItem,
  ReviewStats,
  ResultListItem,
  ResultSummary,
} from "../types";

const BASE = "/api";

async function request<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(opts?.headers as Record<string, string> || {}) },
    ...opts,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  return res.json();
}

// Health
export const getHealth = () =>
  request<{ status: string; version: string }>("/health");

export const getReadiness = () =>
  request<{ status: string; ollama: string; version: { semantic_version: string; git_commit_short: string; git_commit_full: string; config_hash: string } }>("/health/ready");

// Jobs
export const createJob = (nctIds: string[]) =>
  request<{ job_id: string; status: string; total_trials: number }>("/jobs", {
    method: "POST",
    body: JSON.stringify({ nct_ids: nctIds }),
  });

export const listJobs = () =>
  request<JobSummary[]>("/jobs");

export const getJob = (id: string) =>
  request<Record<string, unknown>>(`/jobs/${id}`);

export const cancelJob = (id: string) =>
  request<{ success: boolean }>(`/jobs/${id}/cancel`, { method: "POST" });

// Status
export const getPipelineStatus = (id: string) =>
  request<PipelineStatus>(`/status/pipeline/${id}`);

export const getAvailableModels = () =>
  request<{ models: string[] }>("/status/models");

// Results
export const listResults = () =>
  request<{ results: ResultListItem[]; total: number }>("/results");

export const getResults = (id: string) =>
  request<Record<string, unknown>>(`/results/${id}`);

export const getResultsSummary = (id: string) =>
  request<ResultSummary>(`/results/${id}/summary`);

export const getResultsCsvUrl = (jobId: string, format: "standard" | "full" = "standard") =>
  `${BASE}/results/${jobId}/csv?format=${format}`;

// Review
export const getReviewItems = (jobId?: string, status?: string) => {
  const params = new URLSearchParams();
  if (jobId) params.set("job_id", jobId);
  if (status) params.set("status", status);
  const qs = params.toString();
  return request<{ items: ReviewItem[]; total: number }>(`/review${qs ? `?${qs}` : ""}`);
};

export const getReviewStats = () =>
  request<ReviewStats>("/review/stats");

export const submitReview = (
  jobId: string,
  nctId: string,
  field: string,
  decision: { action: string; value?: string; note?: string },
) =>
  request<Record<string, unknown>>(`/review/${jobId}/${nctId}/${field}`, {
    method: "POST",
    body: JSON.stringify(decision),
  });

// Settings
export const getSettings = () =>
  request<Record<string, unknown>>("/settings");

export const updateSettings = (overrides: Record<string, unknown>) =>
  request<Record<string, unknown>>("/settings", { method: "PUT", body: JSON.stringify(overrides) });

export const reloadSettings = () =>
  request<Record<string, unknown>>("/settings/reload", { method: "POST" });

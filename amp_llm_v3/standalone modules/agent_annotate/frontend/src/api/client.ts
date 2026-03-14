/**
 * API client for Agent Annotate backend.
 */

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
export const getHealth = () => request<{ status: string; version: string }>("/health");
export const getReadiness = () => request<{ status: string; ollama: string; version: object }>("/health/ready");

// Jobs
export const createJob = (nctIds: string[]) =>
  request<{ job_id: string; status: string; total_trials: number }>("/jobs", {
    method: "POST",
    body: JSON.stringify({ nct_ids: nctIds }),
  });

export const listJobs = () => request<Array<{ job_id: string; status: string; created_at: string; total_trials: number; completed_trials: number }>>("/jobs");
export const getJob = (id: string) => request<any>(`/jobs/${id}`);
export const cancelJob = (id: string) => request<any>(`/jobs/${id}/cancel`, { method: "POST" });

// Status
export const getPipelineStatus = (id: string) => request<any>(`/status/pipeline/${id}`);
export const getAvailableModels = () => request<{ models: string[] }>("/status/models");

// Results
export const getResults = (id: string) => request<any>(`/results/${id}`);
export const getResultsSummary = (id: string) => request<any>(`/results/${id}/summary`);
export const exportCSV = (jobId: string, format: string = "standard") =>
  request<any>("/results/export/csv", {
    method: "POST",
    body: JSON.stringify({ job_id: jobId, format }),
  });

// Review
export const getReviewItems = (jobId?: string) =>
  request<{ items: any[]; total: number }>(`/review${jobId ? `?job_id=${jobId}` : ""}`);
export const submitReview = (jobId: string, nctId: string, field: string, decision: { action: string; value?: string; note?: string }) =>
  request<any>(`/review/${jobId}/${nctId}/${field}`, {
    method: "POST",
    body: JSON.stringify(decision),
  });

// Settings
export const getSettings = () => request<any>("/settings");
export const updateSettings = (overrides: object) =>
  request<any>("/settings", { method: "PUT", body: JSON.stringify(overrides) });
export const reloadSettings = () => request<any>("/settings/reload", { method: "POST" });

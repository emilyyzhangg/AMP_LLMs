import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getPipelineStatus, cancelJob, getPartialResults } from "../api/client";
import type { PipelineStatus, PartialResults } from "../types";

const BATCH_PHASES = ["researching", "annotating", "verifying", "saving"] as const;

function batchPhaseIndex(stage: string): number {
  const s = stage.toLowerCase();
  if (s.includes("research")) return 0;
  if (s.includes("annot")) return 1;
  if (s.includes("verif")) return 2;
  if (s.includes("sav") || s.includes("done")) return 3;
  return -1;
}

function formatAgent(agent: string): string {
  if (!agent) return "--";
  return agent
    .replace(/_/g, " ")
    .replace(/\b\w/g, c => c.toUpperCase());
}

function formatDuration(secs: number): string {
  if (secs < 60) return `${Math.round(secs)}s`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ${Math.round(secs % 60)}s`;
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  return `${h}h ${m}m`;
}

export default function PipelinePage() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const [status, setStatus] = useState<PipelineStatus | null>(null);
  const [error, setError] = useState("");
  const [cancelling, setCancelling] = useState(false);
  const [partialResults, setPartialResults] = useState<PartialResults | null>(null);
  const [partialError, setPartialError] = useState(false);

  useEffect(() => {
    if (!jobId) return;

    let active = true;

    const poll = async () => {
      try {
        const data = await getPipelineStatus(jobId);
        if (!active) return;
        setStatus(data);
        if (data.status === "completed") {
          navigate(`/results/${data.job_id}`);
        } else if (data.status === "failed" || data.status === "cancelled") {
          setError(`Job ${data.status}`);
        }
      } catch (e: unknown) {
        if (!active) return;
        const msg = e instanceof Error ? e.message : "Unknown error";
        setError(msg);
      }
    };

    const pollPartial = async () => {
      if (partialError) return;
      try {
        const data = await getPartialResults(jobId);
        if (!active) return;
        if (data) {
          setPartialResults(data);
        } else {
          setPartialError(true);
        }
      } catch {
        if (!active) return;
        setPartialError(true);
      }
    };

    poll();
    pollPartial();
    const interval = setInterval(poll, 2000);
    const partialInterval = setInterval(pollPartial, 3000);
    return () => {
      active = false;
      clearInterval(interval);
      clearInterval(partialInterval);
    };
  }, [jobId, navigate, partialError]);

  const handleCancel = async () => {
    if (!jobId || cancelling) return;
    setCancelling(true);
    try {
      await cancelJob(jobId);
    } catch {
      // poll will pick up the status change
    }
  };

  if (error) {
    return (
      <div className="card">
        <div style={{ color: "var(--error)" }}>{error}</div>
        <button className="btn btn-secondary mt-2" onClick={() => navigate("/jobs")}>
          Back to Jobs
        </button>
      </div>
    );
  }

  if (!status) {
    return <div className="card text-muted">Loading pipeline status...</div>;
  }

  const progress = status.progress as Record<string, unknown>;
  const completed = (progress.completed_trials as number) || 0;
  const total = (progress.total_trials as number) || 0;
  const pct = (progress.percent as number) || 0;
  const stage = (progress.current_stage as string) || "";
  const currentPhase = batchPhaseIndex(stage);
  const elapsed = (progress.elapsed_display as string) || "";
  const remaining = (progress.estimated_remaining_display as string) || "";
  const avgPerTrial = (progress.avg_per_trial_display as string) || "";

  const currentField = (progress.current_field as string) || "";
  const currentAgent = (progress.current_agent as string) || "";
  const currentModel = (progress.current_model as string) || "";
  const verificationProgress = (progress.verification_progress as string) || "";
  const fieldTimings = (progress.field_timings as Record<string, number>) || {};
  const nctId = (progress.current_nct_id as string) || "";

  // Compute effective throughput from raw seconds
  const elapsedSecs = (progress.elapsed_seconds as number) || 0;
  const effectiveAvg = completed > 0 ? elapsedSecs / completed : 0;

  return (
    <div>
      <h2 style={{ marginBottom: "1rem" }}>Pipeline Progress</h2>
      <div className="card">
        {/* Header */}
        <div className="flex-between mb-2">
          <span>Job: <strong>{jobId}</strong></span>
          <div className="flex gap-1">
            <span className={`badge badge-${status.status}`}>{status.status}</span>
            {status.status === "running" && (
              <button className="btn btn-danger" onClick={handleCancel} disabled={cancelling}>
                {cancelling ? "Cancelling..." : "Cancel"}
              </button>
            )}
          </div>
        </div>

        {/* Mini-batch phase indicators */}
        <div className="flex gap-2 mb-2">
          {BATCH_PHASES.map((phase, i) => {
            let style: React.CSSProperties = {
              padding: "0.3rem 0.8rem",
              borderRadius: "var(--radius)",
              fontSize: "0.75rem",
              fontWeight: 600,
              textTransform: "uppercase",
              letterSpacing: "0.5px",
            };
            if (i < currentPhase) {
              style = { ...style, background: "#064e3b", color: "var(--success)" };
            } else if (i === currentPhase) {
              style = { ...style, background: "#1e3a5f", color: "#60a5fa" };
            } else {
              style = { ...style, background: "var(--bg-secondary)", color: "var(--text-secondary)" };
            }
            return (
              <span key={phase} style={style}>
                {i < currentPhase ? "\u2713 " : ""}{phase}
              </span>
            );
          })}
        </div>

        {/* Trial progress bar */}
        <div className="mb-1">
          <span className="text-sm text-muted">
            {completed} / {total} trials completed
            {nctId && ` \u2014 ${nctId}`}
          </span>
        </div>
        <div className="progress-bar">
          <div className="progress-fill" style={{ width: `${pct}%` }} />
        </div>

        {/* Active work panel */}
        {(currentField || currentAgent || currentModel || verificationProgress) && (
          <div style={{
            marginTop: "0.75rem",
            padding: "0.6rem 0.75rem",
            background: "var(--bg-secondary)",
            borderRadius: "var(--radius)",
            fontSize: "0.8rem",
          }}>
            {/* Current activity line */}
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
              {currentAgent && (
                <span style={{
                  background: stage.includes("verif") ? "#1e3a5f" : "#064e3b",
                  color: stage.includes("verif") ? "#60a5fa" : "var(--success)",
                  padding: "0.15rem 0.5rem",
                  borderRadius: "var(--radius)",
                  fontSize: "0.7rem",
                  fontWeight: 600,
                  textTransform: "uppercase",
                }}>
                  {formatAgent(currentAgent)}
                </span>
              )}
              {currentField && (
                <span style={{ color: "var(--text-primary)" }}>{currentField}</span>
              )}
              {currentModel && (
                <span style={{ color: "var(--text-secondary)", fontSize: "0.75rem" }}>
                  via {currentModel}
                </span>
              )}
            </div>
            {/* Verification progress */}
            {verificationProgress && (
              <div style={{ marginTop: "0.3rem", color: "var(--text-secondary)", fontSize: "0.75rem" }}>
                {verificationProgress}
              </div>
            )}
          </div>
        )}

        {/* Timing grid */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr 1fr",
          gap: "1rem",
          marginTop: "0.75rem",
          padding: "0.75rem",
          background: "var(--bg-secondary)",
          borderRadius: "var(--radius)",
          fontSize: "0.85rem",
        }}>
          <div>
            <div className="text-muted" style={{ fontSize: "0.7rem", marginBottom: "0.2rem" }}>Elapsed</div>
            <div style={{ fontWeight: 600 }}>{elapsed || "0s"}</div>
          </div>
          <div>
            <div className="text-muted" style={{ fontSize: "0.7rem", marginBottom: "0.2rem" }}>Est. Remaining</div>
            <div style={{ fontWeight: 600 }}>{remaining || (completed === 0 ? "Calculating..." : "0s")}</div>
          </div>
          <div>
            <div className="text-muted" style={{ fontSize: "0.7rem", marginBottom: "0.2rem" }}>Throughput</div>
            <div style={{ fontWeight: 600 }}>
              {completed > 0 ? formatDuration(effectiveAvg) + "/trial" : "\u2014"}
            </div>
          </div>
        </div>

        {/* Field timings for current trial */}
        {Object.keys(fieldTimings).length > 0 && (
          <div style={{
            display: "flex",
            gap: "0.5rem",
            flexWrap: "wrap",
            marginTop: "0.5rem",
            fontSize: "0.75rem",
          }}>
            {Object.entries(fieldTimings).map(([field, secs]) => (
              <span key={field} style={{
                padding: "0.15rem 0.4rem",
                background: "var(--bg-secondary)",
                borderRadius: "var(--radius)",
                color: secs === 0 ? "var(--success)" : "var(--text-secondary)",
              }}>
                {field}: {secs === 0 ? "det." : `${Math.round(secs)}s`}
              </span>
            ))}
          </div>
        )}

        {/* Errors */}
        {((progress.errors as string[]) || []).length > 0 && (
          <div className="mt-2">
            <div className="text-sm" style={{ color: "var(--error)" }}>
              Errors ({(progress.errors as string[]).length}):
            </div>
            {(progress.errors as string[]).map((err: string, i: number) => (
              <div key={i} className="text-sm text-muted">{err}</div>
            ))}
          </div>
        )}
      </div>

      {/* Partial Results */}
      {completed > 0 && !partialError && (
        <div className="card">
          <div className="card-title flex-between">
            <span>
              Partial Results
              {partialResults && (
                <span className="text-sm text-muted" style={{ fontWeight: 400, marginLeft: "0.75rem" }}>
                  {partialResults.count?.completed ?? partialResults.trials.length} / {partialResults.count?.total ?? "?"} persisted
                </span>
              )}
            </span>
            {partialResults && partialResults.trials.some(t => t.status === "review") && (
              <button className="btn btn-secondary" style={{ fontSize: "0.8rem", padding: "0.3rem 0.8rem" }}
                onClick={() => navigate(`/review?job_id=${jobId}`)}>
                Review Flagged
              </button>
            )}
          </div>

          {partialResults && partialResults.trials.length > 0 ? (
            <div className="partial-results-table">
              <table>
                <thead>
                  <tr>
                    <th>NCT ID</th>
                    <th>Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {partialResults.trials.map((trial, i) => (
                    <tr key={i}>
                      <td>{trial.nct_id}</td>
                      <td>
                        {trial.status === "ok" || trial.status === "completed" ? (
                          <span className="badge badge-completed">OK</span>
                        ) : trial.status === "failed" ? (
                          <span className="badge badge-failed">Failed</span>
                        ) : trial.status === "review" ? (
                          <span className="badge badge-cancelled">Review</span>
                        ) : (
                          <span className="badge badge-running">{trial.status || "-"}</span>
                        )}
                      </td>
                      <td>
                        {trial.status === "review" && (
                          <button className="btn btn-secondary" style={{ fontSize: "0.75rem", padding: "0.2rem 0.5rem" }}
                            onClick={() => navigate(`/review?job_id=${jobId}`)}>
                            Review
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-sm text-muted">Waiting for first batch to complete...</div>
          )}
        </div>
      )}
    </div>
  );
}

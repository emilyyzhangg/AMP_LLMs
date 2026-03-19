import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getPipelineStatus, cancelJob, getPartialResults } from "../api/client";
import type { PipelineStatus, PartialResults } from "../types";

const PHASES = ["researching", "annotating", "verifying"] as const;

function phaseIndex(stage: string): number {
  const s = stage.toLowerCase();
  if (s.includes("research")) return 0;
  if (s.includes("annot")) return 1;
  if (s.includes("verif") || s.includes("review")) return 2;
  return -1;
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
      if (partialError) return; // Stop trying if endpoint doesn't exist
      try {
        const data = await getPartialResults(jobId);
        if (!active) return;
        if (data) {
          setPartialResults(data);
        } else {
          // null means endpoint not available
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
        <button className="btn btn-secondary mt-2" onClick={() => navigate("/history")}>
          Back to History
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
  const currentPhase = phaseIndex((progress.current_stage as string) || "");
  const elapsed = (progress.elapsed_display as string) || "";
  const remaining = (progress.estimated_remaining_display as string) || "";
  const avgPerTrial = (progress.avg_per_trial_display as string) || "";

  return (
    <div>
      <h2 style={{ marginBottom: "1rem" }}>Pipeline Progress</h2>
      <div className="card">
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

        {/* Phase indicators */}
        <div className="flex gap-2 mb-2">
          {PHASES.map((phase, i) => {
            let style: React.CSSProperties = {
              padding: "0.3rem 0.8rem",
              borderRadius: "var(--radius)",
              fontSize: "0.8rem",
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

        {/* Trial progress */}
        <div className="mb-1">
          <span className="text-sm text-muted">
            {completed} / {total} trials
            {progress.current_nct_id && ` \u2014 Processing ${progress.current_nct_id}`}
          </span>
        </div>
        <div className="progress-bar">
          <div className="progress-fill" style={{ width: `${pct}%` }} />
        </div>

        {/* Timing info */}
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
            <div className="text-muted" style={{ fontSize: "0.75rem", marginBottom: "0.2rem" }}>Elapsed</div>
            <div style={{ fontWeight: 600 }}>{elapsed || "0s"}</div>
          </div>
          <div>
            <div className="text-muted" style={{ fontSize: "0.75rem", marginBottom: "0.2rem" }}>Est. Remaining</div>
            <div style={{ fontWeight: 600 }}>{remaining || (completed === 0 ? "Calculating..." : "0s")}</div>
          </div>
          <div>
            <div className="text-muted" style={{ fontSize: "0.75rem", marginBottom: "0.2rem" }}>Avg / Trial</div>
            <div style={{ fontWeight: 600 }}>{avgPerTrial || (completed === 0 ? "\u2014" : "0s")}</div>
          </div>
        </div>

        <div className="text-sm text-muted mt-1">
          Stage: {(progress.current_stage as string) || "initializing"}
        </div>

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

      {/* Partial Results Section */}
      {completed > 0 && !partialError && (
        <div className="card">
          <div className="card-title flex-between">
            <span>
              Partial Results
              {partialResults && (
                <span className="text-sm text-muted" style={{ fontWeight: 400, marginLeft: "0.75rem" }}>
                  {partialResults.count?.completed ?? partialResults.trials.length} / {partialResults.count?.total ?? "?"} trials
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
            <div className="text-sm text-muted">Waiting for partial results data...</div>
          )}
        </div>
      )}
    </div>
  );
}

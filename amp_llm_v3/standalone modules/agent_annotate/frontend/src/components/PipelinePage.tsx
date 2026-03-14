import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getPipelineStatus, cancelJob } from "../api/client";
import type { PipelineStatus } from "../types";

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

    poll();
    const interval = setInterval(poll, 2000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [jobId, navigate]);

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

  const progress = status.progress;
  const pct = progress.total_trials > 0
    ? Math.round((progress.completed_trials / progress.total_trials) * 100)
    : 0;
  const currentPhase = phaseIndex(progress.current_stage || "");

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

        <div className="mb-1">
          <span className="text-sm text-muted">
            {progress.completed_trials} / {progress.total_trials} trials
            {progress.current_nct_id && ` \u2014 Processing ${progress.current_nct_id}`}
          </span>
        </div>
        <div className="progress-bar">
          <div className="progress-fill" style={{ width: `${pct}%` }} />
        </div>
        <div className="text-sm text-muted mt-1">
          Stage: {progress.current_stage || "initializing"}
        </div>

        {progress.errors.length > 0 && (
          <div className="mt-2">
            <div className="text-sm" style={{ color: "var(--error)" }}>
              Errors ({progress.errors.length}):
            </div>
            {progress.errors.map((err, i) => (
              <div key={i} className="text-sm text-muted">{err}</div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

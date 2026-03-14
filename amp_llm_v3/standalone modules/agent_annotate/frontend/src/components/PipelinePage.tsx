import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getPipelineStatus } from "../api/client";

export default function PipelinePage() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const [status, setStatus] = useState<any>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!jobId) return;

    const poll = async () => {
      try {
        const data = await getPipelineStatus(jobId);
        setStatus(data);
        if (data.status === "completed") {
          navigate(`/results/${jobId}`);
        } else if (data.status === "failed" || data.status === "cancelled") {
          setError(`Job ${data.status}`);
        }
      } catch (e: any) {
        setError(e.message);
      }
    };

    poll();
    const interval = setInterval(poll, 2000);
    return () => clearInterval(interval);
  }, [jobId, navigate]);

  if (error) {
    return (
      <div className="card">
        <div style={{ color: "var(--error)" }}>{error}</div>
      </div>
    );
  }

  if (!status) {
    return <div className="card text-muted">Loading pipeline status...</div>;
  }

  const progress = status.progress || {};
  const pct = progress.total_trials > 0
    ? Math.round((progress.completed_trials / progress.total_trials) * 100)
    : 0;

  return (
    <div>
      <h2 style={{ marginBottom: "1rem" }}>Pipeline Progress</h2>
      <div className="card">
        <div className="flex-between mb-2">
          <span>Job: <strong>{jobId}</strong></span>
          <span className={`badge badge-${status.status}`}>{status.status}</span>
        </div>
        <div className="mb-1">
          <span className="text-sm text-muted">
            {progress.completed_trials} / {progress.total_trials} trials
            {progress.current_nct_id && ` - Processing ${progress.current_nct_id}`}
          </span>
        </div>
        <div className="progress-bar">
          <div className="progress-fill" style={{ width: `${pct}%` }} />
        </div>
        <div className="text-sm text-muted mt-1">
          Stage: {progress.current_stage || "unknown"}
        </div>
      </div>
    </div>
  );
}

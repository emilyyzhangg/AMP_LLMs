import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { listJobs } from "../api/client";
import type { JobSummary } from "../types";

export default function JobsPage() {
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    (async () => {
      try {
        const data = await listJobs();
        setJobs(data);
      } catch (e) {
        console.error("Failed to load jobs", e);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) return <div className="card text-muted">Loading jobs...</div>;

  return (
    <div>
      <h2 style={{ marginBottom: "1rem" }}>Jobs</h2>
      {jobs.length === 0 ? (
        <div className="card text-muted">No jobs yet. Submit NCT IDs to start annotating.</div>
      ) : (
        <div className="card">
          <table>
            <thead>
              <tr>
                <th>Job ID</th>
                <th>Status</th>
                <th>Trials</th>
                <th>Progress</th>
                <th>Issues</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => {
                const issueCount = (job.warnings_count ?? 0)
                  + (job.timeouts_count ?? 0)
                  + (job.retries_count ?? 0);
                return (
                  <tr
                    key={job.job_id}
                    style={{ cursor: "pointer" }}
                    onClick={() => {
                      if (job.status === "completed") navigate(`/results/${job.job_id}`);
                      else if (job.status === "running") navigate(`/pipeline/${job.job_id}`);
                    }}
                  >
                    <td style={{ fontFamily: "monospace", fontSize: "0.85rem" }}>{job.job_id.slice(0, 8)}</td>
                    <td><span className={`badge badge-${job.status}`}>{job.status}</span></td>
                    <td>{job.total_trials}</td>
                    <td>{job.completed_trials} / {job.total_trials}</td>
                    <td>
                      {issueCount > 0 ? (
                        <span className="badge" style={{
                          background: "var(--warning)",
                          color: "#000",
                          fontSize: "0.75rem",
                        }}>
                          {issueCount}
                          {(job.timeouts_count ?? 0) > 0 && ` (${job.timeouts_count} timeout${(job.timeouts_count ?? 0) > 1 ? "s" : ""})`}
                        </span>
                      ) : (
                        <span className="text-sm text-muted">--</span>
                      )}
                    </td>
                    <td className="text-sm text-muted">
                      {new Date(job.created_at).toLocaleString()}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

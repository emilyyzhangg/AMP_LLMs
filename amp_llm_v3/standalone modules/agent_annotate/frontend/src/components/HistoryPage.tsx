import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { listJobs } from "../api/client";
import type { JobSummary } from "../types";

export default function HistoryPage() {
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

  if (loading) return <div className="card text-muted">Loading job history...</div>;

  return (
    <div>
      <h2 style={{ marginBottom: "1rem" }}>Job History</h2>
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
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr
                  key={job.job_id}
                  style={{ cursor: "pointer" }}
                  onClick={() => {
                    if (job.status === "completed") navigate(`/results/${job.job_id}`);
                    else if (job.status === "running") navigate(`/pipeline/${job.job_id}`);
                  }}
                >
                  <td>{job.job_id}</td>
                  <td><span className={`badge badge-${job.status}`}>{job.status}</span></td>
                  <td>{job.total_trials}</td>
                  <td>{job.completed_trials} / {job.total_trials}</td>
                  <td className="text-sm text-muted">
                    {new Date(job.created_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

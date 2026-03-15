import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { listResults, getResults, getResultsSummary, getResultsCsvUrl } from "../api/client";
import type { ResultListItem, ResultSummary } from "../types";

function ResultsList() {
  const navigate = useNavigate();
  const [results, setResults] = useState<ResultListItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const data = await listResults();
        setResults(data.results || []);
      } catch (e) {
        console.error("Failed to load results", e);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) return <div className="card text-muted">Loading results...</div>;

  return (
    <div>
      <h2 style={{ marginBottom: "1rem" }}>Results</h2>
      {results.length === 0 ? (
        <div className="card text-muted">No completed results yet.</div>
      ) : (
        <div className="card">
          <table>
            <thead>
              <tr>
                <th>Job ID</th>
                <th>Trials</th>
                <th>Successful</th>
                <th>Failed</th>
                <th>Review</th>
                <th>Version</th>
                <th>Date</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r) => (
                <tr
                  key={r.job_id}
                  style={{ cursor: "pointer" }}
                  onClick={() => navigate(`/results/${r.job_id}`)}
                >
                  <td>{r.job_id}</td>
                  <td>{r.total_trials}</td>
                  <td>{r.successful}</td>
                  <td>{r.failed}</td>
                  <td>{r.manual_review}</td>
                  <td className="text-sm text-muted">{r.version || "\u2014"}</td>
                  <td className="text-sm text-muted">
                    {r.timestamp ? new Date(r.timestamp).toLocaleString() : "\u2014"}
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

function ResultDetail({ jobId }: { jobId: string }) {
  const navigate = useNavigate();
  const [results, setResults] = useState<Record<string, unknown> | null>(null);
  const [summary, setSummary] = useState<ResultSummary | null>(null);
  const [error, setError] = useState("");
  const [showJson, setShowJson] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [res, sum] = await Promise.all([getResults(jobId), getResultsSummary(jobId)]);
        setResults(res);
        setSummary(sum);
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : "Unknown error";
        setError(msg);
      }
    })();
  }, [jobId]);

  if (error) return <div className="card" style={{ color: "var(--error)" }}>{error}</div>;
  if (!results) return <div className="card text-muted">Loading results...</div>;

  const trials = (results.trials as Record<string, unknown>[]) || [];

  return (
    <div>
      <div className="flex-between mb-2">
        <div>
          <button className="btn btn-secondary" onClick={() => navigate("/results")} style={{ marginRight: "1rem" }}>
            &larr; All Results
          </button>
          <strong style={{ fontSize: "1.1rem" }}>Results: {jobId}</strong>
        </div>
        {summary && (
          <div className="text-sm text-muted">
            {summary.total_trials} trials | {summary.successful} OK | {summary.failed} failed | {summary.manual_review} review
          </div>
        )}
      </div>

      {results.version && (
        <div className="text-sm text-muted mb-2">
          v{(results.version as Record<string, string>).version || (results.version as Record<string, string>).semantic_version || ""}{" "}
          ({(results.version as Record<string, string>).git_commit_short || (results.version as Record<string, string>).git_commit || ""}){" "}
          | config: {(results.version as Record<string, string>).config_hash || "\u2014"}
        </div>
      )}

      {/* CSV download links */}
      <div className="flex gap-1 mb-2">
        <a
          className="btn btn-secondary"
          href={getResultsCsvUrl(jobId, "standard")}
          download
        >
          Download CSV (Standard)
        </a>
        <a
          className="btn btn-secondary"
          href={getResultsCsvUrl(jobId, "full")}
          download
        >
          Download CSV (Full)
        </a>
        <button className="btn btn-secondary" onClick={() => setShowJson(!showJson)}>
          {showJson ? "Hide JSON" : "Show JSON"}
        </button>
      </div>

      {/* JSON viewer */}
      {showJson && (
        <div className="card mb-2">
          <pre style={{
            background: "var(--bg-primary)",
            padding: "1rem",
            borderRadius: "var(--radius)",
            overflow: "auto",
            maxHeight: "500px",
            fontSize: "0.8rem",
            color: "var(--text-secondary)",
          }}>
            {JSON.stringify(results, null, 2)}
          </pre>
        </div>
      )}

      {/* Trials table */}
      <div className="card">
        {trials.length > 0 ? (
          <table>
            <thead>
              <tr>
                <th>NCT ID</th>
                <th>Classification</th>
                <th>Delivery Mode</th>
                <th>Outcome</th>
                <th>Peptide</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {trials.map((trial: Record<string, unknown>, i: number) => {
                const fields: Record<string, string> = {};
                ((trial.fields as Record<string, unknown>[]) || []).forEach((f: Record<string, unknown>) => {
                  fields[f.field_name as string] = f.final_value as string;
                });
                const flagged = (trial.verification as Record<string, unknown>)?.flagged_for_review;
                return (
                  <tr key={i}>
                    <td>{trial.nct_id as string}</td>
                    <td>{fields.classification || "\u2014"}</td>
                    <td>{fields.delivery_mode || "\u2014"}</td>
                    <td>{fields.outcome || "\u2014"}</td>
                    <td>{fields.peptide || "\u2014"}</td>
                    <td>
                      {flagged ? (
                        <span className="badge badge-cancelled">Review</span>
                      ) : (
                        <span className="badge badge-completed">OK</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <div className="text-muted">No trial results available.</div>
        )}
      </div>
    </div>
  );
}

export default function ResultsPage() {
  const { jobId } = useParams<{ jobId: string }>();

  if (!jobId) {
    return <ResultsList />;
  }

  return <ResultDetail jobId={jobId} />;
}

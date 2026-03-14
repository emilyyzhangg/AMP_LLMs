import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import { getResults, getResultsSummary } from "../api/client";

export default function ResultsPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const [results, setResults] = useState<any>(null);
  const [summary, setSummary] = useState<any>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!jobId) return;
    (async () => {
      try {
        const [res, sum] = await Promise.all([getResults(jobId), getResultsSummary(jobId)]);
        setResults(res);
        setSummary(sum);
      } catch (e: any) {
        setError(e.message);
      }
    })();
  }, [jobId]);

  if (error) return <div className="card" style={{ color: "var(--error)" }}>{error}</div>;
  if (!results) return <div className="card text-muted">Loading results...</div>;

  return (
    <div>
      <div className="flex-between mb-2">
        <h2>Results: {jobId}</h2>
        {summary && (
          <div className="text-sm text-muted">
            {summary.completed_trials} trials | {summary.flagged_for_review} flagged
          </div>
        )}
      </div>

      {results.version && (
        <div className="text-sm text-muted mb-2">
          v{results.version.semantic_version} ({results.version.git_commit_short}) | config: {results.version.config_hash}
        </div>
      )}

      <div className="card">
        {results.trials?.length > 0 ? (
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
              {results.trials.map((trial: any, i: number) => {
                const fields: Record<string, string> = {};
                (trial.fields || []).forEach((f: any) => {
                  fields[f.field_name] = f.final_value;
                });
                return (
                  <tr key={i}>
                    <td>{trial.nct_id}</td>
                    <td>{fields.classification || "-"}</td>
                    <td>{fields.delivery_mode || "-"}</td>
                    <td>{fields.outcome || "-"}</td>
                    <td>{fields.peptide || "-"}</td>
                    <td>
                      {trial.flagged_for_review ? (
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

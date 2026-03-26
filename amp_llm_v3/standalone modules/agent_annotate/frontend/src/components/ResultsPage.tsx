import { useState, useEffect, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { listResults, getResults, getResultsSummary, getResultsCsvUrl, resumeJob, listJobs } from "../api/client";
import type { ResultListItem, ResultSummary, TimingInfo, JobSummary } from "../types";

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  if (mins < 60) return `${mins}m ${secs.toFixed(0)}s`;
  const hrs = Math.floor(mins / 60);
  const remainMins = mins % 60;
  return `${hrs}h ${remainMins}m`;
}

function TimingBadge({ timing }: { timing?: TimingInfo }) {
  if (!timing || !timing.elapsed_seconds) return null;
  return (
    <span className="text-sm text-muted" title={`${timing.avg_seconds_per_trial.toFixed(1)}s/trial | ${timing.timezone}`}>
      {formatElapsed(timing.elapsed_seconds)}
    </span>
  );
}

// --- Confidence dot component ---
function ConfidenceDot({ confidence }: { confidence?: number }) {
  if (confidence === undefined || confidence === null) return null;
  let cls = "low";
  if (confidence >= 0.8) cls = "high";
  else if (confidence >= 0.4) cls = "medium";
  return <span className={`confidence-dot ${cls}`} title={`Confidence: ${(confidence * 100).toFixed(0)}%`} />;
}

// --- Helper to extract field data from a trial ---
interface FieldData {
  final_value: string;
  confidence?: number;
  reasoning?: string;
  model_name?: string;
  evidence?: Array<{ source: string; snippet: string; url?: string }>;
  verification_summary?: string;
  verifier_agree_count?: number;
  verifier_total?: number;
  research_agents?: Array<{ agent_name: string; citations: number }>;
}

function extractFieldData(trial: Record<string, unknown>): Record<string, FieldData> {
  const fields: Record<string, FieldData> = {};
  const fieldList = (trial.fields as Record<string, unknown>[]) || [];
  for (const f of fieldList) {
    const name = f.field_name as string;
    const evidence: Array<{ source: string; snippet: string; url?: string }> = [];
    const evidenceRaw = (f.evidence as Record<string, unknown>[]) || [];
    for (const e of evidenceRaw.slice(0, 3)) {
      evidence.push({
        source: (e.source as string) || (e.source_name as string) || "Unknown",
        snippet: (e.snippet as string) || (e.text as string) || "",
        url: e.url as string | undefined,
      });
    }

    // Research agents from trial-level metadata
    const researchAgents: Array<{ agent_name: string; citations: number }> = [];
    const researchCoverage = (trial.research_coverage as Record<string, unknown>) || {};
    for (const [agentName, agentData] of Object.entries(researchCoverage)) {
      const data = agentData as Record<string, unknown>;
      researchAgents.push({
        agent_name: agentName,
        citations: (data.citations_count as number) || 0,
      });
    }

    // Verification info
    const verification = (trial.verification as Record<string, unknown>) || {};
    const fieldVerification = (verification.field_results as Record<string, unknown>)?.[name] as Record<string, unknown> | undefined;
    let verifierAgreeCount = 0;
    let verifierTotal = 0;
    let verificationSummary = "";
    if (fieldVerification) {
      verifierAgreeCount = (fieldVerification.agree_count as number) || 0;
      verifierTotal = (fieldVerification.total_verifiers as number) || 0;
      verificationSummary = `${verifierAgreeCount}/${verifierTotal} agree`;
    } else {
      // Try top-level verification summary
      const opinions = (verification.opinions as Record<string, unknown>[]) || [];
      verifierTotal = opinions.length;
      verifierAgreeCount = opinions.filter((o) => o.agrees).length;
      if (verifierTotal > 0) {
        verificationSummary = `${verifierAgreeCount}/${verifierTotal} agree`;
      }
    }

    fields[name] = {
      final_value: (f.final_value as string) || "",
      confidence: f.confidence as number | undefined,
      reasoning: (f.reasoning as string) || (f.primary_reasoning as string) || "",
      model_name: (f.model_name as string) || (f.primary_model as string) || "",
      evidence,
      verification_summary: verificationSummary,
      verifier_agree_count: verifierAgreeCount,
      verifier_total: verifierTotal,
      research_agents: researchAgents,
    };
  }
  return fields;
}

// --- Diagnostics card (v17) ---
function DiagnosticsCard({ diagnostics }: { diagnostics: Record<string, unknown> }) {
  const warnings = (diagnostics.warnings as string[]) || [];
  const timeouts = (diagnostics.timeouts as Record<string, number>) || {};
  const retries = (diagnostics.retries as Record<string, number>) || {};
  const timingAnomalies = (diagnostics.timing_anomalies as number) || 0;
  const qualityIssues = (diagnostics.quality_issues as number) || 0;

  const totalTimeouts = Object.values(timeouts).reduce((a, b) => a + b, 0);
  const totalRetries = Object.values(retries).reduce((a, b) => a + b, 0);
  const hasIssues = totalTimeouts > 0 || totalRetries > 0 || warnings.length > 0;

  if (!hasIssues) return null;

  return (
    <div className="card" style={{ marginTop: "1rem", borderLeft: "3px solid var(--warning)" }}>
      <div className="card-title">Diagnostics</div>
      <div style={{ display: "flex", gap: "2rem", flexWrap: "wrap", marginBottom: "0.75rem" }}>
        {totalTimeouts > 0 && (
          <div>
            <span style={{ color: "var(--error)", fontWeight: 600 }}>
              {totalTimeouts} timeout{totalTimeouts > 1 ? "s" : ""}
            </span>
            <div className="text-sm text-muted">
              {Object.entries(timeouts).map(([model, count]) => (
                <div key={model}>{model}: {count}</div>
              ))}
            </div>
          </div>
        )}
        {totalRetries > 0 && (
          <div>
            <span style={{ color: "var(--warning)", fontWeight: 600 }}>
              {totalRetries} retry attempt{totalRetries > 1 ? "s" : ""}
            </span>
            <div className="text-sm text-muted">
              {Object.entries(retries).map(([type, count]) => (
                <div key={type}>{type}: {count}</div>
              ))}
            </div>
          </div>
        )}
        {timingAnomalies > 0 && (
          <div>
            <span style={{ fontWeight: 600 }}>{timingAnomalies} slow trial{timingAnomalies > 1 ? "s" : ""}</span>
          </div>
        )}
        {qualityIssues > 0 && (
          <div>
            <span style={{ fontWeight: 600 }}>{qualityIssues} quality issue{qualityIssues > 1 ? "s" : ""}</span>
          </div>
        )}
      </div>
      {warnings.length > 0 && (
        <details>
          <summary className="text-sm" style={{ cursor: "pointer", color: "var(--text-secondary)" }}>
            {warnings.length} warning{warnings.length > 1 ? "s" : ""} (click to expand)
          </summary>
          <div style={{ marginTop: "0.5rem", maxHeight: "200px", overflow: "auto" }}>
            {warnings.map((w, i) => (
              <div key={i} className="text-sm text-muted" style={{ marginBottom: "0.25rem" }}>{w}</div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

// --- Summary cards ---
function SummaryCards({ summary }: { summary: ResultSummary }) {
  return (
    <div className="summary-cards">
      <div className="summary-card">
        <div className="summary-card-number" style={{ color: "var(--text-primary)" }}>
          {summary.total_trials}
        </div>
        <div className="summary-card-label">Total Trials</div>
      </div>
      <div className="summary-card">
        <div className="summary-card-number" style={{ color: "var(--success)" }}>
          {summary.successful}
        </div>
        <div className="summary-card-label">Successful</div>
      </div>
      <div className="summary-card">
        <div className="summary-card-number" style={{ color: "var(--error)" }}>
          {summary.failed}
        </div>
        <div className="summary-card-label">Failed</div>
      </div>
      <div className="summary-card">
        <div className="summary-card-number" style={{ color: "var(--warning)" }}>
          {summary.manual_review}
        </div>
        <div className="summary-card-label">Flagged for Review</div>
      </div>
    </div>
  );
}

// --- Expanded row detail ---
function RowDetail({ trial }: { trial: Record<string, unknown> }) {
  const fieldData = extractFieldData(trial);
  // Pick the first field that has reasoning for display
  const fieldWithReasoning = Object.values(fieldData).find((f) => f.reasoning);
  const anyField = Object.values(fieldData)[0];

  return (
    <div className="row-detail">
      {/* Evidence section */}
      {anyField?.evidence && anyField.evidence.length > 0 && (
        <div className="row-detail-section">
          <div className="row-detail-title">Evidence</div>
          {anyField.evidence.map((e, i) => (
            <div key={i} className="text-sm mb-1" style={{ paddingLeft: "0.5rem", borderLeft: "2px solid var(--border)" }}>
              <strong>{e.source}</strong>
              {e.snippet && <div className="text-muted" style={{ marginTop: "0.2rem" }}>{e.snippet}</div>}
            </div>
          ))}
        </div>
      )}

      {/* Reasoning section */}
      {fieldWithReasoning?.reasoning && (
        <div className="row-detail-section">
          <div className="row-detail-title">Reasoning</div>
          <div className="text-sm text-muted" style={{ whiteSpace: "pre-wrap" }}>
            {fieldWithReasoning.model_name && (
              <span style={{ color: "var(--accent)", marginRight: "0.5rem" }}>
                [{fieldWithReasoning.model_name}]
              </span>
            )}
            {fieldWithReasoning.reasoning}
          </div>
        </div>
      )}

      {/* Verification section */}
      {anyField?.verification_summary && (
        <div className="row-detail-section">
          <div className="row-detail-title">Verification</div>
          <div className="text-sm">
            {Object.entries(fieldData).map(([fieldName, data]) => (
              data.verification_summary ? (
                <span key={fieldName} style={{ marginRight: "1.5rem" }}>
                  <span className="text-muted">{fieldName}:</span>{" "}
                  <strong style={{
                    color: data.verifier_agree_count === data.verifier_total
                      ? "var(--success)"
                      : data.verifier_agree_count! >= 2
                        ? "var(--warning)"
                        : "var(--error)",
                  }}>
                    {data.verification_summary}
                  </strong>
                </span>
              ) : null
            ))}
          </div>
        </div>
      )}

      {/* Research agents section */}
      {anyField?.research_agents && anyField.research_agents.length > 0 && (
        <div className="row-detail-section">
          <div className="row-detail-title">Research</div>
          <div className="text-sm flex gap-2 flex-wrap">
            {anyField.research_agents.map((agent, i) => (
              <span key={i} className="text-muted">
                {agent.agent_name}: {agent.citations} citation{agent.citations !== 1 ? "s" : ""}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// --- Copy markdown summary ---
function copyMarkdownSummary(summary: ResultSummary, trials: Record<string, unknown>[]) {
  const lines = [
    `## Job ${summary.job_id} Summary`,
    "",
    `| Metric | Count |`,
    `|--------|-------|`,
    `| Total Trials | ${summary.total_trials} |`,
    `| Successful | ${summary.successful} |`,
    `| Failed | ${summary.failed} |`,
    `| Review | ${summary.manual_review} |`,
    "",
    `### Annotations`,
    "",
    `| NCT ID | Classification | Delivery Mode | Outcome | Failure Reason | Peptide | Status |`,
    `|--------|---------------|---------------|---------|----------------|---------|--------|`,
  ];

  for (const trial of trials) {
    const fields = extractFieldData(trial);
    const flagged = (trial.verification as Record<string, unknown>)?.flagged_for_review;
    lines.push(
      `| ${trial.nct_id} | ${fields.classification?.final_value || "\u2014"} | ${fields.delivery_mode?.final_value || "\u2014"} | ${fields.outcome?.final_value || "\u2014"} | ${fields.reason_for_failure?.final_value || "\u2014"} | ${fields.peptide?.final_value || "\u2014"} | ${flagged ? "Review" : "OK"} |`
    );
  }

  navigator.clipboard.writeText(lines.join("\n")).catch(() => {
    // Fallback: do nothing on clipboard failure
  });
}

// --- Results list (job listing view) ---
function ResultsList() {
  const navigate = useNavigate();
  const [results, setResults] = useState<ResultListItem[]>([]);
  const [jobStatuses, setJobStatuses] = useState<Record<string, string>>({});
  const [resumingJob, setResumingJob] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const [data, jobs] = await Promise.all([listResults(), listJobs()]);
        setResults(data.results || []);
        const statusMap: Record<string, string> = {};
        for (const job of jobs) {
          statusMap[job.job_id] = job.status;
        }
        setJobStatuses(statusMap);
      } catch (e) {
        console.error("Failed to load results", e);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const handleResume = async (e: React.MouseEvent, jobId: string) => {
    e.stopPropagation();
    setResumingJob(jobId);
    try {
      await resumeJob(jobId, true);
      navigate(`/pipeline/${jobId}`);
    } catch (err) {
      console.error("Failed to resume job", err);
      alert(`Failed to resume job: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setResumingJob(null);
    }
  };

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
                <th>Duration</th>
                <th>Version</th>
                <th>Date</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r) => {
                const status = jobStatuses[r.job_id];
                const canResume = status === "cancelled" || status === "failed";
                return (
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
                    <td className="text-sm text-muted"><TimingBadge timing={r.timing} /></td>
                    <td className="text-sm text-muted">{r.version || "\u2014"}</td>
                    <td className="text-sm text-muted">
                      {r.timestamp || "\u2014"}
                    </td>
                    <td>
                      {canResume && (
                        <button
                          className="btn btn-secondary"
                          style={{
                            padding: "0.2rem 0.6rem",
                            fontSize: "0.8rem",
                            background: "var(--warning)",
                            color: "var(--bg-primary)",
                            border: "none",
                          }}
                          disabled={resumingJob === r.job_id}
                          onClick={(e) => handleResume(e, r.job_id)}
                        >
                          {resumingJob === r.job_id ? "Resuming..." : "Resume"}
                        </button>
                      )}
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

// --- Result detail dashboard ---
function ResultDetail({ jobId }: { jobId: string }) {
  const navigate = useNavigate();
  const [results, setResults] = useState<Record<string, unknown> | null>(null);
  const [summary, setSummary] = useState<ResultSummary | null>(null);
  const [jobStatus, setJobStatus] = useState<string | null>(null);
  const [resuming, setResuming] = useState(false);
  const [error, setError] = useState("");
  const [showJson, setShowJson] = useState(false);
  const [expandedRow, setExpandedRow] = useState<number | null>(null);
  const [statusFilter, setStatusFilter] = useState<"all" | "ok" | "review">("all");
  const [searchText, setSearchText] = useState("");
  const [copiedMarkdown, setCopiedMarkdown] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [res, sum, jobs] = await Promise.all([
          getResults(jobId),
          getResultsSummary(jobId),
          listJobs(),
        ]);
        setResults(res);
        setSummary(sum);
        const match = jobs.find((j: JobSummary) => j.job_id === jobId);
        if (match) setJobStatus(match.status);
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : "Unknown error";
        setError(msg);
      }
    })();
  }, [jobId]);

  const handleResume = async () => {
    setResuming(true);
    try {
      await resumeJob(jobId, true);
      navigate(`/pipeline/${jobId}`);
    } catch (err) {
      console.error("Failed to resume job", err);
      alert(`Failed to resume job: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setResuming(false);
    }
  };

  const canResume = jobStatus === "cancelled" || jobStatus === "failed";

  const trials = useMemo(() => {
    return (results?.trials as Record<string, unknown>[]) || [];
  }, [results]);

  const filteredTrials = useMemo(() => {
    return trials.filter((trial) => {
      const nctId = (trial.nct_id as string) || "";
      const flagged = !!(trial.verification as Record<string, unknown>)?.flagged_for_review;

      // Status filter
      if (statusFilter === "ok" && flagged) return false;
      if (statusFilter === "review" && !flagged) return false;

      // Text search on NCT ID
      if (searchText && !nctId.toLowerCase().includes(searchText.toLowerCase())) return false;

      return true;
    });
  }, [trials, statusFilter, searchText]);

  if (error) return <div className="card" style={{ color: "var(--error)" }}>{error}</div>;
  if (!results) return <div className="card text-muted">Loading results...</div>;

  const handleCopyMarkdown = () => {
    if (summary) {
      copyMarkdownSummary(summary, trials);
      setCopiedMarkdown(true);
      setTimeout(() => setCopiedMarkdown(false), 2000);
    }
  };

  return (
    <div>
      {/* Header */}
      <div className="flex-between mb-2">
        <div>
          <button className="btn btn-secondary" onClick={() => navigate("/results")} style={{ marginRight: "1rem" }}>
            &larr; All Results
          </button>
          <strong style={{ fontSize: "1.1rem" }}>Results: {jobId}</strong>
          {canResume && (
            <button
              className="btn btn-secondary"
              style={{
                marginLeft: "1rem",
                padding: "0.3rem 0.8rem",
                background: "var(--warning)",
                color: "var(--bg-primary)",
                border: "none",
                fontWeight: 600,
              }}
              disabled={resuming}
              onClick={handleResume}
            >
              {resuming ? "Resuming..." : `Resume (${jobStatus})`}
            </button>
          )}
        </div>
      </div>

      {results.version && (
        <div className="text-sm text-muted mb-2">
          v{(results.version as Record<string, string>).version || (results.version as Record<string, string>).semantic_version || ""}{" "}
          ({(results.version as Record<string, string>).git_commit_short || (results.version as Record<string, string>).git_commit || ""}){" "}
          | config: {(results.version as Record<string, string>).config_hash || "\u2014"}
        </div>
      )}

      {/* Timing metadata */}
      {(results.timing as TimingInfo | undefined)?.elapsed_seconds ? (() => {
        const t = results.timing as TimingInfo;
        return (
          <div className="text-sm text-muted mb-2" style={{ display: "flex", gap: "1.5rem", flexWrap: "wrap" }}>
            {t.started_at && <span>Started: {t.started_at} PT</span>}
            {t.finished_at && <span>Finished: {t.finished_at} PT</span>}
            <span>Duration: {formatElapsed(t.elapsed_seconds)}</span>
            <span>Avg/trial: {t.avg_seconds_per_trial.toFixed(1)}s</span>
            {t.commit_hash && <span>Commit: {t.commit_hash}</span>}
          </div>
        );
      })() : null}

      {/* Section 1: Summary cards */}
      {summary && <SummaryCards summary={summary} />}

      {/* Section 1b: Diagnostics (v17) */}
      {results?.diagnostics && (
        <DiagnosticsCard diagnostics={results.diagnostics as Record<string, unknown>} />
      )}

      {/* Section 2: Filter bar */}
      <div className="filter-bar">
        <label style={{ marginBottom: 0, minWidth: "auto" }}>Status:</label>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as "all" | "ok" | "review")}
        >
          <option value="all">All</option>
          <option value="ok">OK</option>
          <option value="review">Review</option>
        </select>
        <input
          type="text"
          placeholder="Search NCT ID..."
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
        />
        <span className="text-sm text-muted" style={{ marginLeft: "auto" }}>
          {filteredTrials.length} of {trials.length} trials
        </span>
      </div>

      {/* Section 2: Enhanced annotation table */}
      <div className="card">
        {filteredTrials.length > 0 ? (
          <table>
            <thead>
              <tr>
                <th>NCT ID</th>
                <th>Classification</th>
                <th>Delivery Mode</th>
                <th>Outcome</th>
                <th>Failure Reason</th>
                <th>Peptide</th>
                <th>Status</th>
              </tr>
            </thead>
              {filteredTrials.map((trial: Record<string, unknown>, i: number) => {
                const fieldData = extractFieldData(trial);
                const flagged = !!(trial.verification as Record<string, unknown>)?.flagged_for_review;
                const isExpanded = expandedRow === i;
                const originalIndex = trials.indexOf(trial);

                const renderCell = (fieldName: string) => {
                  const data = fieldData[fieldName];
                  if (!data || !data.final_value) return <td>{"\u2014"}</td>;
                  return (
                    <td>
                      {data.final_value}
                      <ConfidenceDot confidence={data.confidence} />
                    </td>
                  );
                };

                return (
                  <tbody key={originalIndex}>
                    <tr
                      className="clickable-row"
                      onClick={() => setExpandedRow(isExpanded ? null : i)}
                    >
                      <td><strong>{trial.nct_id as string}</strong></td>
                      {renderCell("classification")}
                      {renderCell("delivery_mode")}
                      {renderCell("outcome")}
                      {renderCell("reason_for_failure")}
                      {renderCell("peptide")}
                      <td>
                        {flagged ? (
                          <span className="badge badge-cancelled">Review</span>
                        ) : (
                          <span className="badge badge-completed">OK</span>
                        )}
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr>
                        <td colSpan={7} style={{ padding: 0 }}>
                          <RowDetail trial={trial} />
                        </td>
                      </tr>
                    )}
                  </tbody>
                );
              })}
          </table>
        ) : (
          <div className="text-muted">No trial results match the current filters.</div>
        )}
      </div>

      {/* Section 3: Export buttons */}
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
        <button className="btn btn-secondary" onClick={handleCopyMarkdown}>
          {copiedMarkdown ? "Copied!" : "Copy summary as markdown"}
        </button>
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

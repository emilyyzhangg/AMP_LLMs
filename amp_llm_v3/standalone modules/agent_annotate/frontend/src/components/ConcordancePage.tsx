import { useState, useEffect, useMemo } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer,
  LineChart, Line, CartesianGrid,
} from "recharts";
import {
  getConcordanceJobs,
  getJobConcordance,
  compareJobs,
  getConcordanceHistory,
  getHumanConcordance,
} from "../api/client";
import type {
  JobConcordance,
  ConcordanceField,
  ComparisonResult,
  ConcordanceHistoryEntry,
} from "../types";

// ── Helpers ──────────────────────────────────────────────────────────

function kappaColor(k: number): string {
  if (k > 0.6) return "var(--success)";
  if (k >= 0.2) return "var(--warning)";
  return "var(--error)";
}

function kappaBg(k: number): string {
  if (k > 0.6) return "#064e3b";
  if (k >= 0.2) return "#3b3314";
  return "#451a1a";
}

const FIELD_COLORS: Record<string, string> = {
  classification: "#7c8cff",
  delivery_mode: "#34d399",
  outcome: "#fbbf24",
  reason_for_failure: "#f87171",
  peptide: "#a78bfa",
};

function fieldColor(name: string): string {
  return FIELD_COLORS[name] || "#7c8cff";
}

// ── Tab wrapper ──────────────────────────────────────────────────────

type TabKey = "agent-human" | "version-compare" | "human-inter" | "trends";

const TABS: { key: TabKey; label: string }[] = [
  { key: "agent-human", label: "Agent vs Human" },
  { key: "version-compare", label: "Version Comparison" },
  { key: "human-inter", label: "Human Inter-Rater" },
  { key: "trends", label: "Trends" },
];

// ── Concordance summary table (reused in Tab 1 & 3) ─────────────────

function ConcordanceSummaryTable({
  fields,
  label,
}: {
  fields: ConcordanceField[];
  label: string;
}) {
  return (
    <div className="card mb-2">
      <div className="card-title">{label}</div>
      <table>
        <thead>
          <tr>
            <th>Field</th>
            <th>N</th>
            <th>Agree %</th>
            <th style={{ textAlign: "center" }}>&kappa;</th>
            <th>Interpretation</th>
          </tr>
        </thead>
        <tbody>
          {fields.map((f) => (
            <tr key={f.field_name}>
              <td style={{ fontWeight: 500 }}>{f.field_name}</td>
              <td>{f.n}</td>
              <td>{f.agree_pct.toFixed(1)}%</td>
              <td
                style={{
                  textAlign: "center",
                  fontWeight: 600,
                  color: kappaColor(f.kappa),
                  background: kappaBg(f.kappa),
                  borderRadius: "4px",
                }}
              >
                {f.kappa.toFixed(3)}
              </td>
              <td className="text-sm text-muted">{f.interpretation}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Expandable field detail ──────────────────────────────────────────

function FieldDetail({ field }: { field: ConcordanceField }) {
  const [open, setOpen] = useState(false);

  // Build bar-chart data from value distributions
  const distData = useMemo(() => {
    const keys = new Set<string>();
    Object.keys(field.value_distribution.agent).forEach((k) => keys.add(k));
    Object.keys(field.value_distribution.human).forEach((k) => keys.add(k));
    return Array.from(keys)
      .sort()
      .map((value) => ({
        value,
        Agent: field.value_distribution.agent[value] || 0,
        Human: field.value_distribution.human[value] || 0,
      }));
  }, [field]);

  // Build confusion-matrix rows/cols
  const cmRows = Object.keys(field.confusion_matrix).sort();
  const cmColSet = new Set<string>();
  cmRows.forEach((r) =>
    Object.keys(field.confusion_matrix[r]).forEach((c) => cmColSet.add(c)),
  );
  const cmCols = Array.from(cmColSet).sort();
  const maxCount = Math.max(
    1,
    ...cmRows.flatMap((r) => cmCols.map((c) => field.confusion_matrix[r]?.[c] || 0)),
  );

  return (
    <div className="card mb-2">
      <button
        className="btn btn-secondary"
        onClick={() => setOpen(!open)}
        style={{ width: "100%", justifyContent: "space-between" }}
      >
        <span style={{ fontWeight: 500 }}>{field.field_name}</span>
        <span className="text-sm text-muted">
          &kappa; = {field.kappa.toFixed(3)} &middot; {field.agree_pct.toFixed(1)}% agree
          &middot; {open ? "Collapse" : "Expand"}
        </span>
      </button>

      {open && (
        <div style={{ marginTop: "1rem" }}>
          {/* Value distribution bar chart */}
          <div className="card-title">Value Distribution</div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={distData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
              <XAxis
                dataKey="value"
                tick={{ fill: "var(--text-secondary)", fontSize: 12 }}
                interval={0}
                angle={-30}
                textAnchor="end"
                height={60}
              />
              <YAxis tick={{ fill: "var(--text-secondary)", fontSize: 12 }} />
              <Tooltip
                contentStyle={{
                  background: "var(--bg-card)",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius)",
                  color: "var(--text-primary)",
                }}
              />
              <Legend wrapperStyle={{ color: "var(--text-secondary)", fontSize: 12 }} />
              <Bar dataKey="Agent" fill="var(--accent)" radius={[3, 3, 0, 0]} />
              <Bar dataKey="Human" fill="var(--success)" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>

          {/* Confusion matrix */}
          {cmRows.length > 0 && (
            <>
              <div className="card-title mt-2">Confusion Matrix</div>
              <div style={{ overflowX: "auto" }}>
                <table style={{ fontSize: "0.8rem" }}>
                  <thead>
                    <tr>
                      <th style={{ fontSize: "0.75rem" }}>Agent \ Human</th>
                      {cmCols.map((c) => (
                        <th key={c} style={{ textAlign: "center", fontSize: "0.75rem" }}>{c}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {cmRows.map((r) => (
                      <tr key={r}>
                        <td style={{ fontWeight: 500, fontSize: "0.8rem" }}>{r}</td>
                        {cmCols.map((c) => {
                          const count = field.confusion_matrix[r]?.[c] || 0;
                          const intensity = count / maxCount;
                          const isAgree = r === c;
                          const bgColor = isAgree
                            ? `rgba(52, 211, 153, ${0.1 + intensity * 0.5})`
                            : count > 0
                              ? `rgba(248, 113, 113, ${0.1 + intensity * 0.4})`
                              : "transparent";
                          return (
                            <td
                              key={c}
                              style={{
                                textAlign: "center",
                                background: bgColor,
                                fontWeight: count > 0 ? 600 : 400,
                                color: count > 0 ? "var(--text-primary)" : "var(--text-secondary)",
                              }}
                            >
                              {count || "\u2014"}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {/* Disagreement list */}
          {field.disagreements.length > 0 && (
            <>
              <div className="card-title mt-2">
                Disagreements ({field.disagreements.length})
              </div>
              <div style={{ maxHeight: "250px", overflowY: "auto" }}>
                <table style={{ fontSize: "0.8rem" }}>
                  <thead>
                    <tr>
                      <th>NCT ID</th>
                      <th>Agent</th>
                      <th>Human</th>
                    </tr>
                  </thead>
                  <tbody>
                    {field.disagreements.map((d, i) => (
                      <tr key={i}>
                        <td>{d.nct_id}</td>
                        <td>{d.agent_value}</td>
                        <td>{d.human_value}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ── Tab 1: Agent vs Human ────────────────────────────────────────────

function AgentVsHumanTab() {
  const [jobs, setJobs] = useState<string[]>([]);
  const [selectedJob, setSelectedJob] = useState("");
  const [concordance, setConcordance] = useState<{
    agent_vs_r1: JobConcordance;
    agent_vs_r2: JobConcordance;
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Load job list
  useEffect(() => {
    (async () => {
      try {
        const data = await getConcordanceJobs();
        setJobs(Array.isArray(data.jobs) ? data.jobs : []);
      } catch {
        console.error("Failed to load job list");
      }
    })();
  }, []);

  // Load concordance for selected job
  useEffect(() => {
    if (!selectedJob) {
      setConcordance(null);
      return;
    }
    setLoading(true);
    setError("");
    (async () => {
      try {
        const data = await getJobConcordance(selectedJob);
        setConcordance(data);
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Unknown error";
        setError(msg);
        setConcordance(null);
      } finally {
        setLoading(false);
      }
    })();
  }, [selectedJob]);

  return (
    <div>
      <div className="card mb-2">
        <label htmlFor="job-select">Select completed job</label>
        <select
          id="job-select"
          value={selectedJob}
          onChange={(e) => setSelectedJob(e.target.value)}
          style={{ maxWidth: "400px" }}
        >
          <option value="">-- choose a job --</option>
          {jobs.map((j) => (
            <option key={j} value={j}>
              {j}
            </option>
          ))}
        </select>
      </div>

      {loading && <div className="card text-muted">Loading concordance data...</div>}
      {error && <div className="card" style={{ color: "var(--error)" }}>{error}</div>}

      {concordance && (
        <>
          {/* Summary tables */}
          <ConcordanceSummaryTable
            fields={concordance.agent_vs_r1.fields}
            label={`Agent vs R1 — Overall ${concordance.agent_vs_r1.overall_agree_pct.toFixed(1)}% agreement`}
          />
          <ConcordanceSummaryTable
            fields={concordance.agent_vs_r2.fields}
            label={`Agent vs R2 — Overall ${concordance.agent_vs_r2.overall_agree_pct.toFixed(1)}% agreement`}
          />

          {/* Per-field expandable details (use R1 data, which has the full matrices) */}
          <h3 style={{ margin: "1.5rem 0 0.75rem" }}>Field Details (Agent vs R1)</h3>
          {concordance.agent_vs_r1.fields.map((f) => (
            <FieldDetail key={f.field_name} field={f} />
          ))}

          <h3 style={{ margin: "1.5rem 0 0.75rem" }}>Field Details (Agent vs R2)</h3>
          {concordance.agent_vs_r2.fields.map((f) => (
            <FieldDetail key={f.field_name} field={f} />
          ))}
        </>
      )}
    </div>
  );
}

// ── Tab 2: Version Comparison ────────────────────────────────────────

function VersionCompareTab() {
  const [jobs, setJobs] = useState<string[]>([]);
  const [jobA, setJobA] = useState("");
  const [jobB, setJobB] = useState("");
  const [result, setResult] = useState<ComparisonResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const data = await getConcordanceJobs();
        setJobs(Array.isArray(data.jobs) ? data.jobs : []);
      } catch {
        console.error("Failed to load job list");
      }
    })();
  }, []);

  useEffect(() => {
    if (!jobA || !jobB || jobA === jobB) {
      setResult(null);
      return;
    }
    setLoading(true);
    setError("");
    (async () => {
      try {
        const data = await compareJobs(jobA, jobB);
        setResult(data);
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Unknown error";
        setError(msg);
        setResult(null);
      } finally {
        setLoading(false);
      }
    })();
  }, [jobA, jobB]);

  // Build bar-chart data
  const chartData = useMemo(() => {
    if (!result) return [];
    return result.fields.map((f) => ({
      field: f.field_name,
      "Job A": f.kappa_a,
      "Job B": f.kappa_b,
    }));
  }, [result]);

  return (
    <div>
      <div className="card mb-2" style={{ display: "flex", gap: "1rem", flexWrap: "wrap", alignItems: "flex-end" }}>
        <div style={{ flex: 1, minWidth: "200px" }}>
          <label htmlFor="job-a-select">Job A</label>
          <select id="job-a-select" value={jobA} onChange={(e) => setJobA(e.target.value)}>
            <option value="">-- select job A --</option>
            {jobs.map((j) => (
              <option key={j} value={j}>
                {j}
              </option>
            ))}
          </select>
        </div>
        <div style={{ flex: 1, minWidth: "200px" }}>
          <label htmlFor="job-b-select">Job B</label>
          <select id="job-b-select" value={jobB} onChange={(e) => setJobB(e.target.value)}>
            <option value="">-- select job B --</option>
            {jobs.map((j) => (
              <option key={j} value={j}>
                {j}
              </option>
            ))}
          </select>
        </div>
      </div>

      {loading && <div className="card text-muted">Comparing jobs...</div>}
      {error && <div className="card" style={{ color: "var(--error)" }}>{error}</div>}

      {result && (
        <>
          {/* Summary counts */}
          {(() => {
            const improved = result.fields.filter((f) => f.improved).length;
            const regressed = result.fields.filter((f) => !f.improved && f.delta < 0).length;
            const unchanged = result.fields.length - improved - regressed;
            return (
              <div className="card mb-2" style={{ display: "flex", gap: "2rem" }}>
                <span style={{ color: "var(--success)", fontWeight: 600 }}>
                  {improved} improved
                </span>
                <span style={{ color: "var(--error)", fontWeight: 600 }}>
                  {regressed} regressed
                </span>
                <span className="text-muted">
                  {unchanged} unchanged
                </span>
              </div>
            );
          })()}

          {/* Comparison table */}
          <div className="card mb-2">
            <table>
              <thead>
                <tr>
                  <th>Field</th>
                  <th style={{ textAlign: "center" }}>&kappa; (Job A)</th>
                  <th style={{ textAlign: "center" }}>&kappa; (Job B)</th>
                  <th style={{ textAlign: "center" }}>&Delta;</th>
                  <th style={{ textAlign: "center" }}>Direction</th>
                </tr>
              </thead>
              <tbody>
                {result.fields.map((f) => (
                  <tr key={f.field_name}>
                    <td style={{ fontWeight: 500 }}>{f.field_name}</td>
                    <td
                      style={{
                        textAlign: "center",
                        color: kappaColor(f.kappa_a),
                        background: kappaBg(f.kappa_a),
                        borderRadius: "4px",
                        fontWeight: 600,
                      }}
                    >
                      {f.kappa_a.toFixed(3)}
                    </td>
                    <td
                      style={{
                        textAlign: "center",
                        color: kappaColor(f.kappa_b),
                        background: kappaBg(f.kappa_b),
                        borderRadius: "4px",
                        fontWeight: 600,
                      }}
                    >
                      {f.kappa_b.toFixed(3)}
                    </td>
                    <td
                      style={{
                        textAlign: "center",
                        fontWeight: 600,
                        color: f.delta > 0 ? "var(--success)" : f.delta < 0 ? "var(--error)" : "var(--text-secondary)",
                      }}
                    >
                      {f.delta > 0 ? "+" : ""}{f.delta.toFixed(3)}
                    </td>
                    <td style={{ textAlign: "center", fontSize: "1.2rem" }}>
                      {f.improved ? (
                        <span style={{ color: "var(--success)" }} title="Improved">{"\u2191"}</span>
                      ) : f.delta < 0 ? (
                        <span style={{ color: "var(--error)" }} title="Regressed">{"\u2193"}</span>
                      ) : (
                        <span className="text-muted">{"\u2014"}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Side-by-side kappa bar chart */}
          <div className="card">
            <div className="card-title">Kappa Comparison</div>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                <XAxis
                  dataKey="field"
                  tick={{ fill: "var(--text-secondary)", fontSize: 12 }}
                  interval={0}
                  angle={-20}
                  textAnchor="end"
                  height={50}
                />
                <YAxis
                  domain={[-0.1, 1]}
                  tick={{ fill: "var(--text-secondary)", fontSize: 12 }}
                />
                <Tooltip
                  contentStyle={{
                    background: "var(--bg-card)",
                    border: "1px solid var(--border)",
                    borderRadius: "var(--radius)",
                    color: "var(--text-primary)",
                  }}
                  formatter={(value: number) => value.toFixed(3)}
                />
                <Legend wrapperStyle={{ color: "var(--text-secondary)", fontSize: 12 }} />
                <Bar dataKey="Job A" fill="var(--accent)" radius={[3, 3, 0, 0]} />
                <Bar dataKey="Job B" fill="var(--success)" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </div>
  );
}

// ── Tab 3: Human Inter-Rater ─────────────────────────────────────────

function HumanInterRaterTab() {
  const [concordance, setConcordance] = useState<JobConcordance | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const data = await getHumanConcordance();
        setConcordance(data);
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Unknown error";
        setError(msg);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) return <div className="card text-muted">Loading human inter-rater data...</div>;
  if (error) return <div className="card" style={{ color: "var(--error)" }}>{error}</div>;
  if (!concordance) return <div className="card text-muted">No data available.</div>;

  return (
    <div>
      <div className="card mb-2" style={{ color: "var(--text-secondary)", fontSize: "0.9rem" }}>
        This shows how often human annotators agree with each other, providing a baseline for
        interpreting agent performance. Fields where humans frequently disagree (low kappa) are
        inherently harder to annotate, so lower agent agreement on those fields may be expected.
      </div>

      <ConcordanceSummaryTable
        fields={concordance.fields}
        label={`R1 vs R2 — Overall ${concordance.overall_agree_pct.toFixed(1)}% agreement`}
      />

      {concordance.fields.map((f) => (
        <FieldDetail key={f.field_name} field={f} />
      ))}
    </div>
  );
}

// ── Tab 4: Trends ────────────────────────────────────────────────────

function TrendsTab() {
  const [history, setHistory] = useState<ConcordanceHistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const data = await getConcordanceHistory();
        setHistory(data.history || []);
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Unknown error";
        setError(msg);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // Derive all field names from history entries
  const fieldNames = useMemo(() => {
    const names = new Set<string>();
    history.forEach((h) => Object.keys(h.field_kappas).forEach((k) => names.add(k)));
    return Array.from(names).sort();
  }, [history]);

  // Build line-chart data
  const chartData = useMemo(() => {
    return history.map((h) => ({
      label: h.timestamp || h.job_id,
      ...h.field_kappas,
    }));
  }, [history]);

  if (loading) return <div className="card text-muted">Loading trend data...</div>;
  if (error) return <div className="card" style={{ color: "var(--error)" }}>{error}</div>;
  if (history.length === 0) return <div className="card text-muted">No concordance history available yet.</div>;

  return (
    <div className="card">
      <div className="card-title">Kappa Trends Across Jobs</div>
      <ResponsiveContainer width="100%" height={360}>
        <LineChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis
            dataKey="label"
            tick={{ fill: "var(--text-secondary)", fontSize: 11 }}
            interval={0}
            angle={-30}
            textAnchor="end"
            height={70}
          />
          <YAxis
            domain={[-0.1, 1]}
            tick={{ fill: "var(--text-secondary)", fontSize: 12 }}
            label={{
              value: "Cohen's \u03BA",
              angle: -90,
              position: "insideLeft",
              style: { fill: "var(--text-secondary)", fontSize: 12 },
            }}
          />
          <Tooltip
            contentStyle={{
              background: "var(--bg-card)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius)",
              color: "var(--text-primary)",
            }}
            formatter={(value: number) => value.toFixed(3)}
          />
          <Legend wrapperStyle={{ color: "var(--text-secondary)", fontSize: 12 }} />
          {fieldNames.map((name) => (
            <Line
              key={name}
              type="monotone"
              dataKey={name}
              stroke={fieldColor(name)}
              strokeWidth={2}
              dot={{ r: 4, fill: fieldColor(name) }}
              activeDot={{ r: 6 }}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Main page ────────────────────────────────────────────────────────

export default function ConcordancePage() {
  const [activeTab, setActiveTab] = useState<TabKey>("agent-human");

  return (
    <div>
      <h2 style={{ marginBottom: "1rem" }}>Concordance Dashboard</h2>

      {/* Tab bar */}
      <div style={{ display: "flex", gap: "0.25rem", marginBottom: "1.5rem" }}>
        {TABS.map((tab) => (
          <button
            key={tab.key}
            className={`btn ${activeTab === tab.key ? "btn-primary" : "btn-secondary"}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === "agent-human" && <AgentVsHumanTab />}
      {activeTab === "version-compare" && <VersionCompareTab />}
      {activeTab === "human-inter" && <HumanInterRaterTab />}
      {activeTab === "trends" && <TrendsTab />}
    </div>
  );
}

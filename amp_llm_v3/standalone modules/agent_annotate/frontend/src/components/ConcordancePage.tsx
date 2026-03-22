import { useState, useEffect, useMemo } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer,
  ComposedChart, Line, CartesianGrid,
} from "recharts";
import {
  getConcordanceJobs,
  getJobConcordance,
  compareJobs,
  getConcordanceHistory,
  getHumanConcordance,
  getAnnotators,
  getJobAnnotatorsConcordance,
  getHumanAnnotatorsConcordance,
} from "../api/client";
import type {
  JobConcordance,
  ConcordanceField,
  CategoryMetrics,
  ComparisonResult,
  ConcordanceHistoryEntry,
} from "../types";

// ── Helpers ──────────────────────────────────────────────────────────

/** Color for agreement metrics (AC1 or kappa). */
function metricColor(k: number): string {
  if (k > 0.6) return "var(--success)";
  if (k >= 0.2) return "var(--warning)";
  return "var(--error)";
}

/** Background for the primary metric (AC1). */
function metricBg(k: number): string {
  if (k > 0.6) return "#064e3b";
  if (k >= 0.2) return "#3b3314";
  return "#451a1a";
}

// Keep legacy aliases for kappa (used in version-compare tab)
function kappaColor(k: number): string { return metricColor(k); }
function kappaBg(k: number): string { return metricBg(k); }

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
            <th>Skipped</th>
            <th>Coverage</th>
            <th>Agree %</th>
            <th style={{ textAlign: "center" }}>AC&#x2081;</th>
            <th style={{ textAlign: "center" }}>&kappa;</th>
            <th>Interpretation</th>
          </tr>
        </thead>
        <tbody>
          {fields.map((f) => (
            <tr key={f.field_name}>
              <td style={{ fontWeight: 500 }}>{f.field_name}</td>
              <td>{f.n}</td>
              <td className="text-sm text-muted">{f.skipped}</td>
              <td className="text-sm text-muted">
                {f.n + f.skipped > 0 ? `${((f.n / (f.n + f.skipped)) * 100).toFixed(0)}%` : "\u2014"}
              </td>
              <td>{f.agree_pct.toFixed(1)}%</td>
              <td
                style={{
                  textAlign: "center",
                  fontWeight: 600,
                  color: f.ac1 != null ? metricColor(f.ac1) : "var(--text-secondary)",
                  background: f.ac1 != null ? metricBg(f.ac1) : "transparent",
                  borderRadius: "4px",
                }}
              >
                {f.ac1 != null ? f.ac1.toFixed(3) : "N/A"}
              </td>
              <td
                style={{
                  textAlign: "center",
                  color: f.kappa != null ? "var(--text-secondary)" : "var(--text-secondary)",
                }}
              >
                {f.kappa != null ? f.kappa.toFixed(3) : "N/A"}
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

function FieldDetail({ field, labelA = "Agent", labelB = "Human" }: { field: ConcordanceField; labelA?: string; labelB?: string }) {
  const [open, setOpen] = useState(false);

  // Build bar-chart data from value distributions (keys are dynamic: "Agent", "R1", "R2", etc.)
  const distLabels = Object.keys(field.value_distribution);
  const distData = useMemo(() => {
    const allValues = new Set<string>();
    for (const label of distLabels) {
      Object.keys(field.value_distribution[label]).forEach((k) => allValues.add(k));
    }
    return Array.from(allValues)
      .sort()
      .map((value) => {
        const row: Record<string, string | number> = { value };
        for (const label of distLabels) {
          row[label] = field.value_distribution[label][value] || 0;
        }
        return row;
      });
  }, [field, distLabels]);

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
          AC&#x2081; = {field.ac1 != null ? field.ac1.toFixed(3) : "N/A"} &middot; &kappa; = {field.kappa != null ? field.kappa.toFixed(3) : "N/A"} &middot; {field.agree_pct.toFixed(1)}% agree
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
              {distLabels.map((label, i) => (
                <Bar key={label} dataKey={label} fill={i === 0 ? "var(--accent)" : "var(--success)"} radius={[3, 3, 0, 0]} />
              ))}
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
                      <th style={{ fontSize: "0.75rem" }}>{labelA} \ {labelB}</th>
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

          {/* Per-category F1 scores */}
          {field.category_metrics && field.category_metrics.length > 0 && (
            <>
              <div className="card-title mt-2">Per-Category F1 Scores</div>
              <div style={{ overflowX: "auto" }}>
                <table style={{ fontSize: "0.8rem" }}>
                  <thead>
                    <tr>
                      <th>Category</th>
                      <th style={{ textAlign: "center" }}>Count ({labelA})</th>
                      <th style={{ textAlign: "center" }}>Count ({labelB})</th>
                      <th style={{ textAlign: "center" }}>Precision</th>
                      <th style={{ textAlign: "center" }}>Recall</th>
                      <th style={{ textAlign: "center" }}>F1</th>
                    </tr>
                  </thead>
                  <tbody>
                    {field.category_metrics.map((cm: CategoryMetrics) => {
                      const f1Color = cm.f1 != null
                        ? cm.f1 >= 0.8 ? "var(--success)" : cm.f1 >= 0.5 ? "var(--warning)" : "var(--error)"
                        : "var(--text-secondary)";
                      return (
                        <tr key={cm.value || "(blank)"}>
                          <td style={{ fontWeight: 500 }}>{cm.value || "(blank)"}</td>
                          <td style={{ textAlign: "center" }}>{cm.count_a}</td>
                          <td style={{ textAlign: "center" }}>{cm.count_b}</td>
                          <td style={{ textAlign: "center" }}>{cm.precision != null ? cm.precision.toFixed(3) : "\u2014"}</td>
                          <td style={{ textAlign: "center" }}>{cm.recall != null ? cm.recall.toFixed(3) : "\u2014"}</td>
                          <td style={{ textAlign: "center", fontWeight: 600, color: f1Color }}>
                            {cm.f1 != null ? cm.f1.toFixed(3) : "\u2014"}
                          </td>
                        </tr>
                      );
                    })}
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
                      <th>{labelA}</th>
                      <th>{labelB}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {field.disagreements.map((d, i) => (
                      <tr key={i}>
                        <td>{d.nct_id}</td>
                        <td>{d.value_a}</td>
                        <td>{d.value_b}</td>
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

// ── Annotator types and multi-select selector ────────────────────────

interface AnnotatorInfo {
  name: string;
  replicate: string;
  nct_count: number;
}

function AnnotatorSelector({
  annotators,
  selectedR1,
  selectedR2,
  onChangeR1,
  onChangeR2,
}: {
  annotators: AnnotatorInfo[];
  selectedR1: Set<string>;
  selectedR2: Set<string>;
  onChangeR1: (next: Set<string>) => void;
  onChangeR2: (next: Set<string>) => void;
}) {
  const r1Annotators = annotators.filter((a) => a.replicate === "r1");
  const r2Annotators = annotators.filter((a) => a.replicate === "r2");

  const allR1Names = new Set(r1Annotators.map((a) => a.name));
  const allR2Names = new Set(r2Annotators.map((a) => a.name));

  const allR1Selected = allR1Names.size > 0 && [...allR1Names].every((n) => selectedR1.has(n));
  const allR2Selected = allR2Names.size > 0 && [...allR2Names].every((n) => selectedR2.has(n));

  const pillStyle = (active: boolean): React.CSSProperties => ({
    padding: "0.3rem 0.7rem",
    borderRadius: "999px",
    border: active ? "2px solid var(--accent)" : "1px solid var(--border)",
    background: active ? "var(--accent)" : "transparent",
    color: active ? "#fff" : "var(--text-secondary)",
    cursor: "pointer",
    fontSize: "0.8rem",
    fontWeight: active ? 600 : 400,
    whiteSpace: "nowrap",
  });

  const toggleR1 = (name: string) => {
    const next = new Set(selectedR1);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    onChangeR1(next);
  };

  const toggleR2 = (name: string) => {
    const next = new Set(selectedR2);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    onChangeR2(next);
  };

  const toggleAllR1 = () => {
    if (allR1Selected) {
      onChangeR1(new Set());
    } else {
      onChangeR1(new Set(allR1Names));
    }
  };

  const toggleAllR2 = () => {
    if (allR2Selected) {
      onChangeR2(new Set());
    } else {
      onChangeR2(new Set(allR2Names));
    }
  };

  const rowStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: "0.4rem",
    flexWrap: "wrap",
  };

  return (
    <div className="card mb-2" style={{ padding: "0.6rem 1rem" }}>
      {/* Row 1: Aggregate toggles */}
      <div style={{ ...rowStyle, marginBottom: "0.4rem" }}>
        <button style={pillStyle(allR1Selected)} onClick={toggleAllR1}>
          All R1
        </button>
        <button style={pillStyle(allR2Selected)} onClick={toggleAllR2}>
          All R2
        </button>
      </div>
      {/* Row 2: R1 annotators */}
      <div style={{ ...rowStyle, marginBottom: "0.3rem" }}>
        <span className="text-sm text-muted" style={{ fontSize: "0.7rem", minWidth: "1.6rem" }}>R1:</span>
        {r1Annotators.map((a) => (
          <button
            key={`r1-${a.name}`}
            style={pillStyle(selectedR1.has(a.name))}
            onClick={() => toggleR1(a.name)}
          >
            {a.name} ({a.nct_count})
          </button>
        ))}
      </div>
      {/* Row 3: R2 annotators */}
      <div style={rowStyle}>
        <span className="text-sm text-muted" style={{ fontSize: "0.7rem", minWidth: "1.6rem" }}>R2:</span>
        {r2Annotators.map((a) => (
          <button
            key={`r2-${a.name}`}
            style={pillStyle(selectedR2.has(a.name))}
            onClick={() => toggleR2(a.name)}
          >
            {a.name} ({a.nct_count})
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Tab 1: Agent vs Human ────────────────────────────────────────────

function AgentVsHumanTab() {
  const [jobs, setJobs] = useState<Array<{job_id: string; timestamp: string; total_trials: number}>>([]);
  const [selectedJob, setSelectedJob] = useState("");
  const [concordance, setConcordance] = useState<{
    agent_vs_r1: JobConcordance;
    agent_vs_r2: JobConcordance;
    r1_vs_r2: JobConcordance;
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Multi-select annotator state
  const [annotators, setAnnotators] = useState<AnnotatorInfo[]>([]);
  const [selectedR1, setSelectedR1] = useState<Set<string>>(new Set());
  const [selectedR2, setSelectedR2] = useState<Set<string>>(new Set());
  const [r1Concordance, setR1Concordance] = useState<JobConcordance | null>(null);
  const [r2Concordance, setR2Concordance] = useState<JobConcordance | null>(null);
  const [annotatorLoading, setAnnotatorLoading] = useState(false);
  const [initDone, setInitDone] = useState(false);

  // Load job list and annotators
  useEffect(() => {
    (async () => {
      try {
        const data = await getConcordanceJobs();
        setJobs(Array.isArray(data.jobs) ? data.jobs : []);
      } catch {
        console.error("Failed to load job list");
      }
    })();
    (async () => {
      try {
        const data = await getAnnotators();
        const list = Array.isArray(data.annotators) ? data.annotators : [];
        setAnnotators(list);
        // Default: All R1 selected
        const r1Names = new Set(list.filter((a) => a.replicate === "r1").map((a) => a.name));
        setSelectedR1(r1Names);
        setInitDone(true);
      } catch {
        console.error("Failed to load annotators");
        setInitDone(true);
      }
    })();
  }, []);

  // Load base concordance for selected job (used for the comparison grid)
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

  // Load multi-annotator concordance when selections change
  useEffect(() => {
    if (!selectedJob || !initDone) return;

    let cancelled = false;
    setAnnotatorLoading(true);

    const fetchR1 = selectedR1.size > 0
      ? getJobAnnotatorsConcordance(selectedJob, [...selectedR1], "r1")
      : Promise.resolve(null);

    const fetchR2 = selectedR2.size > 0
      ? getJobAnnotatorsConcordance(selectedJob, [...selectedR2], "r2")
      : Promise.resolve(null);

    Promise.all([fetchR1, fetchR2])
      .then(([r1, r2]) => {
        if (!cancelled) {
          setR1Concordance(r1);
          setR2Concordance(r2);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setR1Concordance(null);
          setR2Concordance(null);
        }
      })
      .finally(() => {
        if (!cancelled) setAnnotatorLoading(false);
      });

    return () => { cancelled = true; };
  }, [selectedJob, selectedR1, selectedR2, initDone]);

  // Determine if we're in the "All R1 + no R2" default state (show comparison grid)
  const allR1Names = new Set(annotators.filter((a) => a.replicate === "r1").map((a) => a.name));
  const isDefaultState = selectedR2.size === 0 && allR1Names.size > 0 && [...allR1Names].every((n) => selectedR1.has(n));
  const hasAnySelection = selectedR1.size > 0 || selectedR2.size > 0;

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
            <option key={j.job_id} value={j.job_id}>
              {j.job_id} ({j.total_trials} trials{j.timestamp ? `, ${j.timestamp}` : ""})
            </option>
          ))}
        </select>
      </div>

      {loading && <div className="card text-muted">Loading concordance data...</div>}
      {error && <div className="card" style={{ color: "var(--error)" }}>{error}</div>}

      {concordance && (
        <>
          {/* Multi-select annotator selector */}
          {annotators.length > 0 && (
            <AnnotatorSelector
              annotators={annotators}
              selectedR1={selectedR1}
              selectedR2={selectedR2}
              onChangeR1={setSelectedR1}
              onChangeR2={setSelectedR2}
            />
          )}

          {annotatorLoading && <div className="card text-muted">Loading annotator concordance...</div>}

          {/* Default All R1 state: show full comparison grid */}
          {isDefaultState && !annotatorLoading && (
            <>
              {/* Combined comparison table: Agent vs R1, Agent vs R2, Human baseline (R1 vs R2) */}
              <div className="card mb-2">
                <div className="card-title">
                  Concordance Comparison
                  <span className="text-sm text-muted" style={{ fontWeight: 400, marginLeft: "0.75rem" }}>
                    Green = exceeds human baseline, Red = below
                  </span>
                </div>
                <table>
                  <thead>
                    <tr>
                      <th>Field</th>
                      <th style={{ textAlign: "center", borderLeft: "2px solid var(--border)" }}>Agent vs R1</th>
                      <th style={{ textAlign: "center" }}>Agent vs R2</th>
                      <th style={{ textAlign: "center", borderLeft: "2px solid var(--warning)", background: "rgba(234,179,8,0.05)" }}>R1 vs R2 (Human Baseline)</th>
                      <th style={{ textAlign: "center", borderLeft: "2px solid var(--border)" }}>Verdict</th>
                    </tr>
                  </thead>
                  <tbody>
                    {concordance.agent_vs_r1.fields.map((f, i) => {
                      const r2f = concordance.agent_vs_r2.fields[i];
                      const hf = concordance.r1_vs_r2.fields[i];
                      const agentBest = Math.max(f.agree_pct, r2f?.agree_pct ?? 0);
                      const humanBaseline = hf?.agree_pct ?? 0;
                      const exceeds = agentBest > humanBaseline;
                      return (
                        <tr key={f.field_name}>
                          <td style={{ fontWeight: 500 }}>{f.field_name}</td>
                          <td style={{
                            textAlign: "center",
                            borderLeft: "2px solid var(--border)",
                            fontWeight: 600,
                            color: f.agree_pct > humanBaseline ? "var(--success)" : f.agree_pct < humanBaseline ? "var(--error)" : "var(--text-primary)",
                          }}>
                            {f.agree_pct.toFixed(1)}%
                            <span className="text-sm text-muted" style={{ fontWeight: 400 }}>
                              {" "}(n={f.n}, &kappa;={f.kappa != null ? f.kappa.toFixed(2) : "N/A"})
                            </span>
                          </td>
                          <td style={{
                            textAlign: "center",
                            fontWeight: 600,
                            color: (r2f?.agree_pct ?? 0) > humanBaseline ? "var(--success)" : (r2f?.agree_pct ?? 0) < humanBaseline ? "var(--error)" : "var(--text-primary)",
                          }}>
                            {r2f ? `${r2f.agree_pct.toFixed(1)}%` : "\u2014"}
                            <span className="text-sm text-muted" style={{ fontWeight: 400 }}>
                              {r2f ? ` (n=${r2f.n}, \u03BA=${r2f.kappa != null ? r2f.kappa.toFixed(2) : "N/A"})` : ""}
                            </span>
                          </td>
                          <td style={{
                            textAlign: "center",
                            borderLeft: "2px solid var(--warning)",
                            background: "rgba(234,179,8,0.05)",
                            fontWeight: 600,
                          }}>
                            {hf ? `${hf.agree_pct.toFixed(1)}%` : "\u2014"}
                            <span className="text-sm text-muted" style={{ fontWeight: 400 }}>
                              {hf ? ` (n=${hf.n}, \u03BA=${hf.kappa != null ? hf.kappa.toFixed(2) : "N/A"})` : ""}
                            </span>
                          </td>
                          <td style={{
                            textAlign: "center",
                            borderLeft: "2px solid var(--border)",
                            fontWeight: 700,
                            color: exceeds ? "var(--success)" : "var(--error)",
                          }}>
                            {exceeds ? "EXCEEDS" : "BELOW"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Individual detail tables */}
              <ConcordanceSummaryTable
                fields={concordance.agent_vs_r1.fields}
                label={`Agent vs R1 — Overall ${concordance.agent_vs_r1.overall_agree_pct.toFixed(1)}% agreement`}
              />
              <ConcordanceSummaryTable
                fields={concordance.agent_vs_r2.fields}
                label={`Agent vs R2 — Overall ${concordance.agent_vs_r2.overall_agree_pct.toFixed(1)}% agreement`}
              />
              <ConcordanceSummaryTable
                fields={concordance.r1_vs_r2.fields}
                label={`R1 vs R2 (Human Baseline) — Overall ${concordance.r1_vs_r2.overall_agree_pct.toFixed(1)}% agreement`}
              />

              {/* Per-field expandable details */}
              <h3 style={{ margin: "1.5rem 0 0.75rem" }}>Field Details (Agent vs R1)</h3>
              {concordance.agent_vs_r1.fields.map((f) => (
                <FieldDetail key={f.field_name} field={f} labelA="Agent" labelB="R1" />
              ))}

              <h3 style={{ margin: "1.5rem 0 0.75rem" }}>Field Details (Agent vs R2)</h3>
              {concordance.agent_vs_r2.fields.map((f) => (
                <FieldDetail key={f.field_name} field={f} labelA="Agent" labelB="R2" />
              ))}
            </>
          )}

          {/* Non-default state: show separate tables per replicate */}
          {!isDefaultState && !annotatorLoading && hasAnySelection && (
            <>
              {/* R1 concordance section */}
              {r1Concordance && r1Concordance.fields.length > 0 && (
                <>
                  <ConcordanceSummaryTable
                    fields={r1Concordance.fields}
                    label={`${r1Concordance.comparison_label} — Overall ${r1Concordance.overall_agree_pct.toFixed(1)}% agreement (n=${r1Concordance.n_overlapping})`}
                  />
                  {r1Concordance.fields.map((f) => (
                    <FieldDetail key={`r1-${f.field_name}`} field={f} labelA="Agent" labelB="R1" />
                  ))}
                </>
              )}

              {/* R2 concordance section */}
              {r2Concordance && r2Concordance.fields.length > 0 && (
                <>
                  <ConcordanceSummaryTable
                    fields={r2Concordance.fields}
                    label={`${r2Concordance.comparison_label} — Overall ${r2Concordance.overall_agree_pct.toFixed(1)}% agreement (n=${r2Concordance.n_overlapping})`}
                  />
                  {r2Concordance.fields.map((f) => (
                    <FieldDetail key={`r2-${f.field_name}`} field={f} labelA="Agent" labelB="R2" />
                  ))}
                </>
              )}
            </>
          )}

          {/* No selection state */}
          {!isDefaultState && !annotatorLoading && !hasAnySelection && (
            <div className="card text-muted">Select annotators to view concordance data.</div>
          )}
        </>
      )}
    </div>
  );
}

// ── Tab 2: Version Comparison ────────────────────────────────────────

function VersionCompareTab() {
  const [jobs, setJobs] = useState<Array<{job_id: string; timestamp: string; total_trials: number}>>([]);
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
      "Job A": f.kappa_a ?? 0,
      "Job B": f.kappa_b ?? 0,
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
              <option key={j.job_id} value={j.job_id}>
                {j.job_id} ({j.total_trials} trials{j.timestamp ? `, ${j.timestamp}` : ""})
              </option>
            ))}
          </select>
        </div>
        <div style={{ flex: 1, minWidth: "200px" }}>
          <label htmlFor="job-b-select">Job B</label>
          <select id="job-b-select" value={jobB} onChange={(e) => setJobB(e.target.value)}>
            <option value="">-- select job B --</option>
            {jobs.map((j) => (
              <option key={j.job_id} value={j.job_id}>
                {j.job_id} ({j.total_trials} trials{j.timestamp ? `, ${j.timestamp}` : ""})
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
            const regressed = result.fields.filter((f) => !f.improved && f.delta != null && f.delta < 0).length;
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
                        color: f.kappa_a != null ? kappaColor(f.kappa_a) : "var(--text-secondary)",
                        background: f.kappa_a != null ? kappaBg(f.kappa_a) : "transparent",
                        borderRadius: "4px",
                        fontWeight: 600,
                      }}
                    >
                      {f.kappa_a != null ? f.kappa_a.toFixed(3) : "N/A"}
                    </td>
                    <td
                      style={{
                        textAlign: "center",
                        color: f.kappa_b != null ? kappaColor(f.kappa_b) : "var(--text-secondary)",
                        background: f.kappa_b != null ? kappaBg(f.kappa_b) : "transparent",
                        borderRadius: "4px",
                        fontWeight: 600,
                      }}
                    >
                      {f.kappa_b != null ? f.kappa_b.toFixed(3) : "N/A"}
                    </td>
                    <td
                      style={{
                        textAlign: "center",
                        fontWeight: 600,
                        color: f.delta != null && f.delta > 0 ? "var(--success)" : f.delta != null && f.delta < 0 ? "var(--error)" : "var(--text-secondary)",
                      }}
                    >
                      {f.delta != null ? `${f.delta > 0 ? "+" : ""}${f.delta.toFixed(3)}` : "N/A"}
                    </td>
                    <td style={{ textAlign: "center", fontSize: "1.2rem" }}>
                      {f.improved ? (
                        <span style={{ color: "var(--success)" }} title="Improved">{"\u2191"}</span>
                      ) : f.delta != null && f.delta < 0 ? (
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

  // Multi-select annotator state
  const [annotators, setAnnotators] = useState<AnnotatorInfo[]>([]);
  const [selectedR1, setSelectedR1] = useState<Set<string>>(new Set());
  const [selectedR2, setSelectedR2] = useState<Set<string>>(new Set());
  const [filteredConcordance, setFilteredConcordance] = useState<JobConcordance | null>(null);
  const [annotatorLoading, setAnnotatorLoading] = useState(false);
  const [initDone, setInitDone] = useState(false);

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
    (async () => {
      try {
        const data = await getAnnotators();
        const list = Array.isArray(data.annotators) ? data.annotators : [];
        setAnnotators(list);
        // Default: All R1 selected (matches previous default of "All" which showed full R1 vs R2)
        const r1Names = new Set(list.filter((a) => a.replicate === "r1").map((a) => a.name));
        setSelectedR1(r1Names);
        setInitDone(true);
      } catch {
        console.error("Failed to load annotators");
        setInitDone(true);
      }
    })();
  }, []);

  // Load filtered concordance when selections change
  useEffect(() => {
    if (!initDone) return;

    const allR1Names = new Set(annotators.filter((a) => a.replicate === "r1").map((a) => a.name));
    const allR1Selected = allR1Names.size > 0 && [...allR1Names].every((n) => selectedR1.has(n));
    const noR2 = selectedR2.size === 0;

    // If all R1 selected and no R2 selected, that's the default (full R1 vs R2)
    if (allR1Selected && noR2) {
      setFilteredConcordance(null);
      return;
    }

    // If nothing selected, clear
    if (selectedR1.size === 0 && selectedR2.size === 0) {
      setFilteredConcordance(null);
      return;
    }

    let cancelled = false;
    setAnnotatorLoading(true);

    getHumanAnnotatorsConcordance(
      selectedR1.size > 0 ? [...selectedR1] : undefined,
      selectedR2.size > 0 ? [...selectedR2] : undefined,
    )
      .then((data) => {
        if (!cancelled) setFilteredConcordance(data);
      })
      .catch(() => {
        if (!cancelled) setFilteredConcordance(null);
      })
      .finally(() => {
        if (!cancelled) setAnnotatorLoading(false);
      });

    return () => { cancelled = true; };
  }, [selectedR1, selectedR2, initDone, annotators]);

  // Determine display state
  const allR1Names = new Set(annotators.filter((a) => a.replicate === "r1").map((a) => a.name));
  const isDefaultState = allR1Names.size > 0 && [...allR1Names].every((n) => selectedR1.has(n)) && selectedR2.size === 0;
  const activeConcordance = isDefaultState ? concordance : filteredConcordance;
  const hasAnySelection = selectedR1.size > 0 || selectedR2.size > 0;

  if (loading) return <div className="card text-muted">Loading human inter-rater data...</div>;
  if (error) return <div className="card" style={{ color: "var(--error)" }}>{error}</div>;
  if (!concordance) return <div className="card text-muted">No data available.</div>;

  return (
    <div>
      <div className="card mb-2" style={{ color: "var(--text-secondary)", fontSize: "0.9rem" }}>
        <p style={{ marginBottom: "0.5rem" }}>
          <strong>R1 vs R2 human inter-rater agreement.</strong> Only trials where BOTH annotators
          filled in a value are compared. The "Skipped" column shows how many trials had one or
          both annotators leave the field blank.
        </p>
        <p style={{ marginBottom: "0.5rem" }}>
          <strong>R1 annotators:</strong> Mercan (rows 1-309), Maya (310-617), Anat (617-822),
          Ali (823-926, 1417-1544), Emre (926-1186), Iris (1187-1417), Berke (1545-1846)
        </p>
        <p>
          <strong>R2 annotators:</strong> Emily (most rows), Anat (462-480), Ali (923-941), Iris (1384-1405)
        </p>
      </div>

      {/* Multi-select annotator selector */}
      {annotators.length > 0 && (
        <AnnotatorSelector
          annotators={annotators}
          selectedR1={selectedR1}
          selectedR2={selectedR2}
          onChangeR1={setSelectedR1}
          onChangeR2={setSelectedR2}
        />
      )}

      {annotatorLoading && <div className="card text-muted">Loading annotator concordance...</div>}

      {!annotatorLoading && hasAnySelection && activeConcordance && (
        <>
          <ConcordanceSummaryTable
            fields={activeConcordance.fields}
            label={`${activeConcordance.comparison_label} — Overall ${activeConcordance.overall_agree_pct.toFixed(1)}% agreement (n=${activeConcordance.n_overlapping})`}
          />

          {activeConcordance.fields.map((f) => (
            <FieldDetail key={f.field_name} field={f} labelA="R1" labelB="R2" />
          ))}
        </>
      )}

      {!annotatorLoading && !hasAnySelection && (
        <div className="card text-muted">Select annotators to view inter-rater concordance data.</div>
      )}
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
      label: h.job_id.slice(0, 8),
      n_trials: h.n_trials || 0,
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
        <ComposedChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
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
            yAxisId="left"
            domain={[-0.1, 1]}
            tick={{ fill: "var(--text-secondary)", fontSize: 12 }}
            label={{
              value: "Cohen's \u03BA",
              angle: -90,
              position: "insideLeft",
              style: { fill: "var(--text-secondary)", fontSize: 12 },
            }}
          />
          <YAxis
            yAxisId="right"
            orientation="right"
            tick={{ fill: "var(--text-secondary)", fontSize: 12 }}
            label={{
              value: "Trials",
              angle: 90,
              position: "insideRight",
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
          <Bar yAxisId="right" dataKey="n_trials" fill="rgba(255,255,255,0.1)" radius={[3, 3, 0, 0]} name="Trials" />
          {fieldNames.map((name) => (
            <Line
              key={name}
              yAxisId="left"
              type="monotone"
              dataKey={name}
              stroke={fieldColor(name)}
              strokeWidth={2}
              dot={{ r: 4, fill: fieldColor(name) }}
              activeDot={{ r: 6 }}
            />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Main page ────────────────────────────────────────────────────────

function MetricsExplainer() {
  const [open, setOpen] = useState(false);
  return (
    <div className="card mb-2">
      <button
        className="btn btn-secondary"
        onClick={() => setOpen(!open)}
        style={{ width: "100%", justifyContent: "space-between" }}
      >
        <span style={{ fontWeight: 500 }}>About these metrics</span>
        <span className="text-sm text-muted">{open ? "Collapse" : "Expand"}</span>
      </button>
      {open && (
        <div style={{ marginTop: "1rem", fontSize: "0.9rem", lineHeight: 1.6, color: "var(--text-secondary)" }}>
          <p style={{ marginBottom: "0.75rem" }}>
            <strong style={{ color: "var(--text-primary)" }}>Gwet's AC&#x2081;</strong> (primary metric): Measures agreement between two annotators, correcting for
            chance agreement. Unlike Cohen's &kappa;, AC&#x2081; handles the "prevalence paradox" &mdash; when one category
            dominates (e.g., 85% of trials are "Other"), &kappa; collapses to near-zero even with high agreement,
            while AC&#x2081; correctly reports the true agreement level.
          </p>
          <p style={{ marginBottom: "0.75rem", paddingLeft: "1rem", borderLeft: "3px solid var(--border)" }}>
            Interpretation: &lt;0.20 Poor | 0.21&ndash;0.40 Fair | 0.41&ndash;0.60 Moderate | 0.61&ndash;0.80 Substantial | 0.81&ndash;1.00 Almost Perfect
          </p>
          <p style={{ marginBottom: "0.75rem" }}>
            <strong style={{ color: "var(--text-primary)" }}>Cohen's &kappa;</strong> (secondary metric): The traditional inter-rater agreement metric. Provided for
            comparability with prior literature. Unreliable when one category is highly prevalent (classification,
            reason_for_failure in this dataset).
          </p>
          <p>
            <strong style={{ color: "var(--text-primary)" }}>Per-category F1</strong>: For each possible value in a field, F1 = 2&times;Precision&times;Recall/(Precision+Recall).
            Precision = "when the agent says X, how often is the human also X?"
            Recall = "when the human says X, how often does the agent also say X?"
            This reveals which specific categories the agent handles well vs poorly.
          </p>
        </div>
      )}
    </div>
  );
}

function DataCleaningRules() {
  const [open, setOpen] = useState(false);
  const ruleStyle: React.CSSProperties = { marginBottom: "0.4rem" };
  return (
    <div className="card mb-2">
      <button
        className="btn btn-secondary"
        onClick={() => setOpen(!open)}
        style={{ width: "100%", justifyContent: "space-between" }}
      >
        <span style={{ fontWeight: 500 }}>Data cleaning &amp; comparison rules</span>
        <span className="text-sm text-muted">{open ? "Collapse" : "Expand"}</span>
      </button>
      {open && (
        <div style={{ marginTop: "1rem", fontSize: "0.85rem", lineHeight: 1.6, color: "var(--text-secondary)" }}>
          <p style={{ marginBottom: "0.75rem" }}><strong style={{ color: "var(--text-primary)" }}>Blank handling (universal standard)</strong></p>
          <ul style={{ paddingLeft: "1.2rem", margin: 0 }}>
            <li style={ruleStyle}>An NCT is considered "annotated" only if at least 1 of the 5 annotation fields has a non-blank value. Rows assigned to an annotator but left completely blank are excluded from all counts and comparisons.</li>
            <li style={ruleStyle}>For <strong>classification, delivery_mode, outcome, peptide</strong> (blank_means_skip): a pair is skipped if <em>either</em> side is blank. The agent always fills all fields, so skips only occur when the human left a field empty.</li>
            <li style={ruleStyle}>For <strong>reason_for_failure</strong> (outcome-aware): blank reason + blank outcome on both sides = skipped (annotator didn't engage). Blank reason with a non-failure outcome = legitimate "no failure" (counts as agreement if both blank). Blank reason with a failure outcome = missing data (skipped).</li>
            <li style={ruleStyle}>Agent annotations always have all 5 fields filled — the agent never produces blank values.</li>
          </ul>

          <p style={{ marginBottom: "0.75rem", marginTop: "1rem" }}><strong style={{ color: "var(--text-primary)" }}>Value normalization</strong></p>
          <ul style={{ paddingLeft: "1.2rem", margin: 0 }}>
            <li style={ruleStyle}><strong>Classification:</strong> Case-normalized. "amp(infection)" → "AMP(infection)", "amp (other)" → "AMP(other)", etc.</li>
            <li style={ruleStyle}><strong>Delivery mode:</strong> Multi-value fields are split on comma, each part normalized independently, then sorted alphabetically and re-joined. Aliases: "intravenous"/"iv" → "IV", "subcutaneous"/"sc" → "Subcutaneous/Intradermal", etc.</li>
            <li style={ruleStyle}><strong>Outcome:</strong> "active" → "Active, not recruiting", "failed" / "completed" → "Failed - completed trial", etc.</li>
            <li style={ruleStyle}><strong>Reason for failure:</strong> Case-normalized. "business_reason" → "Business Reason", "toxic_unsafe" → "Toxic/Unsafe".</li>
            <li style={ruleStyle}><strong>Peptide:</strong> Boolean normalization. "true"/"yes"/"1"/True → "True", "false"/"no"/"0"/False → "False".</li>
          </ul>

          <p style={{ marginBottom: "0.75rem", marginTop: "1rem" }}><strong style={{ color: "var(--text-primary)" }}>Annotator identification</strong></p>
          <ul style={{ paddingLeft: "1.2rem", margin: 0 }}>
            <li style={ruleStyle}>R1 and R2 are independent annotation replicates from separate Excel sheets.</li>
            <li style={ruleStyle}>Individual annotators are identified by Excel row ranges (workload assignment). Counts reflect only rows where the annotator actually filled in at least one field.</li>
            <li style={ruleStyle}>Anat, Ali, and Iris appear in both R1 and R2 (different NCT ranges). Selecting them from the R1 row gives their R1 annotations; from the R2 row gives their R2 annotations. These are separate annotation sessions on different NCTs.</li>
            <li style={ruleStyle}>Multi-selecting annotators within the same replicate combines their NCTs into one concordance. Cross-replicate selections produce separate tables (cannot merge because the same NCT may have different values in R1 vs R2).</li>
          </ul>

          <p style={{ marginBottom: "0.75rem", marginTop: "1rem" }}><strong style={{ color: "var(--text-primary)" }}>Agent data source</strong></p>
          <ul style={{ paddingLeft: "1.2rem", margin: 0 }}>
            <li style={ruleStyle}>Agent values are the <strong>final verified values</strong> from the verification pipeline (post-consensus, post-reconciliation). If verification was skipped (deterministic annotation with high confidence), the primary annotator value is used.</li>
            <li style={ruleStyle}>Only completed annotation jobs with consolidated JSON output are available for concordance. Cancelled/partial jobs are not included.</li>
          </ul>
        </div>
      )}
    </div>
  );
}

export default function ConcordancePage() {
  const [activeTab, setActiveTab] = useState<TabKey>("agent-human");

  return (
    <div>
      <h2 style={{ marginBottom: "1rem" }}>Concordance Dashboard</h2>

      {/* Metrics explainer (collapsed by default) */}
      <MetricsExplainer />

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

      {/* Data cleaning rules (collapsed by default, below tab content) */}
      <div style={{ marginTop: "2rem" }}>
        <DataCleaningRules />
      </div>
    </div>
  );
}

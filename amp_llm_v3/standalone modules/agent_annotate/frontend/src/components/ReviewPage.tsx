import { useState, useEffect } from "react";
import { getReviewItems, getReviewStats, submitReview, getFieldValues } from "../api/client";
import type { ReviewItem, ReviewStats, ModelOpinion } from "../types";

interface JobGroup {
  job_id: string;
  items: ReviewItem[];
}

export default function ReviewPage() {
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [stats, setStats] = useState<ReviewStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedJob, setSelectedJob] = useState<string | null>(null);
  const [selected, setSelected] = useState<ReviewItem | null>(null);
  const [overrideValue, setOverrideValue] = useState("");
  const [note, setNote] = useState("");
  const [fieldValues, setFieldValues] = useState<Record<string, string[]>>({});
  const [modelMap, setModelMap] = useState<Record<string, { name: string; role: string }>>({});

  const loadItems = async () => {
    try {
      const [data, statsData, fv] = await Promise.all([
        getReviewItems(undefined, "pending"),
        getReviewStats(),
        getFieldValues(),
      ]);
      setItems(data.items || []);
      setStats(statsData);
      setFieldValues(fv.fields || {});
      setModelMap(fv.model_map || {});
    } catch (e) {
      console.error("Failed to load review items", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadItems();
  }, []);

  const handleDecision = async (item: ReviewItem, action: string) => {
    try {
      const body: { action: string; value?: string; note?: string } = { action };
      if (action === "overridden" && overrideValue) {
        body.value = overrideValue;
      }
      if (note) {
        body.note = note;
      }
      await submitReview(item.job_id, item.nct_id, item.field_name, body);
      setSelected(null);
      setOverrideValue("");
      setNote("");
      // If no more items in this job, go back to job list
      const remaining = items.filter(
        (i) => i.job_id === item.job_id && i !== item,
      );
      if (remaining.length === 0) {
        setSelectedJob(null);
      }
      loadItems();
    } catch (e) {
      console.error("Failed to submit review", e);
    }
  };

  // Group items by job
  const jobGroups: JobGroup[] = [];
  const jobMap = new Map<string, ReviewItem[]>();
  for (const item of items) {
    if (!jobMap.has(item.job_id)) jobMap.set(item.job_id, []);
    jobMap.get(item.job_id)!.push(item);
  }
  for (const [job_id, jobItems] of jobMap) {
    jobGroups.push({ job_id, items: jobItems });
  }

  const currentJobItems = selectedJob
    ? items.filter((i) => i.job_id === selectedJob)
    : [];

  const validValuesForField = selected ? fieldValues[selected.field_name] : null;

  const resolveModelName = (key: string): string => {
    const entry = modelMap[key];
    return entry ? entry.name : key;
  };

  if (loading) return <div className="card text-muted">Loading review queue...</div>;

  // --- Job list view ---
  if (!selectedJob) {
    return (
      <div>
        <div className="flex-between mb-2">
          <h2>Review Queue</h2>
          {stats && (
            <div className="text-sm text-muted">
              {stats.pending} pending / {stats.total} total ({stats.decided} decided, {stats.skipped} skipped)
            </div>
          )}
        </div>

        {jobGroups.length === 0 ? (
          <div className="card text-muted">No items pending review.</div>
        ) : (
          <div>
            {jobGroups.map((group) => (
              <div
                key={group.job_id}
                className="card"
                style={{ cursor: "pointer" }}
                onClick={() => {
                  setSelectedJob(group.job_id);
                  setSelected(null);
                  setOverrideValue("");
                  setNote("");
                }}
              >
                <div className="flex-between mb-1">
                  <strong>Job {group.job_id}</strong>
                  <span className="badge badge-running">
                    {group.items.length} pending
                  </span>
                </div>
                <div className="text-sm text-muted">
                  Fields: {[...new Set(group.items.map((i) => i.field_name))].join(", ")}
                </div>
                <div className="text-sm text-muted">
                  Trials: {[...new Set(group.items.map((i) => i.nct_id))].length} unique
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  // --- Job detail view: items for selected job ---
  return (
    <div>
      <div className="flex-between mb-2">
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <button
            className="btn btn-secondary"
            onClick={() => {
              setSelectedJob(null);
              setSelected(null);
            }}
            style={{ padding: "0.25rem 0.75rem" }}
          >
            &larr; Back
          </button>
          <h2 style={{ margin: 0 }}>Job {selectedJob}</h2>
          <span className="text-sm text-muted">
            {currentJobItems.length} items pending
          </span>
        </div>
        {stats && (
          <div className="text-sm text-muted">
            {stats.pending} pending / {stats.total} total
          </div>
        )}
      </div>

      {currentJobItems.length === 0 ? (
        <div className="card text-muted">All items in this job have been reviewed.</div>
      ) : (
        <div className="flex" style={{ gap: "1rem", alignItems: "flex-start" }}>
          {/* Item list */}
          <div style={{ flex: "0 0 340px" }}>
            {currentJobItems.map((item) => (
              <div
                key={`${item.job_id}-${item.nct_id}-${item.field_name}`}
                className="card"
                style={{
                  cursor: "pointer",
                  borderColor: selected === item ? "var(--accent)" : undefined,
                }}
                onClick={() => {
                  setSelected(item);
                  setOverrideValue("");
                  setNote("");
                }}
              >
                <div className="flex-between mb-1">
                  <strong>{item.nct_id}</strong>
                  <span className="badge badge-running">pending</span>
                </div>
                <div className="text-sm text-muted">{item.field_name}</div>
                <div className="text-sm">
                  Original: <strong>{item.original_value || "\u2014"}</strong>
                </div>
              </div>
            ))}
          </div>

          {/* Detail panel */}
          <div style={{ flex: 1 }}>
            {selected ? (
              <div className="card">
                <div className="card-title">
                  {selected.nct_id} &mdash; {selected.field_name}
                </div>

                <div className="text-sm mb-2">
                  <strong>Original value:</strong> {selected.original_value || "\u2014"}
                </div>

                {selected.suggested_values.length > 0 && (
                  <div className="text-sm mb-2">
                    <strong>Suggestions:</strong> {selected.suggested_values.join(", ")}
                  </div>
                )}

                {/* Model opinions */}
                {selected.opinions.length > 0 && (
                  <div className="mb-2">
                    <div className="text-sm" style={{ fontWeight: 600, marginBottom: "0.5rem" }}>
                      Verifier Opinions ({selected.opinions.filter((o) => o.agrees).length} of{" "}
                      {selected.opinions.length} verifiers agree with the primary annotator)
                    </div>
                    <div className="flex" style={{ gap: "0.75rem", flexWrap: "wrap" }}>
                      {selected.opinions.map((op: ModelOpinion, i: number) => (
                        <div
                          key={i}
                          style={{
                            flex: "1 1 200px",
                            background: "var(--bg-primary)",
                            border: `1px solid ${op.agrees ? "var(--success)" : "var(--error)"}`,
                            borderRadius: "var(--radius)",
                            padding: "0.75rem",
                          }}
                        >
                          <div className="text-sm" style={{ fontWeight: 600, marginBottom: "0.3rem" }}>
                            {op.model_name}
                            <span className="text-muted" style={{ fontWeight: 400 }}>
                              {" "}({resolveModelName(op.model_name)})
                            </span>
                          </div>
                          <div className="text-sm">
                            <span style={{ color: op.agrees ? "var(--success)" : "var(--error)" }}>
                              {op.agrees ? "Agrees with primary" : "Disagrees with primary"}
                            </span>
                          </div>
                          <div className="text-sm text-muted">
                            This verifier is {Math.round((op.confidence || 0) * 100)}% confident in
                            its own answer
                          </div>
                          {op.suggested_value && (
                            <div className="text-sm mt-1">
                              Value: <strong>{op.suggested_value}</strong>
                            </div>
                          )}
                          {op.reasoning && (
                            <div className="text-sm text-muted mt-1" style={{ fontStyle: "italic" }}>
                              {op.reasoning}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Override value: dropdown for validated fields, text input for others */}
                <div className="mb-1">
                  <label>Override value</label>
                  {validValuesForField ? (
                    <select
                      value={overrideValue}
                      onChange={(e) => setOverrideValue(e.target.value)}
                      style={{ width: "100%" }}
                    >
                      <option value="">Select a value...</option>
                      {validValuesForField.map((v) => (
                        <option key={v} value={v}>
                          {v}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type="text"
                      value={overrideValue}
                      onChange={(e) => setOverrideValue(e.target.value)}
                      placeholder="Enter corrected value..."
                    />
                  )}
                </div>

                <div className="mb-2">
                  <label>Note (optional)</label>
                  <input
                    type="text"
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    placeholder="Reviewer note..."
                  />
                </div>

                {/* Action buttons */}
                <div className="flex gap-1">
                  <button
                    className="btn btn-primary"
                    onClick={() => handleDecision(selected, "approved")}
                  >
                    Approve
                  </button>
                  <button
                    className="btn btn-secondary"
                    onClick={() => handleDecision(selected, "overridden")}
                    disabled={!overrideValue}
                  >
                    Override
                  </button>
                  <button
                    className="btn btn-secondary"
                    onClick={() => handleDecision(selected, "retry")}
                  >
                    Retry
                  </button>
                  <button
                    className="btn btn-secondary"
                    onClick={() => handleDecision(selected, "skipped")}
                  >
                    Skip
                  </button>
                </div>
              </div>
            ) : (
              <div className="card text-muted">
                Select an item from the list to review.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

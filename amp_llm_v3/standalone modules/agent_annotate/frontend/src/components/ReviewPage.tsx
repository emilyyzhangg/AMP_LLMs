import { useState, useEffect, useCallback } from "react";
import { getReviewItems, getReviewStats, submitReview, getFieldValues } from "../api/client";
import type { ReviewItem, ReviewStats, ModelOpinion } from "../types";

// --- Annotation guidelines definitions ---
const GUIDELINES: Record<string, Array<{ value: string; definition: string; group?: string }>> = {
  classification: [
    { value: "AMP(infection)", definition: "Direct antimicrobial mechanism targeting infection" },
    { value: "AMP(other)", definition: "AMP used for non-infection purpose (e.g., wound healing, anti-cancer)" },
    { value: "Other", definition: "Not an antimicrobial peptide study" },
  ],
  peptide: [
    { value: "True", definition: "Active drug is a peptide therapeutic" },
    { value: "False", definition: "Not a peptide drug" },
  ],
  outcome: [
    { value: "Completed", definition: "Trial finished all phases as planned" },
    { value: "Active, not recruiting", definition: "Ongoing but no longer enrolling participants" },
    { value: "Recruiting", definition: "Currently enrolling participants" },
    { value: "Terminated", definition: "Stopped early (safety, futility, sponsor decision)" },
    { value: "Withdrawn", definition: "Cancelled before enrolling any participants" },
    { value: "Not yet recruiting", definition: "Registered but enrollment has not started" },
    { value: "Unknown status", definition: "Status not verified in over 2 years" },
  ],
  delivery_mode: [
    { value: "Intravenous", definition: "IV infusion or injection into vein", group: "Injection" },
    { value: "Intramuscular", definition: "Injection into muscle tissue", group: "Injection" },
    { value: "Subcutaneous", definition: "Injection under the skin", group: "Injection" },
    { value: "Intrathecal", definition: "Injection into spinal canal", group: "Injection" },
    { value: "Oral", definition: "Taken by mouth (tablet, capsule, solution)", group: "Oral" },
    { value: "Topical", definition: "Applied to skin or wound surface", group: "Topical" },
    { value: "Inhaled", definition: "Delivered via respiratory tract", group: "Other" },
    { value: "Intravitreal", definition: "Injection into the eye", group: "Other" },
    { value: "Intranasal", definition: "Delivered through the nose", group: "Other" },
    { value: "Other", definition: "Any route not listed above", group: "Other" },
  ],
  reason_for_failure: [
    { value: "Lack of efficacy", definition: "Drug did not meet primary efficacy endpoint" },
    { value: "Safety/toxicity", definition: "Unacceptable adverse events or toxicity" },
    { value: "Business/strategic", definition: "Sponsor decision unrelated to drug performance" },
    { value: "Enrollment issues", definition: "Failed to recruit sufficient participants" },
    { value: "Other", definition: "Reason not captured by above categories" },
    { value: "(empty)", definition: "No failure reason applicable (trial not terminated/failed)" },
  ],
};

interface JobGroup {
  job_id: string;
  items: ReviewItem[];
}

// --- Confirmation modal ---
function ConfirmModal({
  title,
  message,
  onConfirm,
  onCancel,
}: {
  title: string;
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-title">{title}</div>
        <div className="text-sm">{message}</div>
        <div className="modal-actions">
          <button className="btn btn-secondary" onClick={onCancel}>Cancel</button>
          <button className="btn btn-primary" onClick={onConfirm}>Confirm</button>
        </div>
      </div>
    </div>
  );
}

// --- Guidelines sidebar ---
function GuidelinesSidebar({
  open,
  onClose,
  activeField,
}: {
  open: boolean;
  onClose: () => void;
  activeField?: string;
}) {
  if (!open) return null;

  const fieldOrder = ["classification", "peptide", "outcome", "delivery_mode", "reason_for_failure"];

  return (
    <div className="guidelines-sidebar">
      <div className="flex-between mb-2">
        <strong>Annotation Guidelines</strong>
        <button className="btn btn-secondary" onClick={onClose} style={{ padding: "0.2rem 0.6rem" }}>
          Close
        </button>
      </div>

      {fieldOrder.map((fieldName) => {
        const entries = GUIDELINES[fieldName];
        if (!entries) return null;
        const isActive = activeField === fieldName;

        // Group delivery_mode by category
        const groups: Record<string, typeof entries> = {};
        const hasGroups = entries.some((e) => e.group);

        if (hasGroups) {
          for (const entry of entries) {
            const g = entry.group || "Other";
            if (!groups[g]) groups[g] = [];
            groups[g].push(entry);
          }
        }

        return (
          <div
            key={fieldName}
            className="guidelines-field"
            style={isActive ? { background: "rgba(124, 140, 255, 0.08)", padding: "0.75rem", borderRadius: "var(--radius)", margin: "-0.75rem -0.75rem 0.75rem", } : undefined}
          >
            <div className="guidelines-field-title">
              {fieldName.replace(/_/g, " ")}
              {isActive && <span style={{ fontSize: "0.7rem", marginLeft: "0.5rem", opacity: 0.7 }}>(active)</span>}
            </div>

            {hasGroups ? (
              Object.entries(groups).map(([groupName, groupEntries]) => (
                <div key={groupName} style={{ marginBottom: "0.4rem" }}>
                  <div className="text-sm text-muted" style={{ fontWeight: 600, fontSize: "0.75rem", marginBottom: "0.2rem" }}>
                    {groupName}
                  </div>
                  {groupEntries.map((entry) => (
                    <div key={entry.value} className="guidelines-value">
                      <span className="guidelines-value-name">{entry.value}:</span>
                      <span className="guidelines-value-def">{entry.definition}</span>
                    </div>
                  ))}
                </div>
              ))
            ) : (
              entries.map((entry) => (
                <div key={entry.value} className="guidelines-value">
                  <span className="guidelines-value-name">{entry.value}:</span>
                  <span className="guidelines-value-def">{entry.definition}</span>
                </div>
              ))
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function ReviewPage() {
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [stats, setStats] = useState<ReviewStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedJob, setSelectedJob] = useState<string | null>(null);
  const [selected, setSelected] = useState<ReviewItem | null>(null);
  const [selectedIndex, setSelectedIndex] = useState<number>(-1);
  const [overrideValue, setOverrideValue] = useState("");
  const [note, setNote] = useState("");
  const [fieldValues, setFieldValues] = useState<Record<string, string[]>>({});
  const [modelMap, setModelMap] = useState<Record<string, { name: string; role: string }>>({});
  const [guidelinesOpen, setGuidelinesOpen] = useState(false);
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [batchFieldFilter, setBatchFieldFilter] = useState<string>("all");

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
      setSelectedIndex(-1);
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

  // Batch approve: items where at least 2 of 3 verifiers agree
  const handleBatchApprove = async () => {
    const jobItems = items.filter((i) => i.job_id === selectedJob);
    const eligible = jobItems.filter((item) => {
      const agreeCount = item.opinions.filter((o) => o.agrees).length;
      return agreeCount >= 2;
    });

    for (const item of eligible) {
      try {
        await submitReview(item.job_id, item.nct_id, item.field_name, { action: "approved" });
      } catch (e) {
        console.error(`Failed to approve ${item.nct_id}/${item.field_name}`, e);
      }
    }

    setShowConfirmModal(false);
    setSelected(null);
    setSelectedIndex(-1);
    loadItems();
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
    ? items.filter((i) => {
        if (i.job_id !== selectedJob) return false;
        if (batchFieldFilter !== "all" && i.field_name !== batchFieldFilter) return false;
        return true;
      })
    : [];

  const validValuesForField = selected ? fieldValues[selected.field_name] : null;

  const resolveModelName = (key: string): string => {
    const entry = modelMap[key];
    return entry ? entry.name : key;
  };

  // Count eligible for batch approve
  const batchEligibleCount = currentJobItems.filter((item) => {
    const agreeCount = item.opinions.filter((o) => o.agrees).length;
    return agreeCount >= 2;
  }).length;

  // Get unique field names for filter
  const uniqueFields = [...new Set(
    items.filter((i) => i.job_id === selectedJob).map((i) => i.field_name)
  )];

  // Navigate to item by index
  const selectByIndex = useCallback((idx: number) => {
    if (idx >= 0 && idx < currentJobItems.length) {
      setSelected(currentJobItems[idx]);
      setSelectedIndex(idx);
      setOverrideValue("");
      setNote("");
    }
  }, [currentJobItems]);

  // Keyboard shortcuts
  useEffect(() => {
    if (!selectedJob || !selected) return;

    const handler = (e: KeyboardEvent) => {
      // Do not capture if user is typing in an input
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

      switch (e.key) {
        case "a":
          e.preventDefault();
          handleDecision(selected, "approved");
          break;
        case "s":
          e.preventDefault();
          handleDecision(selected, "skipped");
          break;
        case "r":
          e.preventDefault();
          handleDecision(selected, "retry");
          break;
        case "n":
        case "ArrowDown":
          e.preventDefault();
          selectByIndex(selectedIndex + 1);
          break;
        case "p":
        case "ArrowUp":
          e.preventDefault();
          selectByIndex(selectedIndex - 1);
          break;
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [selected, selectedJob, selectedIndex, selectByIndex]);

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
                  setSelectedIndex(-1);
                  setOverrideValue("");
                  setNote("");
                  setBatchFieldFilter("all");
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
              setSelectedIndex(-1);
              setGuidelinesOpen(false);
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
        <div className="flex gap-1">
          <button
            className="btn btn-secondary"
            onClick={() => setGuidelinesOpen(!guidelinesOpen)}
          >
            {guidelinesOpen ? "Hide Guidelines" : "Guidelines"}
          </button>
          {stats && (
            <div className="text-sm text-muted" style={{ display: "flex", alignItems: "center" }}>
              {stats.pending} pending / {stats.total} total
            </div>
          )}
        </div>
      </div>

      {/* Batch toolbar */}
      <div className="batch-toolbar">
        <button
          className="btn btn-primary"
          onClick={() => setShowConfirmModal(true)}
          disabled={batchEligibleCount === 0}
          title={`${batchEligibleCount} items where 2+ verifiers agree`}
        >
          Approve all ({"\u2265"}2/3 agree) &mdash; {batchEligibleCount}
        </button>
        <label style={{ marginBottom: 0, fontSize: "0.85rem" }}>Filter by field:</label>
        <select
          value={batchFieldFilter}
          onChange={(e) => setBatchFieldFilter(e.target.value)}
          style={{ width: "auto", minWidth: "150px" }}
        >
          <option value="all">All fields</option>
          {uniqueFields.map((f) => (
            <option key={f} value={f}>{f}</option>
          ))}
        </select>
      </div>

      {/* Confirmation modal */}
      {showConfirmModal && (
        <ConfirmModal
          title="Batch Approve"
          message={`This will approve ${batchEligibleCount} items where at least 2 of 3 verifiers agree with the primary annotator. Continue?`}
          onConfirm={handleBatchApprove}
          onCancel={() => setShowConfirmModal(false)}
        />
      )}

      {/* Guidelines sidebar */}
      <GuidelinesSidebar
        open={guidelinesOpen}
        onClose={() => setGuidelinesOpen(false)}
        activeField={selected?.field_name}
      />

      {currentJobItems.length === 0 ? (
        <div className="card text-muted">All items in this job have been reviewed.</div>
      ) : (
        <div className="flex" style={{ gap: "1rem", alignItems: "flex-start" }}>
          {/* Item list */}
          <div style={{ flex: "0 0 340px" }}>
            {currentJobItems.map((item, idx) => (
              <div
                key={`${item.job_id}-${item.nct_id}-${item.field_name}`}
                className="card"
                style={{
                  cursor: "pointer",
                  borderColor: selected === item ? "var(--accent)" : undefined,
                }}
                onClick={() => {
                  setSelected(item);
                  setSelectedIndex(idx);
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

                {/* Phase 4.1: Primary Annotator section */}
                <div className="primary-annotator-section mb-2">
                  <div className="text-sm" style={{ fontWeight: 600, marginBottom: "0.5rem", color: "var(--accent)" }}>
                    Primary Annotator
                  </div>
                  {selected.primary_model && (
                    <div className="text-sm mb-1">
                      <strong>Model:</strong> {selected.primary_model}
                      {modelMap[selected.primary_model] && (
                        <span className="text-muted"> ({modelMap[selected.primary_model].name})</span>
                      )}
                    </div>
                  )}
                  {selected.primary_confidence !== undefined && selected.primary_confidence !== null && (
                    <div className="text-sm mb-1">
                      <strong>Confidence:</strong>{" "}
                      <span style={{
                        color: selected.primary_confidence >= 0.8
                          ? "var(--success)"
                          : selected.primary_confidence >= 0.4
                            ? "var(--warning)"
                            : "var(--error)",
                        fontWeight: 600,
                      }}>
                        {Math.round(selected.primary_confidence * 100)}%
                      </span>
                    </div>
                  )}
                  {selected.primary_reasoning ? (
                    <div className="text-sm text-muted" style={{ whiteSpace: "pre-wrap", fontStyle: "italic", marginTop: "0.5rem" }}>
                      {selected.primary_reasoning}
                    </div>
                  ) : (
                    <div className="text-sm text-muted" style={{ fontStyle: "italic" }}>
                      No reasoning data available from the primary annotator.
                    </div>
                  )}
                </div>

                {/* Model opinions (verifiers) */}
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

                {/* Action buttons with keyboard shortcut hints */}
                <div className="flex gap-1">
                  <button
                    className="btn btn-primary"
                    onClick={() => handleDecision(selected, "approved")}
                  >
                    Approve<span className="shortcut-hint">(a)</span>
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
                    Retry<span className="shortcut-hint">(r)</span>
                  </button>
                  <button
                    className="btn btn-secondary"
                    onClick={() => handleDecision(selected, "skipped")}
                  >
                    Skip<span className="shortcut-hint">(s)</span>
                  </button>
                </div>

                <div className="text-sm text-muted mt-2" style={{ fontStyle: "italic" }}>
                  Keyboard: a=approve, s=skip, r=retry, n/Down=next, p/Up=previous
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

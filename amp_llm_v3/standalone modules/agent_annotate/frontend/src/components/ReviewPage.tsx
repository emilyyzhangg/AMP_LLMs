import { useState, useEffect } from "react";
import { getReviewItems, getReviewStats, submitReview } from "../api/client";
import type { ReviewItem, ReviewStats, ModelOpinion } from "../types";

export default function ReviewPage() {
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [stats, setStats] = useState<ReviewStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<ReviewItem | null>(null);
  const [overrideValue, setOverrideValue] = useState("");
  const [note, setNote] = useState("");

  const loadItems = async () => {
    try {
      const [data, statsData] = await Promise.all([
        getReviewItems(undefined, "pending"),
        getReviewStats(),
      ]);
      setItems(data.items || []);
      setStats(statsData);
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
      loadItems();
    } catch (e) {
      console.error("Failed to submit review", e);
    }
  };

  if (loading) return <div className="card text-muted">Loading review queue...</div>;

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

      {items.length === 0 ? (
        <div className="card text-muted">No items pending review.</div>
      ) : (
        <div className="flex" style={{ gap: "1rem", alignItems: "flex-start" }}>
          {/* Item list */}
          <div style={{ flex: "0 0 340px" }}>
            {items.map((item, i) => (
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

                {/* Model opinions side by side */}
                {selected.opinions.length > 0 && (
                  <div className="mb-2">
                    <div className="text-sm" style={{ fontWeight: 600, marginBottom: "0.5rem" }}>
                      Model Opinions
                    </div>
                    <div className="flex" style={{ gap: "0.75rem", flexWrap: "wrap" }}>
                      {selected.opinions.map((op: ModelOpinion, i: number) => (
                        <div
                          key={i}
                          style={{
                            flex: "1 1 200px",
                            background: "var(--bg-primary)",
                            border: "1px solid var(--border)",
                            borderRadius: "var(--radius)",
                            padding: "0.75rem",
                          }}
                        >
                          <div className="text-sm" style={{ fontWeight: 600, marginBottom: "0.3rem" }}>
                            {op.model_name}
                          </div>
                          <div className="text-sm">
                            <span style={{ color: op.agrees ? "var(--success)" : "var(--error)" }}>
                              {op.agrees ? "Agrees" : "Disagrees"}
                            </span>
                            {" \u2014 "}
                            confidence: {Math.round((op.confidence || 0) * 100)}%
                          </div>
                          {op.suggested_value && (
                            <div className="text-sm text-muted mt-1">
                              Suggested: {op.suggested_value}
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

                {/* Override value input */}
                <div className="mb-1">
                  <label>Override value (for override action)</label>
                  <input
                    type="text"
                    value={overrideValue}
                    onChange={(e) => setOverrideValue(e.target.value)}
                    placeholder="Enter corrected value..."
                  />
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

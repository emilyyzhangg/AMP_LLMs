import { useState, useEffect } from "react";
import { getReviewItems, submitReview } from "../api/client";

export default function ReviewPage() {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const loadItems = async () => {
    try {
      const data = await getReviewItems();
      setItems(data.items || []);
    } catch (e) {
      console.error("Failed to load review items", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadItems();
  }, []);

  const handleDecision = async (item: any, action: string) => {
    try {
      await submitReview(item.job_id, item.nct_id, item.field_name, { action });
      loadItems();
    } catch (e) {
      console.error("Failed to submit review", e);
    }
  };

  if (loading) return <div className="card text-muted">Loading review queue...</div>;

  return (
    <div>
      <h2 style={{ marginBottom: "1rem" }}>Review Queue</h2>
      {items.length === 0 ? (
        <div className="card text-muted">No items pending review.</div>
      ) : (
        items.map((item, i) => (
          <div key={i} className="card">
            <div className="flex-between mb-1">
              <strong>{item.nct_id} - {item.field_name}</strong>
              <span className={`badge badge-${item.status === "pending" ? "running" : "completed"}`}>
                {item.status}
              </span>
            </div>
            <div className="text-sm mb-1">
              Original: <strong>{item.original_value}</strong>
            </div>
            {item.suggested_values?.length > 0 && (
              <div className="text-sm text-muted mb-1">
                Suggestions: {item.suggested_values.join(", ")}
              </div>
            )}
            {item.status === "pending" && (
              <div className="flex gap-1 mt-1">
                <button className="btn btn-primary" onClick={() => handleDecision(item, "approved")}>
                  Approve
                </button>
                <button className="btn btn-secondary" onClick={() => handleDecision(item, "skipped")}>
                  Skip
                </button>
              </div>
            )}
          </div>
        ))
      )}
    </div>
  );
}

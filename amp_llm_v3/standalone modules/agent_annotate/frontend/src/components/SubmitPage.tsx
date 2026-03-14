import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { createJob } from "../api/client";

export default function SubmitPage() {
  const [input, setInput] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const navigate = useNavigate();

  const handleSubmit = async () => {
    setError("");
    const ids = input
      .split(/[\n,]+/)
      .map((s) => s.trim())
      .filter((s) => /^NCT\d+$/i.test(s));

    if (ids.length === 0) {
      setError("Enter at least one valid NCT ID (e.g. NCT12345678).");
      return;
    }

    setSubmitting(true);
    try {
      const result = await createJob(ids);
      navigate(`/pipeline/${result.job_id}`);
    } catch (e: any) {
      setError(e.message || "Failed to create job");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div>
      <h2 style={{ marginBottom: "1rem" }}>Submit Annotation Job</h2>
      <div className="card">
        <label>NCT IDs (one per line, or comma-separated)</label>
        <textarea
          rows={8}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={"NCT12345678\nNCT87654321\nNCT11223344"}
          style={{ marginBottom: "1rem" }}
        />
        {error && <div style={{ color: "var(--error)", marginBottom: "0.5rem", fontSize: "0.9rem" }}>{error}</div>}
        <button className="btn btn-primary" onClick={handleSubmit} disabled={submitting}>
          {submitting ? "Submitting..." : "Start Annotation Pipeline"}
        </button>
      </div>
    </div>
  );
}

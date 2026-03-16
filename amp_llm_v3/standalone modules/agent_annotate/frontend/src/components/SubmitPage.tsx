import { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { createJob } from "../api/client";

const NCT_PATTERN = /^NCT\d+$/i;

interface ParsedIds {
  valid: string[];
  invalid: string[];
}

function parseNctIds(text: string): ParsedIds {
  const raw = text
    .split(/[\n,\r]+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
  const valid: string[] = [];
  const invalid: string[] = [];
  for (const s of raw) {
    if (NCT_PATTERN.test(s)) {
      valid.push(s.toUpperCase());
    } else {
      invalid.push(s);
    }
  }
  // Deduplicate valid
  return { valid: [...new Set(valid)], invalid };
}

function parseFileContent(content: string, fileName: string): ParsedIds {
  const lower = fileName.toLowerCase();

  if (lower.endsWith(".csv")) {
    // CSV: look for a column containing NCT IDs
    const lines = content.split(/\r?\n/).filter((l) => l.trim());
    if (lines.length === 0) return { valid: [], invalid: [] };

    // Try to find NCT ID column from header
    const header = lines[0].split(",").map((h) => h.trim().toLowerCase().replace(/['"]/g, ""));
    let nctColIndex = header.findIndex((h) =>
      h === "nct_id" || h === "nctid" || h === "nct id" || h === "trial_id" || h === "id"
    );

    // If no header match, check first column for NCT pattern
    if (nctColIndex === -1) {
      const firstDataLine = lines.length > 1 ? lines[1] : lines[0];
      const cells = firstDataLine.split(",").map((c) => c.trim().replace(/['"]/g, ""));
      nctColIndex = cells.findIndex((c) => NCT_PATTERN.test(c));
      if (nctColIndex === -1) nctColIndex = 0; // fallback to first column
    }

    const valid: string[] = [];
    const invalid: string[] = [];
    // Skip header row if it looks like a header
    const startIdx = NCT_PATTERN.test(lines[0].split(",")[nctColIndex]?.trim().replace(/['"]/g, "")) ? 0 : 1;

    for (let i = startIdx; i < lines.length; i++) {
      const cells = lines[i].split(",").map((c) => c.trim().replace(/['"]/g, ""));
      const val = cells[nctColIndex];
      if (val && NCT_PATTERN.test(val)) {
        valid.push(val.toUpperCase());
      } else if (val) {
        invalid.push(val);
      }
    }
    return { valid: [...new Set(valid)], invalid };
  }

  // Plain text: one ID per line or comma-separated
  return parseNctIds(content);
}

export default function SubmitPage() {
  const [input, setInput] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [filePreview, setFilePreview] = useState<ParsedIds | null>(null);
  const [fileName, setFileName] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setFileName(file.name);
    const reader = new FileReader();
    reader.onload = (evt) => {
      const content = evt.target?.result as string;
      const parsed = parseFileContent(content, file.name);
      setFilePreview(parsed);

      // Also populate the textarea with valid IDs
      if (parsed.valid.length > 0) {
        setInput(parsed.valid.join("\n"));
      }
    };
    reader.readAsText(file);

    // Reset file input so the same file can be selected again
    e.target.value = "";
  };

  const handleSubmit = async () => {
    setError("");
    const ids = input
      .split(/[\n,]+/)
      .map((s) => s.trim())
      .filter((s) => NCT_PATTERN.test(s))
      .map((s) => s.toUpperCase());

    // Deduplicate
    const uniqueIds = [...new Set(ids)];

    if (uniqueIds.length === 0) {
      setError("Enter at least one valid NCT ID (e.g. NCT12345678).");
      return;
    }

    setSubmitting(true);
    try {
      const result = await createJob(uniqueIds);
      navigate(`/pipeline/${result.job_id}`);
    } catch (e: any) {
      setError(e.message || "Failed to create job");
    } finally {
      setSubmitting(false);
    }
  };

  const clearFile = () => {
    setFilePreview(null);
    setFileName("");
  };

  // Live parse of textarea for preview count
  const textParsed = input.trim() ? parseNctIds(input) : null;

  return (
    <div>
      <h2 style={{ marginBottom: "1rem" }}>Submit Annotation Job</h2>
      <div className="card">
        {/* File upload area */}
        <div
          className="file-upload-area"
          onClick={() => fileInputRef.current?.click()}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".txt,.csv"
            onChange={handleFileUpload}
          />
          <div style={{ fontSize: "1.5rem", marginBottom: "0.5rem", color: "var(--text-secondary)" }}>
            +
          </div>
          <div className="text-sm text-muted">
            Click to upload a <strong>.txt</strong> or <strong>.csv</strong> file with NCT IDs
          </div>
          <div className="text-sm text-muted" style={{ marginTop: "0.25rem", fontSize: "0.78rem" }}>
            Text files: one ID per line or comma-separated. CSV: auto-detects NCT ID column.
          </div>
        </div>

        {/* File preview */}
        {filePreview && (
          <div className="file-preview">
            <div className="flex-between mb-1">
              <strong className="text-sm">File: {fileName}</strong>
              <button className="btn btn-secondary" onClick={clearFile} style={{ padding: "0.15rem 0.5rem", fontSize: "0.78rem" }}>
                Clear
              </button>
            </div>
            <div className="text-sm mb-1">
              Found <strong style={{ color: "var(--success)" }}>{filePreview.valid.length} valid</strong> ID{filePreview.valid.length !== 1 ? "s" : ""}
              {filePreview.invalid.length > 0 && (
                <>, <strong style={{ color: "var(--error)" }}>{filePreview.invalid.length} invalid</strong></>
              )}
            </div>
            {filePreview.invalid.length > 0 && (
              <div style={{ marginTop: "0.5rem" }}>
                <div className="text-sm text-muted" style={{ marginBottom: "0.3rem" }}>Invalid entries:</div>
                <div className="flex flex-wrap gap-1">
                  {filePreview.invalid.map((inv, i) => (
                    <span key={i} className="file-preview-invalid">{inv}</span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        <label>NCT IDs (one per line, or comma-separated)</label>
        <textarea
          rows={8}
          value={input}
          onChange={(e) => {
            setInput(e.target.value);
            // Clear file preview when user manually edits
            if (filePreview) setFilePreview(null);
          }}
          placeholder={"NCT12345678\nNCT87654321\nNCT11223344"}
          style={{ marginBottom: "0.5rem" }}
        />

        {/* Live parse preview from textarea */}
        {textParsed && (
          <div className="text-sm mb-1" style={{ color: "var(--text-secondary)" }}>
            <span style={{ color: "var(--success)" }}>{textParsed.valid.length} valid</span>
            {textParsed.invalid.length > 0 && (
              <>, <span style={{ color: "var(--error)" }}>{textParsed.invalid.length} invalid</span></>
            )}
            {" "}ID{(textParsed.valid.length + textParsed.invalid.length) !== 1 ? "s" : ""} detected
          </div>
        )}

        {error && <div style={{ color: "var(--error)", marginBottom: "0.5rem", fontSize: "0.9rem" }}>{error}</div>}
        <button className="btn btn-primary" onClick={handleSubmit} disabled={submitting}>
          {submitting ? "Submitting..." : "Start Annotation Pipeline"}
        </button>
      </div>
    </div>
  );
}

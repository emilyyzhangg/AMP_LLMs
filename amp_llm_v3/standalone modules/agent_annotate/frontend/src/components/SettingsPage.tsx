import { useState, useEffect } from "react";
import { getSettings, updateSettings, reloadSettings, getAvailableModels } from "../api/client";

export default function SettingsPage() {
  const [settings, setSettings] = useState<any>(null);
  const [models, setModels] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const [cfg, mdl] = await Promise.all([getSettings(), getAvailableModels()]);
        setSettings(cfg);
        setModels(mdl.models || []);
      } catch (e) {
        console.error("Failed to load settings", e);
      }
    })();
  }, []);

  const handleReload = async () => {
    try {
      const result = await reloadSettings();
      setSettings(result.config);
      setMessage("Settings reloaded from disk.");
      setTimeout(() => setMessage(""), 3000);
    } catch (e) {
      setMessage("Failed to reload settings.");
    }
  };

  if (!settings) return <div className="card text-muted">Loading settings...</div>;

  return (
    <div>
      <div className="flex-between mb-2">
        <h2>Pipeline Settings</h2>
        <div className="flex gap-1">
          <button className="btn btn-secondary" onClick={handleReload}>
            Reload from Disk
          </button>
        </div>
      </div>

      {message && <div className="card text-sm" style={{ color: "var(--success)" }}>{message}</div>}

      <div className="card">
        <div className="card-title">Verification</div>
        <div className="text-sm">
          <div>Verifiers: {settings.verification?.num_verifiers}</div>
          <div>Consensus threshold: {settings.verification?.consensus_threshold}</div>
          <div>Require consensus: {settings.verification?.require_consensus ? "Yes" : "No"}</div>
        </div>
      </div>

      <div className="card">
        <div className="card-title">Models</div>
        {settings.verification?.models && Object.entries(settings.verification.models).map(([key, model]: [string, any]) => (
          <div key={key} className="text-sm mb-1">
            <strong>{key}</strong>: {model.name} ({model.role})
          </div>
        ))}
      </div>

      <div className="card">
        <div className="card-title">Available Ollama Models</div>
        {models.length > 0 ? (
          <div className="text-sm">{models.join(", ")}</div>
        ) : (
          <div className="text-sm text-muted">No models found (is Ollama running?)</div>
        )}
      </div>

      <div className="card">
        <div className="card-title">Orchestrator</div>
        <div className="text-sm">
          <div>Parallel research: {settings.orchestrator?.parallel_research ? "Yes" : "No"}</div>
          <div>Parallel annotation: {settings.orchestrator?.parallel_annotation ? "Yes" : "No"}</div>
          <div>Max retry rounds: {settings.orchestrator?.max_retry_rounds ?? "Unlimited"}</div>
        </div>
      </div>

      <div className="card">
        <div className="card-title">Evidence Thresholds</div>
        {settings.evidence_thresholds && Object.entries(settings.evidence_thresholds).map(([field, thresh]: [string, any]) => (
          <div key={field} className="text-sm mb-1">
            <strong>{field}</strong>: min {thresh.min_sources} sources, quality {">="} {thresh.min_quality_score}
          </div>
        ))}
      </div>
    </div>
  );
}

import { useState, useEffect } from "react";
import { getSettings, updateSettings, reloadSettings, getAvailableModels } from "../api/client";

interface ModelConfig {
  name: string;
  role: string;
}

interface EvidenceThreshold {
  min_sources: number;
  min_quality_score: number;
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<any>(null);
  const [models, setModels] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState<"success" | "error">("success");

  // Editable state for model roles
  const [modelOverrides, setModelOverrides] = useState<Record<string, string>>({});
  // Editable state for evidence thresholds
  const [thresholdOverrides, setThresholdOverrides] = useState<Record<string, EvidenceThreshold>>({});
  // Editable state for consensus threshold
  const [consensusThreshold, setConsensusThreshold] = useState<number>(0.67);

  useEffect(() => {
    (async () => {
      try {
        const [cfg, mdl] = await Promise.all([getSettings(), getAvailableModels()]);
        setSettings(cfg);
        setModels(mdl.models || []);

        // Initialize model overrides from current config
        const verificationModels = (cfg.verification as Record<string, unknown>)?.models as Record<string, ModelConfig> | undefined;
        if (verificationModels) {
          const overrides: Record<string, string> = {};
          for (const [key, model] of Object.entries(verificationModels)) {
            overrides[key] = model.name;
          }
          setModelOverrides(overrides);
        }

        // Initialize evidence threshold overrides
        const thresholds = cfg.evidence_thresholds as Record<string, EvidenceThreshold> | undefined;
        if (thresholds) {
          setThresholdOverrides({ ...thresholds });
        }

        // Initialize consensus threshold
        const ct = (cfg.verification as Record<string, unknown>)?.consensus_threshold;
        if (typeof ct === "number") {
          setConsensusThreshold(ct);
        }
      } catch (e) {
        console.error("Failed to load settings", e);
      }
    })();
  }, []);

  const showMessage = (msg: string, type: "success" | "error" = "success") => {
    setMessage(msg);
    setMessageType(type);
    setTimeout(() => setMessage(""), 4000);
  };

  const handleReload = async () => {
    try {
      const result = await reloadSettings();
      const cfg = result.config as Record<string, unknown>;
      setSettings(cfg);

      // Re-initialize editable state
      const verificationModels = (cfg.verification as Record<string, unknown>)?.models as Record<string, ModelConfig> | undefined;
      if (verificationModels) {
        const overrides: Record<string, string> = {};
        for (const [key, model] of Object.entries(verificationModels)) {
          overrides[key] = model.name;
        }
        setModelOverrides(overrides);
      }
      const thresholds = cfg.evidence_thresholds as Record<string, EvidenceThreshold> | undefined;
      if (thresholds) {
        setThresholdOverrides({ ...thresholds });
      }
      const ct = (cfg.verification as Record<string, unknown>)?.consensus_threshold;
      if (typeof ct === "number") {
        setConsensusThreshold(ct);
      }

      showMessage("Settings reloaded from disk.");
    } catch {
      showMessage("Failed to reload settings.", "error");
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      // Build the overrides payload
      const overrides: Record<string, unknown> = {};

      // Model overrides
      const verificationModels = (settings.verification as Record<string, unknown>)?.models as Record<string, ModelConfig> | undefined;
      if (verificationModels) {
        const modelChanges: Record<string, { name: string }> = {};
        let hasChanges = false;
        for (const [key, currentModel] of Object.entries(verificationModels)) {
          if (modelOverrides[key] && modelOverrides[key] !== currentModel.name) {
            modelChanges[key] = { name: modelOverrides[key] };
            hasChanges = true;
          }
        }
        if (hasChanges) {
          overrides.verification = {
            ...(overrides.verification as Record<string, unknown> || {}),
            models: modelChanges,
          };
        }
      }

      // Consensus threshold
      const origCt = (settings.verification as Record<string, unknown>)?.consensus_threshold;
      if (consensusThreshold !== origCt) {
        overrides.verification = {
          ...(overrides.verification as Record<string, unknown> || {}),
          consensus_threshold: consensusThreshold,
        };
      }

      // Evidence thresholds
      const origThresholds = settings.evidence_thresholds as Record<string, EvidenceThreshold> | undefined;
      if (origThresholds) {
        const thresholdChanges: Record<string, EvidenceThreshold> = {};
        let hasThresholdChanges = false;
        for (const [field, current] of Object.entries(origThresholds)) {
          const override = thresholdOverrides[field];
          if (override && (override.min_sources !== current.min_sources || override.min_quality_score !== current.min_quality_score)) {
            thresholdChanges[field] = override;
            hasThresholdChanges = true;
          }
        }
        if (hasThresholdChanges) {
          overrides.evidence_thresholds = thresholdChanges;
        }
      }

      if (Object.keys(overrides).length === 0) {
        showMessage("No changes to save.");
        setSaving(false);
        return;
      }

      const result = await updateSettings(overrides);
      if (result.config) {
        setSettings(result.config);
      }
      showMessage("Settings saved successfully.");
    } catch (e) {
      showMessage("Failed to save settings.", "error");
    } finally {
      setSaving(false);
    }
  };

  const handleModelChange = (key: string, value: string) => {
    setModelOverrides((prev) => ({ ...prev, [key]: value }));
  };

  const handleThresholdChange = (field: string, prop: "min_sources" | "min_quality_score", value: number) => {
    setThresholdOverrides((prev) => ({
      ...prev,
      [field]: { ...prev[field], [prop]: value },
    }));
  };

  if (!settings) return <div className="card text-muted">Loading settings...</div>;

  const verificationModels = (settings.verification as Record<string, unknown>)?.models as Record<string, ModelConfig> | undefined;
  const roleLabels: Record<string, string> = {
    primary: "Primary Annotator",
    verifier_1: "Verifier 1",
    verifier_2: "Verifier 2",
    verifier_3: "Verifier 3",
    reconciler: "Reconciler",
  };

  return (
    <div>
      <div className="flex-between mb-2">
        <h2>Pipeline Settings</h2>
        <div className="flex gap-1">
          <button className="btn btn-secondary" onClick={handleReload}>
            Reload from Disk
          </button>
          <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
            {saving ? "Saving..." : "Save Changes"}
          </button>
        </div>
      </div>

      {message && (
        <div className="card text-sm" style={{ color: messageType === "success" ? "var(--success)" : "var(--error)" }}>
          {message}
        </div>
      )}

      {/* Model Configuration */}
      <div className="card">
        <div className="card-title">Model Configuration</div>
        {verificationModels && models.length > 0 ? (
          <div>
            {Object.entries(verificationModels).map(([key, model]) => (
              <div key={key} className="model-role-row">
                <label>{roleLabels[key] || key}</label>
                <select
                  value={modelOverrides[key] || model.name}
                  onChange={(e) => handleModelChange(key, e.target.value)}
                >
                  {/* Always include current value even if not in available list */}
                  {!models.includes(model.name) && (
                    <option value={model.name}>{model.name} (current)</option>
                  )}
                  {models.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
                <span className="text-sm text-muted" style={{ minWidth: "60px" }}>
                  {model.role}
                </span>
              </div>
            ))}
          </div>
        ) : verificationModels ? (
          <div>
            {Object.entries(verificationModels).map(([key, model]) => (
              <div key={key} className="text-sm mb-1">
                <strong>{roleLabels[key] || key}</strong>: {model.name} ({model.role})
              </div>
            ))}
            <div className="text-sm text-muted mt-2">
              No Ollama models available for selection. Is Ollama running?
            </div>
          </div>
        ) : (
          <div className="text-sm text-muted">No model configuration found.</div>
        )}
      </div>

      {/* Consensus Threshold */}
      <div className="card">
        <div className="card-title">Consensus Threshold</div>
        <div className="slider-container">
          <label>Threshold</label>
          <input
            type="range"
            min="0.33"
            max="1.0"
            step="0.01"
            value={consensusThreshold}
            onChange={(e) => setConsensusThreshold(parseFloat(e.target.value))}
          />
          <span className="slider-value">{consensusThreshold.toFixed(2)}</span>
        </div>
        <div className="text-sm text-muted">
          {consensusThreshold <= 0.34
            ? "Any 1 verifier agreement is sufficient"
            : consensusThreshold <= 0.5
              ? "Low threshold: fewer items sent to review"
              : consensusThreshold < 0.67
                ? "Moderate threshold"
                : consensusThreshold < 1.0
                  ? "Majority (2/3) agreement required"
                  : "Unanimous agreement required"}
        </div>
      </div>

      {/* Evidence Thresholds */}
      <div className="card">
        <div className="card-title">Evidence Thresholds</div>
        {settings.evidence_thresholds ? (
          Object.entries(thresholdOverrides).map(([field, thresh]) => (
            <div key={field} style={{ marginBottom: "1.25rem", paddingBottom: "1rem", borderBottom: "1px solid var(--border)" }}>
              <div className="text-sm" style={{ fontWeight: 600, marginBottom: "0.5rem" }}>
                {field.replace(/_/g, " ")}
              </div>
              <div className="slider-container">
                <label>Min Sources</label>
                <input
                  type="range"
                  min="1"
                  max="10"
                  step="1"
                  value={thresh.min_sources}
                  onChange={(e) => handleThresholdChange(field, "min_sources", parseInt(e.target.value))}
                />
                <span className="slider-value">{thresh.min_sources}</span>
              </div>
              <div className="slider-container">
                <label>Min Quality</label>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={thresh.min_quality_score}
                  onChange={(e) => handleThresholdChange(field, "min_quality_score", parseFloat(e.target.value))}
                />
                <span className="slider-value">{thresh.min_quality_score.toFixed(2)}</span>
              </div>
            </div>
          ))
        ) : (
          <div className="text-sm text-muted">No evidence thresholds configured.</div>
        )}
      </div>

      {/* Orchestrator settings (read-only display) */}
      <div className="card">
        <div className="card-title">Orchestrator</div>
        <div className="text-sm">
          <div>Parallel research: {settings.orchestrator?.parallel_research ? "Yes" : "No"}</div>
          <div>Parallel annotation: {settings.orchestrator?.parallel_annotation ? "Yes" : "No"}</div>
          <div>Max retry rounds: {settings.orchestrator?.max_retry_rounds ?? "Unlimited"}</div>
        </div>
      </div>

      {/* Verification settings (read-only display) */}
      <div className="card">
        <div className="card-title">Verification</div>
        <div className="text-sm">
          <div>Verifiers: {settings.verification?.num_verifiers}</div>
          <div>Consensus threshold: {consensusThreshold.toFixed(2)}</div>
          <div>Require consensus: {settings.verification?.require_consensus ? "Yes" : "No"}</div>
        </div>
      </div>

      {/* Available models (reference) */}
      <div className="card">
        <div className="card-title">Available Ollama Models</div>
        {models.length > 0 ? (
          <div className="text-sm">{models.join(", ")}</div>
        ) : (
          <div className="text-sm text-muted">No models found (is Ollama running?)</div>
        )}
      </div>
    </div>
  );
}

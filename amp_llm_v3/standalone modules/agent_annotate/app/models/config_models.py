"""
Pydantic models for the YAML configuration file.
"""

from typing import Dict, Optional
from pydantic import BaseModel


class ModelConfig(BaseModel):
    name: str
    role: str  # "annotator" | "verifier" | "reconciler"


class VerificationConfig(BaseModel):
    num_verifiers: int = 3
    require_consensus: bool = True
    consensus_threshold: float = 1.0
    models: Dict[str, ModelConfig] = {}


class ThresholdConfig(BaseModel):
    min_sources: int = 1
    min_quality: float = 0.3


class EvidenceThresholds(BaseModel):
    classification: ThresholdConfig = ThresholdConfig()
    delivery_mode: ThresholdConfig = ThresholdConfig()
    outcome: ThresholdConfig = ThresholdConfig()
    reason_for_failure: ThresholdConfig = ThresholdConfig(min_sources=1, min_quality=0.3)
    peptide: ThresholdConfig = ThresholdConfig()


class ResearchAgentConfig(BaseModel):
    sources: list[str] = []


class AnnotationAgentDef(BaseModel):
    primary_research: str
    secondary_research: str


class OrchestratorConfig(BaseModel):
    max_retry_rounds: Optional[int] = None
    parallel_research: bool = True
    parallel_annotation: bool = True
    hardware_profile: str = "mac_mini"  # "mac_mini" | "server"
    # The premium model used on server profile for high-accuracy tasks:
    # classification, outcome, and reconciliation. Toggle between models here.
    # Options: "kimi-k2-thinking" (default, 1T MoE 32B active, proven reasoning)
    #          "minimax-m2.7" (2.3T MoE 100B active, strong task adherence, slower)
    server_premium_model: str = "kimi-k2-thinking"
    # Server verifier overrides — stronger models for verification on server hardware.
    # List of 3 model names. If empty or not set, uses the default verifiers from
    # verification.models. Auto-pulled if not available locally.
    server_verifiers: list[str] = []
    # v11: Unified annotation model for Mac Mini — eliminates model switches
    # during annotation phase. All 5 fields use this model instead of the
    # primary annotator (llama3.1:8b) for some and qwen3:14b for others.
    annotation_model: str = "qwen3:14b"
    # v42 Phase 4: Run the atomic outcome pipeline alongside the legacy dossier
    # outcome agent. Stored under field_name="outcome_atomic" so the legacy
    # "outcome" remains authoritative. Default OFF to avoid unexpected LLM
    # spend on prod — flip to True for Phase 5 shadow-mode validation.
    outcome_atomic_shadow: bool = False
    # v42 Phase 4: Model used by the Tier 1b per-publication assessor. Empty
    # string falls back to the module default (gemma3:12b). Small focused
    # reading-comprehension calls are a natural fit for Gemma 3 12B.
    outcome_atomic_model: str = ""


class OllamaConfig(BaseModel):
    host: str = "localhost"
    port: int = 11434
    timeout: int = 600
    temperature: float = 0.10
    field_temperatures: Dict[str, float] = {
        "peptide": 0.0,
        "classification": 0.05,
        "outcome": 0.15,
        "delivery_mode": 0.10,
        "reason_for_failure": 0.10,
    }
    # v17: Per-model timeout overrides. Maps model name (or prefix) to timeout
    # in seconds. Models not listed use the global `timeout` value.
    # Smaller models get shorter timeouts since they either respond quickly
    # or are hung (bimodal). Larger models doing annotation need more time.
    model_timeouts: Dict[str, int] = {
        "llama3.1:8b": 300,     # 8B — v42: verifier_3 (adversarial)
        "gemma3:12b": 400,      # 12B — v42: verifier_1 (conservative) + atomic Tier 1b assessor
        "qwen3:8b": 300,        # 8B — v42: verifier_2 (evidence-strict), upgraded from qwen2.5:7b
        "qwen3:14b": 600,       # 14B — v40+: primary annotator + reconciler
    }


class AnnotationConfig(BaseModel):
    """Top-level config model matching default_config.yaml."""
    verification: VerificationConfig = VerificationConfig()
    evidence_thresholds: EvidenceThresholds = EvidenceThresholds()
    research_agents: Dict[str, ResearchAgentConfig] = {}
    annotation_agents: Dict[str, AnnotationAgentDef] = {}
    orchestrator: OrchestratorConfig = OrchestratorConfig()
    ollama: OllamaConfig = OllamaConfig()

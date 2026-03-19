"""
EDAM (Experience-Driven Annotation Memory) configuration constants.

Hardware-aware: call get_profile() to get the right constants for the
current hardware. Mac Mini uses conservative limits to avoid memory
pressure; server uses generous limits for long-term learning accumulation.

All tunable parameters for the self-learning system in one place.
Designed for the agent_annotate pipeline running on Ollama — no cloud APIs.
"""


def _get_hardware_profile() -> str:
    """Read the hardware profile from the annotation config.
    Returns 'mac_mini' or 'server'. Defaults to 'mac_mini' if unavailable."""
    try:
        from app.services.config_service import config_service
        config = config_service.get()
        return getattr(config.orchestrator, "hardware_profile", "mac_mini")
    except Exception:
        return "mac_mini"


# ---------------------------------------------------------------------------
# Hardware-aware profiles
# ---------------------------------------------------------------------------
_PROFILES = {
    "mac_mini": {
        # Conservative limits for 16-24GB unified memory
        "memory_budget_tokens": 2000,
        "max_experiences": 10000,       # ~6 months of data at 100 trials/week
        "max_corrections": 5000,
        "max_prompt_variants": 100,
        "max_embeddings": 15000,
        "self_review_max_items": 8,     # fewer self-reviews to save Ollama time
        "embedding_batch_pause": 0.5,   # seconds between embedding calls
    },
    "server": {
        # Generous limits for 240+ GB RAM
        "memory_budget_tokens": 3500,
        "max_experiences": 100000,      # 3+ years of data
        "max_corrections": 50000,
        "max_prompt_variants": 200,
        "max_embeddings": 150000,
        "self_review_max_items": 20,    # more self-reviews with faster hardware
        "embedding_batch_pause": 0.0,   # no pause needed
    },
}


def get_profile() -> dict:
    """Return the EDAM config profile for the current hardware."""
    hw = _get_hardware_profile()
    return _PROFILES.get(hw, _PROFILES["mac_mini"])


# ---------------------------------------------------------------------------
# Memory budget — max tokens of EDAM guidance injected per LLM call
# ---------------------------------------------------------------------------
CHARS_PER_TOKEN = 4  # heuristic for English text

# Budget allocation by category (must sum to 1.0)
BUDGET_ALLOCATION = {
    "corrections": 0.50,       # most valuable (learned mistakes)
    "stable_exemplars": 0.25,  # known-good few-shot examples
    "prompt_guidance": 0.15,   # prompt variant instructions
    "anomaly_warnings": 0.10,  # statistical anomaly flags
}

# ---------------------------------------------------------------------------
# Epoch-based decay — weights decrease as config changes accumulate
# ---------------------------------------------------------------------------
# Human corrections: slowest decay, highest floor (ground truth about evidence)
HUMAN_DECAY_RATE = 0.85
HUMAN_FLOOR = 0.3

# Self-review corrections: moderate decay (LLM self-critique, may have biases)
SELF_REVIEW_DECAY_RATE = 0.80
SELF_REVIEW_FLOOR = 0.1

# Raw experiences: fastest decay (model behavior under a specific config)
EXPERIENCE_DECAY_RATE = 0.75
EXPERIENCE_FLOOR = 0.05

# Definition-grounded corrections: very slow decay, high floor.
# These are corrections where the scientific definition (e.g., peptide = 2-100 AA
# active drug) directly determined the correct answer. They're as durable as
# human corrections because the definition doesn't change across configs.
DEFINITION_DECAY_RATE = 0.90
DEFINITION_FLOOR = 0.35

# ---------------------------------------------------------------------------
# Stability thresholds (Loop 1)
# ---------------------------------------------------------------------------
STABILITY_EXEMPLAR_MIN_RUNS = 3    # need 3+ runs to call something "stable"
STABILITY_EXEMPLAR_MIN_SCORE = 0.9  # 90%+ agreement across runs

# Evidence grading thresholds
EVIDENCE_GRADE_STRONG_MIN_CONFIDENCE = 0.85
EVIDENCE_GRADE_STRONG_MIN_CONSENSUS = True
EVIDENCE_GRADE_MEDIUM_MIN_CONFIDENCE = 0.6

# ---------------------------------------------------------------------------
# Anomaly detection — flag systematic bias
# ---------------------------------------------------------------------------
ANOMALY_THRESHOLD = 0.80  # flag if >80% of trials get same value for a field
ANOMALY_MIN_TRIALS = 10   # need at least this many trials to detect anomalies

# ---------------------------------------------------------------------------
# Prompt optimization (Loop 3)
# ---------------------------------------------------------------------------
MIN_TRIALS_FOR_PROMOTION = 20     # variant needs 20+ trials before promotion
MIN_IMPROVEMENT_FOR_PROMOTION = 0.05  # 5% accuracy improvement required
MIN_TRIALS_FOR_DISCARD = 10       # discard bad variants after 10 trials
MAX_REGRESSION_FOR_DISCARD = 0.05  # 5% accuracy drop triggers discard
OPTIMIZATION_INTERVAL_JOBS = 3     # run optimizer every Nth job

# ---------------------------------------------------------------------------
# Self-review (Loop 2)
# ---------------------------------------------------------------------------
SELF_REVIEW_ENABLED = True         # can be toggled off

# ---------------------------------------------------------------------------
# Embedding model (local via Ollama)
# ---------------------------------------------------------------------------
EMBEDDING_MODEL = "nomic-embed-text"
EMBEDDING_DIM = 768
EMBEDDING_MAX_TEXT = 32000  # truncate input to this many chars

# Similarity search
SIMILARITY_MIN_THRESHOLD = 0.55   # minimum cosine similarity to include
SIMILARITY_TOP_K = 5              # max results per search

# ---------------------------------------------------------------------------
# Purge strategy: when limits are hit, delete entries with lowest weight
# from the oldest epochs first. Human corrections are protected from purge.
# ---------------------------------------------------------------------------
PURGE_BATCH_SIZE = 500  # delete this many at a time

# ---------------------------------------------------------------------------
# Field-specific learning weights — how much to trust corrections per field
# ---------------------------------------------------------------------------
# Peptide corrections grounded in the scientific definition (2-100 AA active drug)
# are especially durable because the definition is objective and doesn't change.
FIELD_CORRECTION_WEIGHTS = {
    "peptide": {
        "base_weight": 1.2,         # 20% bonus — definition-grounded
        "definition_keywords": [     # if correction reasoning mentions these,
            "amino acid", "AA",      # use DEFINITION_DECAY_RATE instead of
            "2-100", "molecular",    # SELF_REVIEW_DECAY_RATE
            "monoclonal antibody",
            "nutritional formula",
            "active drug", "active therapeutic",
        ],
    },
    "classification": {"base_weight": 1.0},
    "delivery_mode": {"base_weight": 1.0},
    "outcome": {"base_weight": 1.0},
    "reason_for_failure": {"base_weight": 1.0},
}

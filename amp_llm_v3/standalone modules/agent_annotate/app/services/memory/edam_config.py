"""
EDAM (Experience-Driven Annotation Memory) configuration constants.

All tunable parameters for the self-learning system in one place.
These values are designed for the agent_annotate pipeline running
on Ollama with local models — no cloud APIs.
"""

# ---------------------------------------------------------------------------
# Memory budget — max tokens of EDAM guidance injected per LLM call
# ---------------------------------------------------------------------------
MEMORY_BUDGET_TOKENS = 2000
CHARS_PER_TOKEN = 4  # heuristic for English text

# Budget allocation by category (must sum to 1.0)
BUDGET_ALLOCATION = {
    "corrections": 0.50,       # 1000 tokens — most valuable (learned mistakes)
    "stable_exemplars": 0.25,  # 500 tokens  — known-good few-shot examples
    "prompt_guidance": 0.15,   # 300 tokens  — prompt variant instructions
    "anomaly_warnings": 0.10,  # 200 tokens  — statistical anomaly flags
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
SELF_REVIEW_MAX_ITEMS = 10         # max flagged items to self-review per job

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
# Database limits — hard caps to prevent unbounded growth
# ---------------------------------------------------------------------------
MAX_EXPERIENCES = 10000
MAX_CORRECTIONS = 5000
MAX_PROMPT_VARIANTS = 100
MAX_EMBEDDINGS = 15000  # experiences + corrections

# Purge strategy: when limits are hit, delete entries with lowest weight
# from the oldest epochs first. Human corrections are protected from purge.
PURGE_BATCH_SIZE = 500  # delete this many at a time

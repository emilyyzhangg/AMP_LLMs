"""
EDAM (Experience-Driven Annotation Memory) configuration constants.

Hardware-aware: call get_profile() to get the right constants for the
current hardware. Mac Mini uses conservative limits to avoid memory
pressure; server uses generous limits for long-term learning accumulation.

All tunable parameters for the self-learning system in one place.
Designed for the agent_annotate pipeline running on Ollama — no cloud APIs.
"""

import csv
import logging
from pathlib import Path

_logger = logging.getLogger("agent_annotate.edam.config")


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
    "corrections": 0.40,           # most valuable (learned mistakes)
    "stable_exemplars": 0.25,      # known-good few-shot examples
    "reasoning_patterns": 0.15,    # general rules from consistency/self-audit
    "prompt_guidance": 0.10,       # prompt variant instructions
    "anomaly_warnings": 0.10,      # statistical anomaly flags
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
    "classification": {
        "base_weight": 1.1,         # v11: slight bonus — AMP classification corrections
        "definition_keywords": [     # are grounded in antimicrobial mechanism
            "antimicrobial", "membrane disruption", "DRAMP", "DBAASP",
            "pore formation", "bactericidal",
        ],
    },
    "delivery_mode": {"base_weight": 1.0},
    "outcome": {
        "base_weight": 1.1,         # v11: slight bonus — outcome corrections
        "definition_keywords": [     # are grounded in registry status
            "hasResults", "overallStatus", "registry",
            "RECRUITING", "COMPLETED", "publication",
        ],
    },
    "reason_for_failure": {"base_weight": 1.0},
}

# ---------------------------------------------------------------------------
# v11: Field-specific snippet length overrides for Mac Mini
# Peptide needs longer snippets to preserve amino acid count evidence.
# ---------------------------------------------------------------------------
FIELD_SNIPPET_OVERRIDES = {
    "mac_mini": {
        "peptide": 400,     # up from 250 — preserve AA count evidence
    },
}

# ---------------------------------------------------------------------------
# v18: Training NCT allowlist — EDAM only learns from these NCTs.
# The training set CSV contains 642 dual-annotated NCTs. Remaining NCTs
# are the held-out test set for final evaluation. This prevents EDAM from
# learning patterns from test data, which would invalidate the evaluation.
# ---------------------------------------------------------------------------
_TRAINING_CSV = Path(__file__).resolve().parents[3] / "docs" / "human_ground_truth_train_df.csv"
_TEST_BATCH = Path(__file__).resolve().parents[3] / "scripts" / "fast_learning_batch_50.txt"
# 2026-05-11: user-defined formal validation + test cohorts. Sourced
# from clinical_trials-with-sequences.xlsx (the master annotation file)
# and extracted via scripts/extract_val_test_gt.py. These NCTs are
# OUTSIDE the original 680-NCT training CSV — they expand the GT
# universe rather than partitioning the existing one. EDAM still
# learns only from TRAINING_NCTS (which excludes val + test).
_VAL_CSV = Path(__file__).resolve().parents[3] / "docs" / "human_ground_truth_val_df.csv"
_TEST_CSV = Path(__file__).resolve().parents[3] / "docs" / "human_ground_truth_test_df.csv"


def _load_training_ncts() -> set[str]:
    """Load training NCT IDs from the ground truth CSV."""
    if not _TRAINING_CSV.exists():
        _logger.warning("Training CSV not found at %s — EDAM will learn from ALL NCTs", _TRAINING_CSV)
        return set()
    try:
        with open(_TRAINING_CSV) as f:
            reader = csv.DictReader(f)
            ncts = {row["nct_id"].strip().upper() for row in reader if row.get("nct_id")}
        _logger.info("Loaded %d training NCTs from %s", len(ncts), _TRAINING_CSV.name)
        return ncts
    except Exception as e:
        _logger.error("Failed to load training CSV: %s", e)
        return set()


def _load_test_batch_ncts() -> set[str]:
    """Load concordance test-batch NCTs to permanently exclude from EDAM learning.

    These 50 NCTs are used for concordance measurement runs and must never
    contribute to EDAM learning — doing so would let the system 'study' the
    test set and inflate concordance scores on subsequent runs.
    """
    if not _TEST_BATCH.exists():
        _logger.warning("Test batch file not found at %s — no NCTs excluded from EDAM", _TEST_BATCH)
        return set()
    try:
        with open(_TEST_BATCH) as f:
            ncts = {line.strip().upper() for line in f if line.strip()}
        _logger.info("Excluding %d test-batch NCTs from EDAM learning", len(ncts))
        return ncts
    except Exception as e:
        _logger.error("Failed to load test batch file: %s", e)
        return set()


def _load_csv_ncts(path: Path, label: str) -> set[str]:
    """Generic NCT loader for the new val/test CSVs (same schema as training)."""
    if not path.exists():
        _logger.warning("%s CSV not found at %s — set will be empty", label, path)
        return set()
    try:
        with open(path) as f:
            reader = csv.DictReader(f)
            ncts = {row["nct_id"].strip().upper() for row in reader if row.get("nct_id")}
        _logger.info("Loaded %d %s NCTs from %s", len(ncts), label, path.name)
        return ncts
    except Exception as e:
        _logger.error("Failed to load %s CSV: %s", label, e)
        return set()


# Set definitions — clear separation:
#   TRAINING_NCTS    = iteration/EDAM-learning pool (from training CSV minus
#                     legacy test_batch_50, val, and new test cohorts)
#   VALIDATION_NCTS  = formal validation cohort (86 NCTs) — used to score
#                     progress at decision points, never enters EDAM
#   NEW_TEST_NCTS    = formal test cohort (85 NCTs) — single-shot use only
#   TEST_BATCH_NCTS  = legacy test batch (50 NCTs) — kept for historical
#                     scoring; subsumed by NEW_TEST_NCTS going forward
#   ALL_GT_NCTS      = union of all four — the router's allow-list when
#                     allow_test_batch=True. Annotating any of these is OK;
#                     EDAM gating (in stability_tracker + memory_store) uses
#                     TRAINING_NCTS only, so val/test annotations never
#                     contaminate learning.
_train_ncts = _load_training_ncts()
_legacy_test_batch = _load_test_batch_ncts()
VALIDATION_NCTS: set[str] = _load_csv_ncts(_VAL_CSV, "validation")
NEW_TEST_NCTS: set[str] = _load_csv_ncts(_TEST_CSV, "test")
TEST_BATCH_NCTS: set[str] = _legacy_test_batch

TRAINING_NCTS: set[str] = (
    _train_ncts - _legacy_test_batch - VALIDATION_NCTS - NEW_TEST_NCTS
)
ALL_GT_NCTS: set[str] = (
    _train_ncts | VALIDATION_NCTS | NEW_TEST_NCTS | _legacy_test_batch
)


# 2026-06-03: MASTER NCT extension. The annotator-master xlsx contains
# 1844 unique trials; only 850 are in ALL_GT_NCTS. The remaining ~994
# either have zero human annotation (576) or partial annotation outside
# the formal cohorts (~418). We can still produce agent annotations for
# them — they extend the publication dataset, never trigger EDAM
# (gated on TRAINING_NCTS), and have no GT to score against.
#
# To submit any of these, set `allow_external=true` on the job request.
# The router widens its allowed set to ALL_SUBMITTABLE_NCTS for that
# request. EDAM gating is unchanged.

import json as _json  # local import to keep top-of-file imports unchanged

_MASTER_UNANNOTATED = Path(__file__).resolve().parents[3] / "scripts" / "master_unannotated_576.json"
_MASTER_PARTIAL = Path(__file__).resolve().parents[3] / "scripts" / "master_partial_outside_gt_423.json"
_MASTER_EXTENSION = Path(__file__).resolve().parents[3] / "scripts" / "master_extension_v1.json"


def _load_json_ncts(path: Path, label: str) -> set[str]:
    """Load a JSON array of NCT IDs into an uppercased set."""
    if not path.exists():
        _logger.warning("%s file not found at %s — set will be empty", label, path)
        return set()
    try:
        data = _json.loads(path.read_text())
        ncts = {str(n).strip().upper() for n in data if str(n).strip().upper().startswith("NCT")}
        _logger.info("Loaded %d %s NCTs from %s", len(ncts), label, path.name)
        return ncts
    except Exception as e:
        _logger.error("Failed to load %s JSON: %s", label, e)
        return set()


MASTER_NCTS: set[str] = (
    _load_json_ncts(_MASTER_UNANNOTATED, "master-unannotated")
    | _load_json_ncts(_MASTER_PARTIAL, "master-partial-outside-gt")
    | _load_json_ncts(_MASTER_EXTENSION, "master-extension")
)
ALL_SUBMITTABLE_NCTS: set[str] = ALL_GT_NCTS | MASTER_NCTS

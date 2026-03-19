"""
EDAM Memory Store — SQLite + embedding-based persistent learning memory.

Core persistence layer for the self-learning system. Stores annotation
experiences, corrections (human and self-review), prompt variants, and
evidence embeddings. Provides version-gated retrieval with epoch-based
decay and hard token budgets.

All writes are atomic (SQLite transactions). Reads are concurrent-safe
via WAL mode. The store is a singleton initialized once at import.
"""

import json
import logging
import sqlite3
import struct
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.config import RESULTS_DIR
from app.services.memory.edam_config import (
    MEMORY_BUDGET_TOKENS, CHARS_PER_TOKEN, BUDGET_ALLOCATION,
    HUMAN_DECAY_RATE, HUMAN_FLOOR,
    SELF_REVIEW_DECAY_RATE, SELF_REVIEW_FLOOR,
    EXPERIENCE_DECAY_RATE, EXPERIENCE_FLOOR,
    EMBEDDING_MODEL, EMBEDDING_DIM, EMBEDDING_MAX_TEXT,
    SIMILARITY_MIN_THRESHOLD, SIMILARITY_TOP_K,
    MAX_EXPERIENCES, MAX_CORRECTIONS, MAX_EMBEDDINGS,
    PURGE_BATCH_SIZE, ANOMALY_THRESHOLD, ANOMALY_MIN_TRIALS,
)

logger = logging.getLogger("agent_annotate.edam.store")

DB_PATH = RESULTS_DIR / "edam.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS config_epochs (
    epoch           INTEGER PRIMARY KEY AUTOINCREMENT,
    config_hash     TEXT NOT NULL UNIQUE,
    git_commit      TEXT NOT NULL,
    prompt_versions TEXT DEFAULT '{}',
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS experiences (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nct_id          TEXT NOT NULL,
    field_name      TEXT NOT NULL,
    job_id          TEXT NOT NULL,
    value           TEXT NOT NULL,
    confidence      REAL NOT NULL,
    consensus_reached BOOLEAN NOT NULL,
    evidence_summary TEXT,
    reasoning       TEXT,
    config_hash     TEXT NOT NULL,
    git_commit      TEXT NOT NULL,
    prompt_version  TEXT DEFAULT 'base',
    epoch           INTEGER NOT NULL,
    created_at      TEXT NOT NULL,
    UNIQUE(nct_id, field_name, job_id)
);
CREATE INDEX IF NOT EXISTS idx_exp_field ON experiences(field_name);
CREATE INDEX IF NOT EXISTS idx_exp_nct ON experiences(nct_id);
CREATE INDEX IF NOT EXISTS idx_exp_epoch ON experiences(epoch);

CREATE TABLE IF NOT EXISTS corrections (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nct_id          TEXT NOT NULL,
    field_name      TEXT NOT NULL,
    job_id          TEXT NOT NULL,
    original_value  TEXT NOT NULL,
    corrected_value TEXT NOT NULL,
    source          TEXT NOT NULL,
    reflection      TEXT NOT NULL,
    evidence_citations TEXT,
    reviewer_note   TEXT,
    config_hash     TEXT NOT NULL,
    epoch           INTEGER NOT NULL,
    created_at      TEXT NOT NULL,
    UNIQUE(nct_id, field_name, job_id, source)
);
CREATE INDEX IF NOT EXISTS idx_corr_field ON corrections(field_name);

CREATE TABLE IF NOT EXISTS prompt_variants (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    field_name      TEXT NOT NULL,
    variant_name    TEXT NOT NULL,
    prompt_diff     TEXT NOT NULL,
    parent_variant  TEXT DEFAULT 'base',
    status          TEXT DEFAULT 'testing',
    accuracy_score  REAL DEFAULT 0.0,
    total_trials    INTEGER DEFAULT 0,
    correct_trials  INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL,
    promoted_at     TEXT,
    discarded_at    TEXT,
    epoch           INTEGER NOT NULL,
    UNIQUE(field_name, variant_name)
);

CREATE TABLE IF NOT EXISTS embeddings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ref_table       TEXT NOT NULL,
    ref_id          INTEGER NOT NULL,
    embedding       BLOB NOT NULL,
    created_at      TEXT NOT NULL,
    UNIQUE(ref_table, ref_id)
);

CREATE TABLE IF NOT EXISTS stability_index (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nct_id          TEXT NOT NULL,
    field_name      TEXT NOT NULL,
    stability_score REAL NOT NULL,
    majority_value  TEXT,
    evidence_grade  TEXT,
    total_runs      INTEGER NOT NULL,
    distinct_values INTEGER NOT NULL,
    last_computed   TEXT NOT NULL,
    UNIQUE(nct_id, field_name)
);
CREATE INDEX IF NOT EXISTS idx_stab_field ON stability_index(field_name);
"""


def _now_iso() -> str:
    return datetime.now().isoformat()


def _serialize_embedding(vec: list[float]) -> bytes:
    """Pack a float list into a compact binary blob."""
    return struct.pack(f"{len(vec)}f", *vec)


def _deserialize_embedding(blob: bytes) -> list[float]:
    """Unpack a binary blob into a float list."""
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors. Pure Python for portability."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def compute_weight(experience_epoch: int, current_epoch: int,
                   source: str = "experience") -> float:
    """
    Compute relevance weight based on epoch distance.

    Decay is exponential with a floor to prevent total amnesia.
    Human corrections decay slowest (they're evidence-grounded truth).
    """
    epoch_distance = max(0, current_epoch - experience_epoch)

    if source == "human_review":
        return max(HUMAN_FLOOR, 1.0 * (HUMAN_DECAY_RATE ** epoch_distance))
    elif source == "self_review":
        return max(SELF_REVIEW_FLOOR, 0.9 * (SELF_REVIEW_DECAY_RATE ** epoch_distance))
    else:
        return max(EXPERIENCE_FLOOR, 1.0 * (EXPERIENCE_DECAY_RATE ** epoch_distance))


class MemoryStore:
    """SQLite-backed experience database with embedding search."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(db_path), check_same_thread=False,
            isolation_level="DEFERRED",
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._init_schema()
        logger.info("EDAM memory store initialized at %s", db_path)

    def _init_schema(self):
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self):
        self._conn.close()

    # --- Epoch management ---

    def get_or_create_epoch(self, config_hash: str, git_commit: str,
                            prompt_versions: dict[str, str] | None = None) -> int:
        row = self._conn.execute(
            "SELECT epoch FROM config_epochs WHERE config_hash = ?",
            (config_hash,),
        ).fetchone()
        if row:
            return row["epoch"]
        self._conn.execute(
            "INSERT INTO config_epochs (config_hash, git_commit, prompt_versions, created_at) "
            "VALUES (?, ?, ?, ?)",
            (config_hash, git_commit, json.dumps(prompt_versions or {}), _now_iso()),
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT epoch FROM config_epochs WHERE config_hash = ?",
            (config_hash,),
        ).fetchone()
        epoch = row["epoch"]
        logger.info("EDAM: new epoch %d for config %s (commit %s)", epoch, config_hash[:8], git_commit)
        return epoch

    def get_current_epoch(self) -> int:
        row = self._conn.execute("SELECT MAX(epoch) as e FROM config_epochs").fetchone()
        return row["e"] if row and row["e"] is not None else 0

    # --- Experience CRUD ---

    def store_experience(self, nct_id: str, field_name: str, job_id: str,
                         value: str, confidence: float, consensus_reached: bool,
                         evidence_summary: str, reasoning: str,
                         config_hash: str, git_commit: str,
                         prompt_version: str = "base") -> int:
        epoch = self.get_or_create_epoch(config_hash, git_commit)
        self._conn.execute(
            "INSERT OR REPLACE INTO experiences "
            "(nct_id, field_name, job_id, value, confidence, consensus_reached, "
            "evidence_summary, reasoning, config_hash, git_commit, prompt_version, "
            "epoch, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (nct_id, field_name, job_id, value, confidence, consensus_reached,
             (evidence_summary or "")[:2000], (reasoning or "")[:1000],
             config_hash, git_commit, prompt_version, epoch, _now_iso()),
        )
        self._conn.commit()
        row = self._conn.execute("SELECT last_insert_rowid()").fetchone()
        self._enforce_limits("experiences", MAX_EXPERIENCES)
        return row[0]

    def get_experiences(self, nct_id: str = None, field_name: str = None,
                        min_epoch: int = None, limit: int = 50) -> list[dict]:
        clauses, params = [], []
        if nct_id:
            clauses.append("nct_id = ?")
            params.append(nct_id)
        if field_name:
            clauses.append("field_name = ?")
            params.append(field_name)
        if min_epoch is not None:
            clauses.append("epoch >= ?")
            params.append(min_epoch)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        rows = self._conn.execute(
            f"SELECT * FROM experiences{where} ORDER BY epoch DESC, id DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        return [dict(r) for r in rows]

    # --- Correction CRUD ---

    def store_correction(self, nct_id: str, field_name: str, job_id: str,
                         original_value: str, corrected_value: str,
                         source: str, reflection: str,
                         evidence_citations: list[dict],
                         config_hash: str, git_commit: str,
                         reviewer_note: str = None) -> int:
        if not evidence_citations:
            raise ValueError("Corrections require at least one evidence citation")
        epoch = self.get_or_create_epoch(config_hash, git_commit)
        self._conn.execute(
            "INSERT OR REPLACE INTO corrections "
            "(nct_id, field_name, job_id, original_value, corrected_value, "
            "source, reflection, evidence_citations, reviewer_note, "
            "config_hash, epoch, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (nct_id, field_name, job_id, original_value, corrected_value,
             source, reflection, json.dumps(evidence_citations),
             reviewer_note, config_hash, epoch, _now_iso()),
        )
        self._conn.commit()
        row = self._conn.execute("SELECT last_insert_rowid()").fetchone()
        self._enforce_limits("corrections", MAX_CORRECTIONS)
        return row[0]

    def get_corrections(self, field_name: str = None,
                        min_epoch: int = None, limit: int = 20) -> list[dict]:
        clauses, params = [], []
        if field_name:
            clauses.append("field_name = ?")
            params.append(field_name)
        if min_epoch is not None:
            clauses.append("epoch >= ?")
            params.append(min_epoch)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        rows = self._conn.execute(
            f"SELECT * FROM corrections{where} ORDER BY epoch DESC, id DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        return [dict(r) for r in rows]

    # --- Embedding operations ---

    async def generate_embedding(self, text: str) -> list[float]:
        """Generate an embedding via Ollama's nomic-embed-text."""
        from app.services.ollama_client import ollama_client
        await ollama_client.ensure_model(EMBEDDING_MODEL)

        import httpx
        from app.config import OLLAMA_BASE_URL
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{OLLAMA_BASE_URL}/api/embeddings",
                json={"model": EMBEDDING_MODEL, "prompt": text[:EMBEDDING_MAX_TEXT]},
            )
            resp.raise_for_status()
            data = resp.json()
            return data["embedding"]

    async def store_embedding(self, ref_table: str, ref_id: int,
                              text: str) -> None:
        vec = await self.generate_embedding(text)
        blob = _serialize_embedding(vec)
        self._conn.execute(
            "INSERT OR REPLACE INTO embeddings (ref_table, ref_id, embedding, created_at) "
            "VALUES (?, ?, ?, ?)",
            (ref_table, ref_id, blob, _now_iso()),
        )
        self._conn.commit()
        self._enforce_limits("embeddings", MAX_EMBEDDINGS)

    async def search_similar(self, query_text: str, ref_table: str,
                             field_name: str = None, top_k: int = SIMILARITY_TOP_K,
                             min_similarity: float = SIMILARITY_MIN_THRESHOLD) -> list[dict]:
        """Find top-k most similar records by cosine similarity."""
        query_vec = await self.generate_embedding(query_text)

        # Get all embeddings for the ref_table, join with source table for field filtering
        if field_name and ref_table == "corrections":
            rows = self._conn.execute(
                "SELECT e.ref_id, e.embedding, c.* FROM embeddings e "
                "JOIN corrections c ON e.ref_id = c.id "
                "WHERE e.ref_table = ? AND c.field_name = ?",
                (ref_table, field_name),
            ).fetchall()
        elif field_name and ref_table == "experiences":
            rows = self._conn.execute(
                "SELECT e.ref_id, e.embedding, x.* FROM embeddings e "
                "JOIN experiences x ON e.ref_id = x.id "
                "WHERE e.ref_table = ? AND x.field_name = ?",
                (ref_table, field_name),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM embeddings WHERE ref_table = ?",
                (ref_table,),
            ).fetchall()

        scored = []
        for row in rows:
            stored_vec = _deserialize_embedding(row["embedding"])
            sim = _cosine_similarity(query_vec, stored_vec)
            if sim >= min_similarity:
                scored.append((sim, dict(row)))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [{"similarity": s, **d} for s, d in scored[:top_k]]

    # --- Stability index ---

    def upsert_stability(self, nct_id: str, field_name: str,
                         stability_score: float, majority_value: str,
                         evidence_grade: str, total_runs: int,
                         distinct_values: int) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO stability_index "
            "(nct_id, field_name, stability_score, majority_value, evidence_grade, "
            "total_runs, distinct_values, last_computed) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (nct_id, field_name, stability_score, majority_value, evidence_grade,
             total_runs, distinct_values, _now_iso()),
        )
        self._conn.commit()

    def get_stability(self, nct_id: str = None, field_name: str = None,
                      min_score: float = None, max_score: float = None,
                      limit: int = 100) -> list[dict]:
        clauses, params = [], []
        if nct_id:
            clauses.append("nct_id = ?")
            params.append(nct_id)
        if field_name:
            clauses.append("field_name = ?")
            params.append(field_name)
        if min_score is not None:
            clauses.append("stability_score >= ?")
            params.append(min_score)
        if max_score is not None:
            clauses.append("stability_score <= ?")
            params.append(max_score)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        rows = self._conn.execute(
            f"SELECT * FROM stability_index{where} "
            f"ORDER BY stability_score DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        return [dict(r) for r in rows]

    def get_stable_exemplars(self, field_name: str, min_stability: float = 0.9,
                             min_runs: int = 3, limit: int = 5) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM stability_index "
            "WHERE field_name = ? AND stability_score >= ? AND total_runs >= ? "
            "ORDER BY stability_score DESC, total_runs DESC LIMIT ?",
            (field_name, min_stability, min_runs, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # --- Prompt variants ---

    def store_variant(self, field_name: str, variant_name: str,
                      prompt_diff: str, parent_variant: str = "base",
                      epoch: int = None) -> int:
        if epoch is None:
            epoch = self.get_current_epoch()
        self._conn.execute(
            "INSERT OR REPLACE INTO prompt_variants "
            "(field_name, variant_name, prompt_diff, parent_variant, status, "
            "epoch, created_at) VALUES (?, ?, ?, ?, 'testing', ?, ?)",
            (field_name, variant_name, prompt_diff, parent_variant, epoch, _now_iso()),
        )
        self._conn.commit()
        row = self._conn.execute("SELECT last_insert_rowid()").fetchone()
        return row[0]

    def update_variant_stats(self, field_name: str, variant_name: str,
                             is_correct: bool) -> None:
        self._conn.execute(
            "UPDATE prompt_variants SET total_trials = total_trials + 1, "
            "correct_trials = correct_trials + CASE WHEN ? THEN 1 ELSE 0 END, "
            "accuracy_score = CAST(correct_trials + CASE WHEN ? THEN 1 ELSE 0 END AS REAL) "
            "/ (total_trials + 1) "
            "WHERE field_name = ? AND variant_name = ?",
            (is_correct, is_correct, field_name, variant_name),
        )
        self._conn.commit()

    def promote_variant(self, field_name: str, variant_name: str) -> None:
        # Demote any currently promoted variant for this field
        self._conn.execute(
            "UPDATE prompt_variants SET status = 'superseded' "
            "WHERE field_name = ? AND status = 'promoted'",
            (field_name,),
        )
        self._conn.execute(
            "UPDATE prompt_variants SET status = 'promoted', promoted_at = ? "
            "WHERE field_name = ? AND variant_name = ?",
            (_now_iso(), field_name, variant_name),
        )
        self._conn.commit()

    def discard_variant(self, field_name: str, variant_name: str) -> None:
        self._conn.execute(
            "UPDATE prompt_variants SET status = 'discarded', discarded_at = ? "
            "WHERE field_name = ? AND variant_name = ?",
            (_now_iso(), field_name, variant_name),
        )
        self._conn.commit()

    def get_active_variant(self, field_name: str) -> str:
        row = self._conn.execute(
            "SELECT variant_name FROM prompt_variants "
            "WHERE field_name = ? AND status = 'promoted' "
            "ORDER BY promoted_at DESC LIMIT 1",
            (field_name,),
        ).fetchone()
        return row["variant_name"] if row else "base"

    def get_active_prompts(self) -> dict[str, str]:
        rows = self._conn.execute(
            "SELECT field_name, variant_name FROM prompt_variants "
            "WHERE status = 'promoted'"
        ).fetchall()
        return {r["field_name"]: r["variant_name"] for r in rows}

    # --- Anomaly detection ---

    def detect_anomalies(self, field_name: str,
                         recent_epochs: int = 3) -> list[dict]:
        """Flag if >ANOMALY_THRESHOLD of trials share the same value."""
        current_epoch = self.get_current_epoch()
        min_epoch = max(0, current_epoch - recent_epochs)
        rows = self._conn.execute(
            "SELECT value, COUNT(*) as cnt FROM experiences "
            "WHERE field_name = ? AND epoch >= ? "
            "GROUP BY value ORDER BY cnt DESC",
            (field_name, min_epoch),
        ).fetchall()
        if not rows:
            return []
        total = sum(r["cnt"] for r in rows)
        if total < ANOMALY_MIN_TRIALS:
            return []
        anomalies = []
        for row in rows:
            pct = row["cnt"] / total
            if pct > ANOMALY_THRESHOLD:
                anomalies.append({
                    "field_name": field_name,
                    "dominant_value": row["value"],
                    "pct": round(pct, 3),
                    "count": row["cnt"],
                    "total": total,
                    "warning": (
                        f"{pct:.0%} of recent trials have {field_name}="
                        f"'{row['value']}'. Verify this isn't a systematic bias."
                    ),
                })
        return anomalies

    # --- Budget-aware guidance retrieval ---

    async def build_guidance(self, nct_id: str, field_name: str,
                             evidence_text: str,
                             max_tokens: int = MEMORY_BUDGET_TOKENS) -> str:
        """Build the full EDAM guidance block for an annotation call.

        Respects token budget. Returns empty string if no relevant memories.
        """
        current_epoch = self.get_current_epoch()
        if current_epoch == 0:
            return ""  # cold start — no memories yet

        parts = []
        budget_chars = max_tokens * CHARS_PER_TOKEN

        # --- 1. Corrections (50% budget) ---
        corr_budget = int(budget_chars * BUDGET_ALLOCATION["corrections"])
        corrections = self.get_corrections(field_name=field_name, limit=10)
        if corrections:
            corr_lines = []
            corr_used = 0
            for c in corrections:
                weight = compute_weight(c["epoch"], current_epoch, c["source"])
                if weight < 0.1:
                    continue
                line = (
                    f"- {c['nct_id']}/{c['field_name']}: corrected from "
                    f"'{c['original_value']}' to '{c['corrected_value']}' — "
                    f"{c['reflection'][:200]}"
                )
                if corr_used + len(line) > corr_budget:
                    break
                corr_lines.append(line)
                corr_used += len(line)
            if corr_lines:
                parts.append("[PAST CORRECTIONS]")
                parts.extend(corr_lines)

        # Also try semantic search for similar corrections
        if evidence_text:
            try:
                similar = await self.search_similar(
                    evidence_text[:500], "corrections",
                    field_name=field_name, top_k=3,
                )
                for s in similar:
                    if s.get("corrected_value"):
                        line = (
                            f"- Similar trial {s.get('nct_id', '?')}: "
                            f"'{s.get('original_value', '?')}' was wrong, "
                            f"correct is '{s['corrected_value']}' "
                            f"(similarity={s['similarity']:.2f})"
                        )
                        parts.append(line)
            except Exception:
                pass  # embedding search failure is non-fatal

        # --- 2. Stable exemplars (25% budget) ---
        exemplar_budget = int(budget_chars * BUDGET_ALLOCATION["stable_exemplars"])
        exemplars = self.get_stable_exemplars(field_name, limit=5)
        if exemplars:
            ex_lines = []
            ex_used = 0
            for ex in exemplars:
                line = (
                    f"- {ex['nct_id']}: consistently '{ex['majority_value']}' "
                    f"({ex['total_runs']} runs, evidence={ex['evidence_grade']})"
                )
                if ex_used + len(line) > exemplar_budget:
                    break
                ex_lines.append(line)
                ex_used += len(line)
            if ex_lines:
                parts.append("[STABLE PATTERNS]")
                parts.extend(ex_lines)

        # --- 3. Anomaly warnings (10% budget) ---
        anomalies = self.detect_anomalies(field_name)
        if anomalies:
            parts.append("[WARNINGS]")
            for a in anomalies:
                parts.append(f"- {a['warning']}")

        if not parts:
            return ""

        block = "=== EDAM GUIDANCE ===\n" + "\n".join(parts) + "\n=== END GUIDANCE ==="

        # Final budget enforcement
        max_chars = max_tokens * CHARS_PER_TOKEN
        if len(block) > max_chars:
            block = block[:max_chars - 20] + "\n=== END GUIDANCE ==="

        return block

    async def get_anomaly_warnings(self, field_name: str,
                                   max_tokens: int = 200) -> str:
        """Get only anomaly warnings (safe for verifier injection)."""
        anomalies = self.detect_anomalies(field_name)
        if not anomalies:
            return ""
        lines = ["[EDAM WARNING]"]
        for a in anomalies:
            lines.append(a["warning"])
        text = "\n".join(lines)
        max_chars = max_tokens * CHARS_PER_TOKEN
        return text[:max_chars]

    # --- Maintenance ---

    def _enforce_limits(self, table: str, max_entries: int) -> None:
        """Purge oldest low-weight entries if over limit."""
        row = self._conn.execute(f"SELECT COUNT(*) as cnt FROM {table}").fetchone()
        if row["cnt"] <= max_entries:
            return
        overflow = row["cnt"] - max_entries
        to_delete = min(overflow + PURGE_BATCH_SIZE, row["cnt"] // 4)
        if table == "corrections":
            # Never purge human corrections
            self._conn.execute(
                f"DELETE FROM {table} WHERE id IN ("
                f"SELECT id FROM {table} WHERE source != 'human_review' "
                f"ORDER BY epoch ASC, id ASC LIMIT ?)",
                (to_delete,),
            )
        else:
            self._conn.execute(
                f"DELETE FROM {table} WHERE id IN ("
                f"SELECT id FROM {table} ORDER BY epoch ASC, id ASC LIMIT ?)",
                (to_delete,),
            )
        self._conn.commit()
        logger.info("EDAM: purged %d entries from %s (was %d, limit %d)",
                     to_delete, table, row["cnt"], max_entries)

    def get_stats(self) -> dict:
        """Return table counts and database size for monitoring."""
        stats = {}
        for table in ["experiences", "corrections", "prompt_variants",
                       "embeddings", "stability_index", "config_epochs"]:
            row = self._conn.execute(f"SELECT COUNT(*) as cnt FROM {table}").fetchone()
            stats[table] = row["cnt"]
        stats["db_size_mb"] = round(self._db_path.stat().st_size / (1024 * 1024), 2)
        stats["current_epoch"] = self.get_current_epoch()
        return stats


# Module-level singleton
memory_store = MemoryStore()

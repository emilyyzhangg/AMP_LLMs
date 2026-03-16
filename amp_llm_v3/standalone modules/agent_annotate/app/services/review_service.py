"""
Human review queue service - manages flagged annotations.

Persists the review queue as JSON at results/review_queue.json so it
survives restarts.  Uses atomic write (tmp + rename) to prevent corruption.
"""

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from app.models.job import ReviewItem

logger = logging.getLogger("agent_annotate.review_service")


class ReviewService:
    """Disk-backed review queue for flagged annotations."""

    def __init__(self, persist_path: Optional[Path] = None):
        self._queue: dict[str, ReviewItem] = {}  # key: "{job_id}:{nct_id}:{field_name}"
        if persist_path is not None:
            self._persist_path = persist_path
        else:
            # Default: results/review_queue.json relative to project root
            from app.config import RESULTS_DIR
            self._persist_path = RESULTS_DIR / "review_queue.json"
        self._load()

    def _key(self, job_id: str, nct_id: str, field_name: str) -> str:
        return f"{job_id}:{nct_id}:{field_name}"

    # -- persistence helpers --------------------------------------------------

    def _load(self) -> None:
        """Load the review queue from disk on startup."""
        if not self._persist_path.exists():
            logger.info("No existing review queue file; starting empty.")
            return
        try:
            raw = json.loads(self._persist_path.read_text(encoding="utf-8"))
            for key, item_dict in raw.items():
                self._queue[key] = ReviewItem(**item_dict)
            logger.info(f"Loaded {len(self._queue)} review items from {self._persist_path}")
        except Exception as exc:
            logger.warning(f"Failed to load review queue from {self._persist_path}: {exc}")

    def _save(self) -> None:
        """Atomically persist the review queue to disk (write tmp then rename)."""
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = {k: v.model_dump(mode="json") for k, v in self._queue.items()}
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=str(self._persist_path.parent),
                prefix=".review_queue_",
                suffix=".tmp",
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, default=str)
                os.replace(tmp_path, str(self._persist_path))
            except BaseException:
                # Clean up temp file on any write/rename failure
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except Exception as exc:
            logger.error(f"Failed to save review queue: {exc}")

    # -- public API (unchanged signatures) ------------------------------------

    def add(self, item: ReviewItem) -> None:
        """Add an item to the review queue and persist."""
        key = self._key(item.job_id, item.nct_id, item.field_name)
        self._queue[key] = item
        self._save()

    def get_pending(self, job_id: Optional[str] = None) -> list[ReviewItem]:
        """Return all pending review items, optionally filtered by job."""
        items = [v for v in self._queue.values() if v.status == "pending"]
        if job_id:
            items = [i for i in items if i.job_id == job_id]
        return items

    def get_all(self, job_id: Optional[str] = None) -> list[ReviewItem]:
        """Return all review items regardless of status."""
        items = list(self._queue.values())
        if job_id:
            items = [i for i in items if i.job_id == job_id]
        return items

    def decide(
        self,
        job_id: str,
        nct_id: str,
        field_name: str,
        action: str,
        value: Optional[str] = None,
        note: Optional[str] = None,
    ) -> Optional[ReviewItem]:
        """Apply a review decision (approve / override / skip) and persist."""
        key = self._key(job_id, nct_id, field_name)
        item = self._queue.get(key)
        if not item:
            return None
        item.status = action  # "approved" | "overridden" | "skipped"
        if value is not None:
            item.reviewer_value = value
        if note is not None:
            item.reviewer_note = note
        self._save()
        return item

    def retry(self, job_id: str) -> int:
        """Reset all pending items for a job back to pending (no-op currently)."""
        count = 0
        for item in self._queue.values():
            if item.job_id == job_id and item.status == "pending":
                count += 1
        return count


# Module-level singleton
review_service = ReviewService()

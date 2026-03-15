"""
Human review queue service - manages flagged annotations.
"""

from typing import Optional
from app.models.job import ReviewItem


class ReviewService:
    """In-memory review queue for flagged annotations."""

    def __init__(self):
        self._queue: dict[str, ReviewItem] = {}  # key: "{job_id}:{nct_id}:{field_name}"

    def _key(self, job_id: str, nct_id: str, field_name: str) -> str:
        return f"{job_id}:{nct_id}:{field_name}"

    def add(self, item: ReviewItem) -> None:
        """Add an item to the review queue."""
        key = self._key(item.job_id, item.nct_id, item.field_name)
        self._queue[key] = item

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
        """Apply a review decision (approve / override / skip)."""
        key = self._key(job_id, nct_id, field_name)
        item = self._queue.get(key)
        if not item:
            return None
        item.status = action  # "approved" | "overridden" | "skipped"
        if value is not None:
            item.reviewer_value = value
        if note is not None:
            item.reviewer_note = note
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

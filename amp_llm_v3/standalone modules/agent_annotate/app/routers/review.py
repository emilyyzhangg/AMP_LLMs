"""
Human review queue endpoints.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.review_service import review_service

router = APIRouter(prefix="/api/review", tags=["review"])


class ReviewDecision(BaseModel):
    action: str  # "approved" | "overridden" | "skipped"
    value: Optional[str] = None
    note: Optional[str] = None


@router.get("")
async def list_review_items(job_id: Optional[str] = None, status: str = "pending"):
    """List review items, optionally filtered by job and status."""
    if status == "pending":
        items = review_service.get_pending(job_id=job_id)
    else:
        items = review_service.get_all(job_id=job_id)
    return {"items": [item.model_dump() for item in items], "total": len(items)}


@router.post("/{job_id}/{nct_id}/{field_name}")
async def submit_review(
    job_id: str,
    nct_id: str,
    field_name: str,
    decision: ReviewDecision,
):
    """Submit a review decision for a flagged annotation."""
    if decision.action not in ("approved", "overridden", "skipped"):
        raise HTTPException(status_code=400, detail="Invalid action")

    item = review_service.decide(
        job_id=job_id,
        nct_id=nct_id,
        field_name=field_name,
        action=decision.action,
        value=decision.value,
        note=decision.note,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Review item not found")
    return item.model_dump()

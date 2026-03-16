"""
Human review queue endpoints.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.review_service import review_service

router = APIRouter(prefix="/api/review", tags=["review"])

# Valid values per field for dropdown selection in the review UI.
from agents.annotation.classification import VALID_VALUES as _CLS_VALS
from agents.annotation.peptide import VALID_VALUES as _PEP_VALS
from agents.annotation.outcome import VALID_VALUES as _OUT_VALS
from agents.annotation.delivery_mode import VALID_VALUES as _DM_VALS
from agents.annotation.failure_reason import VALID_VALUES as _FR_VALS

FIELD_VALID_VALUES: dict[str, list[str]] = {
    "classification": _CLS_VALS,
    "peptide": _PEP_VALS,
    "outcome": _OUT_VALS,
    "delivery_mode": _DM_VALS,
    "reason_for_failure": _FR_VALS,
}


class ReviewDecision(BaseModel):
    action: str  # "approved" | "overridden" | "skipped" | "retry"
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


@router.get("/field-values")
async def field_values():
    """Valid values for each annotation field and verifier model mapping."""
    from app.services.config_service import config_service
    cfg = config_service.get()
    model_map = {
        key: {"name": m.name, "role": m.role}
        for key, m in cfg.verification.models.items()
    }
    return {"fields": FIELD_VALID_VALUES, "model_map": model_map}


@router.get("/stats")
async def review_stats():
    """Summary stats for the review queue."""
    all_items = review_service.get_all()
    pending = [i for i in all_items if i.status == "pending"]
    decided = [i for i in all_items if i.status in ("approved", "overridden")]
    return {
        "total": len(all_items),
        "pending": len(pending),
        "decided": len(decided),
        "skipped": sum(1 for i in all_items if i.status == "skipped"),
    }


@router.post("/{job_id}/{nct_id}/{field_name}")
async def submit_review(
    job_id: str,
    nct_id: str,
    field_name: str,
    decision: ReviewDecision,
):
    """Submit a review decision for a flagged annotation."""
    valid_actions = ("approved", "overridden", "skipped", "retry")
    if decision.action not in valid_actions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action. Must be one of: {valid_actions}",
        )

    if decision.action == "retry":
        # Mark for retry — the frontend can re-submit this trial
        # through the pipeline with deeper search
        item = review_service.decide(
            job_id=job_id,
            nct_id=nct_id,
            field_name=field_name,
            action="retry",
            note=decision.note or "Sent back for deeper search",
        )
        if not item:
            raise HTTPException(status_code=404, detail="Review item not found")
        return {
            "status": "retry_queued",
            "item": item.model_dump(),
            "message": f"Re-submit {nct_id} to the pipeline for deeper research on {field_name}",
        }

    if decision.action == "overridden" and not decision.value:
        raise HTTPException(
            status_code=400,
            detail="Must provide a value when overriding",
        )

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
    return {"status": decision.action, "item": item.model_dump()}

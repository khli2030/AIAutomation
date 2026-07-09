"""Execution plan endpoints — implemented in Phase 5."""

from fastapi import APIRouter, HTTPException, status

router = APIRouter()


@router.get("/{plan_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def get_execution_plan(plan_id: int) -> None:
    raise HTTPException(status_code=501, detail="Not implemented yet (Phase 5)")


@router.get("/{plan_id}/jobs", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def list_plan_jobs(plan_id: int) -> None:
    raise HTTPException(status_code=501, detail="Not implemented yet (Phase 5)")

"""Execution job endpoints — dry-run / approve / run in Phases 5–6."""

from fastapi import APIRouter, HTTPException, status

router = APIRouter()


@router.post("/{job_id}/dry-run", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def dry_run_job(job_id: int) -> None:
    raise HTTPException(status_code=501, detail="Not implemented yet (Phase 6)")


@router.post("/{job_id}/approve", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def approve_job(job_id: int) -> None:
    raise HTTPException(status_code=501, detail="Not implemented yet (Phase 5)")


@router.post("/{job_id}/reject", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def reject_job(job_id: int) -> None:
    raise HTTPException(status_code=501, detail="Not implemented yet (Phase 5)")


@router.post("/{job_id}/run", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def run_job(job_id: int) -> None:
    """Real execution — only after dry-run success + approval (Phase 6)."""
    raise HTTPException(status_code=501, detail="Not implemented yet (Phase 6)")


@router.get("/{job_id}/results", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def get_job_results(job_id: int) -> None:
    raise HTTPException(status_code=501, detail="Not implemented yet (Phase 6)")

"""Dashboard and needs-review endpoints — Phase 7 UI support."""

from fastapi import APIRouter, HTTPException, status

router = APIRouter()


@router.get("/summary", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def dashboard_summary() -> None:
    raise HTTPException(status_code=501, detail="Not implemented yet (Phase 7)")

"""AI suggestion review endpoints — Phase 4.

AI-generated playbooks are never executed automatically.
"""

from fastapi import APIRouter, HTTPException, status

router = APIRouter()


@router.get("/needs-review", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def list_needs_review() -> None:
    """GET /needs-review is also exposed at root via main; placeholder here."""
    raise HTTPException(status_code=501, detail="Not implemented yet (Phase 3/4)")


@router.post("/{suggestion_id}/approve", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def approve_suggestion(suggestion_id: int) -> None:
    raise HTTPException(status_code=501, detail="Not implemented yet (Phase 4)")


@router.post("/{suggestion_id}/reject", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def reject_suggestion(suggestion_id: int) -> None:
    raise HTTPException(status_code=501, detail="Not implemented yet (Phase 4)")


@router.post(
    "/{suggestion_id}/convert-to-catalog",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
def convert_suggestion_to_catalog(suggestion_id: int) -> None:
    """Human-reviewed conversion only — never auto-execute AI drafts."""
    raise HTTPException(status_code=501, detail="Not implemented yet (Phase 4)")

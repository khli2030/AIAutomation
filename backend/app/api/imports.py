"""Import endpoints — implemented in Phase 2."""

from fastapi import APIRouter, HTTPException, status

router = APIRouter()


@router.post("/upload", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def upload_excel() -> None:
    """POST /imports/upload — Phase 2."""
    raise HTTPException(status_code=501, detail="Not implemented yet (Phase 2)")


@router.get("/{batch_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def get_import_batch(batch_id: int) -> None:
    """GET /imports/{batch_id} — Phase 2."""
    raise HTTPException(status_code=501, detail="Not implemented yet (Phase 2)")


@router.get("/{batch_id}/records", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def list_import_records(batch_id: int) -> None:
    """GET /imports/{batch_id}/records — Phase 2/3."""
    raise HTTPException(status_code=501, detail="Not implemented yet (Phase 2)")


@router.post("/{batch_id}/generate-plan", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def generate_plan(batch_id: int) -> None:
    """POST /imports/{batch_id}/generate-plan — Phase 5."""
    raise HTTPException(status_code=501, detail="Not implemented yet (Phase 5)")

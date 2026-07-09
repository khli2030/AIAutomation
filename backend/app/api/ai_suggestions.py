"""AI suggestion review endpoints — Phase 4.

AI-generated playbooks are never executed automatically.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import (
    ADMIN_ONLY,
    APPROVER_ROLES,
    AuthContext,
    READ_ROLES,
    require_roles,
)
from app.db.session import get_db
from app.schemas.ai_suggestions import (
    AISuggestionListResponse,
    AISuggestionResponse,
    ConvertToCatalogRequest,
    ConvertToCatalogResponse,
    ReviewActionRequest,
)
from app.services.ai_suggestions import AISuggestionError, AISuggestionService

router = APIRouter()


@router.get("/", response_model=AISuggestionListResponse)
@router.get("", response_model=AISuggestionListResponse, include_in_schema=False)
def list_ai_suggestions(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    auth: AuthContext = require_roles(*READ_ROLES),
) -> AISuggestionListResponse:
    """GET /ai-suggestions — list draft/review suggestions (never executable)."""
    items, total = AISuggestionService(db).list_suggestions(
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return AISuggestionListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[AISuggestionResponse.model_validate(row) for row in items],
    )


@router.get("/{suggestion_id}", response_model=AISuggestionResponse)
def get_ai_suggestion(
    suggestion_id: int,
    db: Session = Depends(get_db),
    auth: AuthContext = require_roles(*READ_ROLES),
) -> AISuggestionResponse:
    """GET /ai-suggestions/{suggestion_id}."""
    try:
        suggestion = AISuggestionService(db).get_suggestion(suggestion_id)
    except AISuggestionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return AISuggestionResponse.model_validate(suggestion)


@router.post("/{suggestion_id}/approve", response_model=AISuggestionResponse)
def approve_suggestion(
    suggestion_id: int,
    body: ReviewActionRequest | None = None,
    db: Session = Depends(get_db),
    auth: AuthContext = require_roles(*APPROVER_ROLES),
) -> AISuggestionResponse:
    """Approve changes suggestion status only — does not execute or add to catalog."""
    payload = body or ReviewActionRequest()
    _ = payload
    try:
        suggestion = AISuggestionService(db).approve(
            suggestion_id,
            reviewed_by=auth.actor,
            role=auth.role.value,
        )
    except AISuggestionError as exc:
        detail = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in detail.lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=detail) from exc
    return AISuggestionResponse.model_validate(suggestion)


@router.post("/{suggestion_id}/reject", response_model=AISuggestionResponse)
def reject_suggestion(
    suggestion_id: int,
    body: ReviewActionRequest | None = None,
    db: Session = Depends(get_db),
    auth: AuthContext = require_roles(*APPROVER_ROLES),
) -> AISuggestionResponse:
    """Reject changes suggestion status only — does not execute."""
    payload = body or ReviewActionRequest()
    _ = payload
    try:
        suggestion = AISuggestionService(db).reject(
            suggestion_id,
            reviewed_by=auth.actor,
            role=auth.role.value,
        )
    except AISuggestionError as exc:
        detail = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in detail.lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=detail) from exc
    return AISuggestionResponse.model_validate(suggestion)


@router.post(
    "/{suggestion_id}/convert-to-catalog",
    response_model=ConvertToCatalogResponse,
)
def convert_suggestion_to_catalog(
    suggestion_id: int,
    body: ConvertToCatalogRequest | None = None,
    db: Session = Depends(get_db),
    auth: AuthContext = require_roles(*ADMIN_ONLY),
) -> ConvertToCatalogResponse:
    """Human-reviewed conversion only — catalog entry disabled by default; never execute AI draft."""
    payload = body or ConvertToCatalogRequest()
    try:
        suggestion, catalog = AISuggestionService(db).convert_to_catalog(
            suggestion_id,
            reviewed_by=auth.actor,
            task_code=payload.task_code,
            title=payload.title,
            enable=payload.enable,
            role=auth.role.value,
        )
    except AISuggestionError as exc:
        detail = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in detail.lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=detail) from exc

    return ConvertToCatalogResponse(
        suggestion_id=suggestion.id,
        catalog_id=catalog.id,
        task_code=catalog.task_code,
        is_enabled=catalog.is_enabled,
        ansible_playbook_path=catalog.ansible_playbook_path,
    )

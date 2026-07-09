"""Audit log helper — every sensitive action should call this."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def write_audit_log(
    db: Session,
    *,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: str | int,
    details: dict[str, Any] | str | None = None,
    role: str | None = None,
    commit: bool = False,
) -> AuditLog:
    """Persist an audit event. Caller controls transaction unless commit=True.

    ``role`` is merged into details as ``auth_role`` (Phase 8A) so actor + role
    are queryable without a schema migration. Production may add a dedicated column later.
    """
    if isinstance(details, dict):
        payload: dict[str, Any] = dict(details)
    elif details is None:
        payload = {}
    else:
        payload = {"message": details}

    if role:
        payload.setdefault("auth_role", role)

    details_text: str | None = (
        json.dumps(payload, ensure_ascii=False, default=str) if payload else None
    )

    entry = AuditLog(
        actor=actor or "system",
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        details=details_text,
    )
    db.add(entry)
    if commit:
        db.commit()
        db.refresh(entry)
    return entry

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
    commit: bool = False,
) -> AuditLog:
    """Persist an audit event. Caller controls transaction unless commit=True."""
    if isinstance(details, dict):
        details_text: str | None = json.dumps(details, ensure_ascii=False, default=str)
    else:
        details_text = details

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

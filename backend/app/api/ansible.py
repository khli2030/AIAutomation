"""Ansible readiness + Phase 10A/10B pilot safety endpoints.

GET /preflight, /safety-status, /lab-config-preview never execute Ansible.
POST /connectivity-check is gated and blocked by default (ping only).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import OPERATOR_ROLES, READ_ROLES, AuthContext, require_roles
from app.config import Settings, get_settings
from app.db.session import get_db
from app.models.remediation_catalog import RemediationCatalog
from app.schemas.ansible import (
    AnsiblePreflightResponse,
    AnsibleSafetyStatusResponse,
    ConnectivityCheckRequest,
    ConnectivityCheckResponse,
    LabConfigPreviewResponse,
    PilotReadinessResponse,
    PreflightCheckResponse,
    RemediationCapabilitiesResponse,
    RemediationCapabilityItem,
)
from app.services.ansible_safety import build_preflight_report
from app.services.lab_ansible_config import (
    build_lab_config_preview,
    build_pilot_readiness,
)
from app.services.playbook_quality import (
    PHASE11A_IMPLEMENTED_TASK_CODES,
    catalog_capability_flags,
    is_stub_playbook,
)
from app.services.real_ansible_pilot import (
    RealAnsiblePilotError,
    RealAnsiblePilotService,
    build_safety_status,
)
from pathlib import Path

router = APIRouter()


def _known_task_codes(db: Session) -> list[str]:
    return list(db.scalars(select(RemediationCatalog.task_code)).all())


@router.get("/preflight", response_model=AnsiblePreflightResponse)
def ansible_preflight(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    auth: AuthContext = require_roles(*READ_ROLES),
) -> AnsiblePreflightResponse:
    """Report real-Ansible readiness without executing anything."""
    _ = auth
    enabled_paths = db.scalars(
        select(RemediationCatalog.ansible_playbook_path).where(
            RemediationCatalog.is_enabled.is_(True)
        )
    ).all()
    report = build_preflight_report(settings, enabled_catalog_paths=enabled_paths)
    payload = report.to_dict()
    return AnsiblePreflightResponse(
        mock_mode=payload["mock_mode"],
        real_ansible_enabled=payload["real_ansible_enabled"],
        app_env=payload["app_env"],
        real_ansible_allowed=payload["real_ansible_allowed"],
        checks=[PreflightCheckResponse(**c) for c in payload["checks"]],
        blockers=payload["blockers"],
        message=payload["message"],
    )


@router.get("/safety-status", response_model=AnsibleSafetyStatusResponse)
def ansible_safety_status(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    auth: AuthContext = require_roles(*READ_ROLES),
) -> AnsibleSafetyStatusResponse:
    """Phase 10A/10B safety status — configuration only, never executes Ansible."""
    _ = auth
    status_obj = build_safety_status(
        settings, known_task_codes=_known_task_codes(db)
    )
    return AnsibleSafetyStatusResponse(**status_obj.to_dict())


@router.get("/lab-config-preview", response_model=LabConfigPreviewResponse)
def ansible_lab_config_preview(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    auth: AuthContext = require_roles(*READ_ROLES),
) -> LabConfigPreviewResponse:
    """Sanitized lab pilot config preview — no secrets or private key contents."""
    _ = auth
    preview = build_lab_config_preview(
        settings, known_task_codes=_known_task_codes(db)
    )
    return LabConfigPreviewResponse(**preview.to_dict())


@router.get("/pilot-readiness", response_model=PilotReadinessResponse)
def ansible_pilot_readiness(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    auth: AuthContext = require_roles(*READ_ROLES),
) -> PilotReadinessResponse:
    """Phase 10C single-host pilot readiness — configuration only, no execution."""
    _ = auth
    readiness = build_pilot_readiness(
        settings, known_task_codes=_known_task_codes(db)
    )
    return PilotReadinessResponse(**readiness.to_dict())


@router.get(
    "/remediation-capabilities",
    response_model=RemediationCapabilitiesResponse,
)
def ansible_remediation_capabilities(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    auth: AuthContext = require_roles(*READ_ROLES),
) -> RemediationCapabilitiesResponse:
    """Phase 11A catalog capability flags (backup / validation / rollback).

    Never executes Ansible. Never returns playbook secrets or Excel/AI text.
    """
    _ = auth
    rows = list(db.scalars(select(RemediationCatalog)).all())
    playbooks_dir = Path(settings.ansible_playbooks_dir)
    items: list[RemediationCapabilityItem] = []
    for row in rows:
        rel = (row.ansible_playbook_path or "").strip()
        path = playbooks_dir / rel if rel else None
        flags = catalog_capability_flags(
            task_code=row.task_code,
            playbook_path=path if path and path.is_file() else None,
        )
        # Prefer DB seed flags when present; fall back to playbook inspection.
        supports_backup = bool(
            getattr(row, "supports_backup", False) or flags["supports_backup"]
        )
        supports_validation = bool(
            getattr(row, "supports_validation", False)
            or flags["supports_validation"]
        )
        supports_rollback = str(
            getattr(row, "supports_rollback", None)
            or flags["supports_rollback"]
            or "none"
        )
        stub = bool(flags["is_stub"])
        if path is not None and path.is_file():
            stub = is_stub_playbook(path)
        items.append(
            RemediationCapabilityItem(
                task_code=row.task_code,
                title=row.title,
                ansible_playbook_path=rel or None,
                is_enabled=bool(row.is_enabled),
                is_stub=stub,
                phase11a_implemented=bool(flags["phase11a_implemented"]),
                supports_backup=supports_backup,
                supports_validation=supports_validation,
                supports_rollback=supports_rollback,
                high_risk_blocked=bool(flags["high_risk_blocked"]),
                requires_backup=bool(row.requires_backup),
                requires_validation=bool(row.requires_validation),
            )
        )
    return RemediationCapabilitiesResponse(
        items=items,
        implemented_task_codes=sorted(PHASE11A_IMPLEMENTED_TASK_CODES),
        stub_blocked_from_real_execution=True,
        automated_rollback_available=False,
    )


@router.post("/connectivity-check", response_model=ConnectivityCheckResponse)
def ansible_connectivity_check(
    body: ConnectivityCheckRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    auth: AuthContext = require_roles(*OPERATOR_ROLES),
) -> ConnectivityCheckResponse:
    """Allowlisted host connectivity check (ping). Blocked when real Ansible is off.

    Never runs playbooks or applies changes.
    """
    service = RealAnsiblePilotService(db, settings=settings)
    try:
        result = service.connectivity_check(
            body.hosts,
            actor=auth.actor,
            role=auth.role.value,
            known_task_codes=_known_task_codes(db),
        )
    except RealAnsiblePilotError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return ConnectivityCheckResponse(
        ok=bool(result.get("ok")),
        blocked=bool(result.get("blocked")),
        hosts=list(result.get("hosts") or []),
        blocked_hosts=list(result.get("blocked_hosts") or []),
        reasons=list(result.get("reasons") or []),
        stdout=str(result.get("stdout") or ""),
        stderr=str(result.get("stderr") or ""),
        mock_mode=bool(result.get("mock_mode", True)),
        real_ansible_enabled=bool(result.get("real_ansible_enabled", False)),
        execution_backend=result.get("execution_backend"),
        module=result.get("module"),
    )

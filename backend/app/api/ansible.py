"""Ansible readiness + Phase 10A pilot safety endpoints.

GET /preflight and GET /safety-status never execute Ansible.
POST /connectivity-check is gated and blocked by default.
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
    PreflightCheckResponse,
)
from app.services.ansible_safety import build_preflight_report
from app.services.real_ansible_pilot import (
    RealAnsiblePilotError,
    RealAnsiblePilotService,
    build_safety_status,
)

router = APIRouter()


@router.get("/preflight", response_model=AnsiblePreflightResponse)
def ansible_preflight(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    auth: AuthContext = require_roles(*READ_ROLES),
) -> AnsiblePreflightResponse:
    """Report real-Ansible readiness without executing anything.

    Real Ansible remains blocked unless MOCK_MODE=false, REAL_ANSIBLE_ENABLED=true,
    and APP_ENV is lab|test. Production stays blocked in Phase 8B.
    """
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
    settings: Settings = Depends(get_settings),
    auth: AuthContext = require_roles(*READ_ROLES),
) -> AnsibleSafetyStatusResponse:
    """Phase 10A safety status — configuration only, never executes Ansible."""
    _ = auth
    status_obj = build_safety_status(settings)
    return AnsibleSafetyStatusResponse(**status_obj.to_dict())


@router.post("/connectivity-check", response_model=ConnectivityCheckResponse)
def ansible_connectivity_check(
    body: ConnectivityCheckRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    auth: AuthContext = require_roles(*OPERATOR_ROLES),
) -> ConnectivityCheckResponse:
    """Allowlisted host connectivity check (ping). Blocked when real Ansible is off."""
    service = RealAnsiblePilotService(db, settings=settings)
    try:
        result = service.connectivity_check(
            body.hosts, actor=auth.actor, role=auth.role.value
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

"""Ansible readiness endpoints — Phase 8B.

Read-only preflight. Never executes playbooks, ansible-runner, subprocess, or SSH.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import READ_ROLES, AuthContext, require_roles
from app.config import Settings, get_settings
from app.db.session import get_db
from app.models.remediation_catalog import RemediationCatalog
from app.schemas.ansible import AnsiblePreflightResponse, PreflightCheckResponse
from app.services.ansible_safety import build_preflight_report

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

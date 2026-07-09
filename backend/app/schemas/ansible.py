"""Ansible readiness schemas — Phase 8B (no execution)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PreflightCheckResponse(BaseModel):
    name: str
    ok: bool
    detail: str


class AnsiblePreflightResponse(BaseModel):
    mock_mode: bool
    real_ansible_enabled: bool
    app_env: str
    real_ansible_allowed: bool
    checks: list[PreflightCheckResponse] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    message: str

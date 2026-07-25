"""Ansible readiness + Phase 10A pilot safety schemas."""

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


class AnsibleSafetyStatusResponse(BaseModel):
    mock_mode: bool
    real_ansible_enabled: bool
    check_mode_only: bool
    allowed_hosts_count: int
    allowed_task_codes_count: int
    inventory_configured: bool
    private_key_configured: bool
    remote_user_configured: bool
    real_execution_available: bool
    reasons: list[str] = Field(default_factory=list)
    allowed_hosts: list[str] = Field(default_factory=list)
    allowed_task_codes: list[str] = Field(default_factory=list)
    timeout_seconds: int = 120


class ConnectivityCheckRequest(BaseModel):
    hosts: list[str] = Field(default_factory=list)


class ConnectivityCheckResponse(BaseModel):
    ok: bool
    blocked: bool = False
    hosts: list[str] = Field(default_factory=list)
    blocked_hosts: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    mock_mode: bool = True
    real_ansible_enabled: bool = False
    execution_backend: str | None = None
    module: str | None = None

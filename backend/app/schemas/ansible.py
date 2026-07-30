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
    pilot_mode: bool = False
    max_hosts_per_run: int = 1
    single_host_pilot_qualified: bool = False
    auth_mode: str = "explicit"
    auth_source: str = "explicit"
    execution_mode: str = "local"
    control_node_configured: bool = False
    control_node_workdir: str | None = None
    delegate_available: bool = False


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


class LabConfigPreviewResponse(BaseModel):
    """Sanitized lab pilot config — never includes secrets or key contents."""

    allowed_hosts: list[str] = Field(default_factory=list)
    allowed_task_codes: list[str] = Field(default_factory=list)
    inventory_path_configured: bool = False
    private_key_configured: bool = False
    remote_user_configured: bool = False
    timeout_seconds: int = 120
    validation_status: str
    validation_errors: list[str] = Field(default_factory=list)
    mock_mode: bool = True
    real_ansible_enabled: bool = False
    check_mode_only: bool = True
    connectivity_allowed: bool = False
    pilot_mode: bool = False
    max_hosts_per_run: int = 1
    pilot_ready: bool = False
    pilot_readiness_errors: list[str] = Field(default_factory=list)
    auth_mode: str = "explicit"
    auth_source: str = "explicit"
    execution_mode: str = "local"
    control_node_configured: bool = False
    control_node_workdir: str | None = None
    delegate_available: bool = False


class PilotReadinessResponse(BaseModel):
    ready: bool
    mock_mode: bool
    real_ansible_enabled: bool
    check_mode_only: bool
    pilot_mode: bool
    max_hosts_per_run: int
    allowed_hosts: list[str] = Field(default_factory=list)
    allowed_task_codes: list[str] = Field(default_factory=list)
    inventory_configured: bool = False
    remote_user_configured: bool = False
    private_key_configured: bool = False
    auth_mode: str = "explicit"
    auth_source: str = "explicit"
    execution_mode: str = "local"
    control_node_configured: bool = False
    control_node_workdir: str | None = None
    delegate_available: bool = False
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RemediationCapabilityItem(BaseModel):
    task_code: str
    title: str | None = None
    ansible_playbook_path: str | None = None
    is_enabled: bool = False
    is_stub: bool = True
    phase11a_implemented: bool = False
    phase11c_implemented: bool = False
    supports_backup: bool = False
    supports_validation: bool = False
    supports_rollback: str = "none"
    high_risk_blocked: bool = False
    requires_backup: bool = True
    requires_validation: bool = True


class RemediationCapabilitiesResponse(BaseModel):
    items: list[RemediationCapabilityItem] = Field(default_factory=list)
    implemented_task_codes: list[str] = Field(default_factory=list)
    stub_blocked_from_real_execution: bool = True
    automated_rollback_available: bool = False
    note: str = (
        "Phase 11A/11C implement safe catalog remediations only "
        "(SSH hardening, journald Compress, shell TMOUT, crontab/cron.daily "
        "permissions). Stub playbooks and high-risk remediations are blocked "
        "from real execution. Rollback is manual — see docs/remediation-rollback.md."
    )

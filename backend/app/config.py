"""Application settings loaded from environment variables.

Never hardcode credentials. Copy `.env.example` to `.env` for local/MVP use.
"""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.services.ansible_env_parse import (
    TIMEOUT_DEFAULT_SECONDS,
    TIMEOUT_MAX_SECONDS,
    TIMEOUT_MIN_SECONDS,
    parse_csv_allowlist,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "compliance-remediation-platform"
    app_env: str = "development"
    debug: bool = False
    secret_key: str = "change-me-in-production"

    # Phase 8A MVP role tokens (shared secrets — not production SSO).
    # At least one token must be set; ADMIN_TOKEN alone remains valid (admin role).
    viewer_token: str = ""
    operator_token: str = ""
    approver_token: str = ""
    admin_token: str = ""

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://127.0.0.1:3000,http://localhost:3000"

    database_url: str = (
        "postgresql+psycopg://compliance:compliance_change_me@db:5432/compliance"
    )

    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"

    ansible_home: str = "/opt/ansible"
    ansible_playbooks_dir: str = "/opt/ansible/playbooks"
    ansible_inventories_dir: str = "/opt/ansible/inventories"
    # Ansible env override; default True (safe).
    ansible_host_key_checking: bool = True

    # Host paths map to ./data via docker-compose volume.
    upload_dir: str = "/var/lib/compliance/uploads"
    runner_private_data_dir: str = "/var/lib/compliance/ansible_private_data"
    tmp_inventory_dir: str = "/var/lib/compliance/tmp_inventories"

    # Phase 2 default chunk size for Excel insert batches.
    excel_chunk_size: int = 1000
    job_batch_size: int = 75

    # When True, AnsibleExecutionService never calls ansible-runner or shell.
    # Use for local/dev. Real execution only on the internal Ansible control server
    # with MOCK_MODE=false (see DEPLOYMENT.md). Default True for safety.
    mock_mode: bool = True

    # Phase 8B: second gate for real Ansible. Default false — even if MOCK_MODE=false,
    # real execution stays blocked unless this is explicitly enabled for lab/test.
    real_ansible_enabled: bool = False

    # Phase 10A/10B pilot gates (safe defaults — no broad real execution).
    # Check-mode only unless explicitly disabled for a later phase.
    real_ansible_check_mode_only: bool = True
    # Comma-separated allowlists; empty means nothing is allowlisted.
    # Example: REAL_ANSIBLE_ALLOWED_HOSTS=lab-server-01,10.10.10.15
    real_ansible_allowed_hosts: str = ""
    # Example: REAL_ANSIBLE_ALLOWED_TASK_CODES=AIDE_INSTALL,SSH_MAX_AUTH_TRIES
    real_ansible_allowed_task_codes: str = ""
    # Lab pilot inventory / SSH identity (required when REAL_ANSIBLE_ENABLED=true).
    real_ansible_inventory_path: str | None = None
    real_ansible_private_key_path: str | None = None
    real_ansible_remote_user: str | None = None
    real_ansible_timeout_seconds: int = TIMEOUT_DEFAULT_SECONDS

    # AI Analyzer is interface-only until explicitly configured (mock by default).
    ai_provider: str = "mock"
    ai_enabled: bool = False
    ai_api_key: str | None = None
    ai_base_url: str | None = None
    ai_model: str | None = None

    @field_validator("real_ansible_timeout_seconds", mode="before")
    @classmethod
    def _validate_timeout_bounds(cls, value: object) -> int:
        """Clamp timeout into safe min/max; invalid values fall back to default."""
        try:
            n = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return TIMEOUT_DEFAULT_SECONDS
        if n < TIMEOUT_MIN_SECONDS:
            return TIMEOUT_MIN_SECONDS
        if n > TIMEOUT_MAX_SECONDS:
            return TIMEOUT_MAX_SECONDS
        return n

    @field_validator(
        "real_ansible_inventory_path",
        "real_ansible_private_key_path",
        "real_ansible_remote_user",
        mode="before",
    )
    @classmethod
    def _strip_optional_str(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def real_ansible_allowed_hosts_list(self) -> list[str]:
        return parse_csv_allowlist(self.real_ansible_allowed_hosts)

    @property
    def real_ansible_allowed_task_codes_list(self) -> list[str]:
        return parse_csv_allowlist(self.real_ansible_allowed_task_codes)


@lru_cache
def get_settings() -> Settings:
    return Settings()

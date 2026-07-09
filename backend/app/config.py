"""Application settings loaded from environment variables.

Never hardcode credentials. Copy `.env.example` to `.env` for local/MVP use.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # Simple shared-token guard for non-health API routes (Phase 1 hardening).
    # Set a strong value in .env — requests without this token are rejected.
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

    # AI Analyzer is interface-only until explicitly configured (mock by default).
    ai_provider: str = "mock"
    ai_enabled: bool = False
    ai_api_key: str | None = None
    ai_base_url: str | None = None
    ai_model: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

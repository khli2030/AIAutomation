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

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:3000"

    database_url: str = (
        "postgresql+psycopg://compliance:compliance_change_me@db:5432/compliance"
    )

    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"

    ansible_home: str = "/opt/ansible"
    ansible_playbooks_dir: str = "/opt/ansible/playbooks"
    ansible_inventories_dir: str = "/opt/ansible/inventories"
    upload_dir: str = "/var/lib/compliance/uploads"
    runner_private_data_dir: str = "/var/lib/compliance/ansible_private_data"
    tmp_inventory_dir: str = "/var/lib/compliance/tmp_inventories"

    excel_chunk_size: int = 500
    job_batch_size: int = 75

    # AI Analyzer is interface-only until explicitly configured.
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

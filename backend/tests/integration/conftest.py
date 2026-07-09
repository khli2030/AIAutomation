"""Integration / E2E fixtures — SQLite + TestClient, MOCK_MODE=true.

No Redis/Celery broker, no ansible-runner, no subprocess Ansible, no SSH.
Parse is invoked synchronously by patching Celery .delay.
"""

from __future__ import annotations

import sys
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure mock path stays clean if other tests imported the real adapter.
sys.modules.pop("app.services.real_ansible_runner", None)

from app.config import Settings, get_settings  # noqa: E402
from app.db.seed_assets import seed_test_assets  # noqa: E402
from app.db.seed_remediation_catalog import seed_remediation_catalog  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
from app.workers.tasks_import import parse_excel_batch  # noqa: E402

ADMIN_TOKEN = "e2e-admin-token-phase65"


@pytest.fixture()
def e2e_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[dict, None, None]:
    """Isolated SQLite DB + upload dir with MOCK_MODE=true and admin token."""
    db_path = tmp_path / "e2e.sqlite"
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        f"sqlite+pysqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(
        bind=engine, autocommit=False, autoflush=False, class_=Session
    )

    settings = Settings(
        admin_token=ADMIN_TOKEN,
        mock_mode=True,
        database_url=f"sqlite+pysqlite:///{db_path}",
        upload_dir=str(upload_dir),
        ai_enabled=False,
        ai_provider="mock",
    )

    get_settings.cache_clear()

    def _settings() -> Settings:
        return settings

    # FastAPI Depends() captured get_settings at import time — override the callable.
    app.dependency_overrides[get_settings] = _settings
    monkeypatch.setattr("app.config.get_settings", _settings)
    monkeypatch.setattr("app.main.settings", settings)
    monkeypatch.setattr("app.auth.get_settings", _settings)
    monkeypatch.setattr("app.services.ansible_execution.get_settings", _settings)
    monkeypatch.setattr("app.workers.tasks_import.get_settings", _settings)
    monkeypatch.setattr("app.workers.tasks_import.SessionLocal", TestingSessionLocal)
    monkeypatch.setattr("app.db.session.SessionLocal", TestingSessionLocal)

    def _sync_parse(batch_id: int) -> dict:
        # Celery task with bind=True — .run() executes body without broker.
        return parse_excel_batch.run(batch_id)

    monkeypatch.setattr("app.api.imports.parse_excel_batch.delay", _sync_parse)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    from app.db.session import get_db

    app.dependency_overrides[get_db] = override_get_db

    # Seed catalog (enabled SSH_DISABLE_ROOT_LOGIN) + test assets.
    db = TestingSessionLocal()
    try:
        seed_remediation_catalog(db)
        seed_test_assets(db)
    finally:
        db.close()

    yield {
        "settings": settings,
        "admin_token": ADMIN_TOKEN,
        "upload_dir": upload_dir,
        "session_factory": TestingSessionLocal,
        "engine": engine,
    }

    app.dependency_overrides.clear()
    get_settings.cache_clear()
    sys.modules.pop("app.services.real_ansible_runner", None)


@pytest.fixture()
def e2e_client(e2e_env: dict) -> Generator[TestClient, None, None]:
    with TestClient(app) as client:
        yield client


@pytest.fixture()
def auth_headers(e2e_env: dict) -> dict[str, str]:
    return {"X-Admin-Token": e2e_env["admin_token"]}

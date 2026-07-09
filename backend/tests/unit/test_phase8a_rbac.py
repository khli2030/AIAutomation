"""Phase 8A RBAC unit tests — role tokens, gates, audit role, no Ansible."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.auth import (
    ADMIN_ONLY,
    APPROVER_ROLES,
    AuthContext,
    OPERATOR_ROLES,
    READ_ROLES,
    Role,
    require_roles,
    resolve_token,
)
from app.config import Settings, get_settings
from app.services.audit import write_audit_log

FORBIDDEN = {"ansible_runner", "subprocess", "paramiko", "fabric", "invoke"}


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _settings(**kwargs: object) -> Settings:
    defaults = {
        "admin_token": "tok-admin",
        "viewer_token": "tok-viewer",
        "operator_token": "tok-operator",
        "approver_token": "tok-approver",
        "mock_mode": True,
        "database_url": "postgresql+psycopg://x:x@localhost/x",
    }
    defaults.update(kwargs)
    return Settings(**defaults)  # type: ignore[arg-type]


def test_resolve_token_maps_each_role() -> None:
    settings = _settings()
    assert resolve_token(x_admin_token="tok-viewer", settings=settings).role == Role.VIEWER
    assert resolve_token(x_admin_token="tok-operator", settings=settings).role == Role.OPERATOR
    assert resolve_token(x_admin_token="tok-approver", settings=settings).role == Role.APPROVER
    assert resolve_token(x_admin_token="tok-admin", settings=settings).role == Role.ADMIN


def test_resolve_token_bearer_and_invalid() -> None:
    settings = _settings()
    ctx = resolve_token(authorization="Bearer tok-operator", settings=settings)
    assert ctx.role == Role.OPERATOR
    assert ctx.actor == "role:operator"
    with pytest.raises(Exception) as exc:
        resolve_token(x_admin_token="wrong", settings=settings)
    assert exc.value.status_code == 401  # type: ignore[attr-defined]


def test_resolve_token_no_tokens_configured() -> None:
    settings = _settings(
        admin_token="",
        viewer_token="",
        operator_token="",
        approver_token="",
    )
    with pytest.raises(Exception) as exc:
        resolve_token(x_admin_token="anything", settings=settings)
    assert exc.value.status_code == 503  # type: ignore[attr-defined]


def test_admin_token_alone_still_works() -> None:
    settings = _settings(
        admin_token="only-admin",
        viewer_token="",
        operator_token="",
        approver_token="",
    )
    ctx = resolve_token(x_admin_token="only-admin", settings=settings)
    assert ctx.role == Role.ADMIN


def _app_with_gates() -> TestClient:
    app = FastAPI()

    @app.middleware("http")
    async def inject_auth(request: Request, call_next):  # type: ignore[no-untyped-def]
        # Simulate middleware: resolve from header using test settings
        settings = _settings()
        try:
            request.state.auth = resolve_token(
                x_admin_token=request.headers.get("X-Admin-Token"),
                settings=settings,
            )
        except Exception as exc:  # noqa: BLE001
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=getattr(exc, "status_code", 401),
                content={"detail": getattr(exc, "detail", str(exc))},
            )
        return await call_next(request)

    @app.get("/read")
    def read_ep(auth: AuthContext = require_roles(*READ_ROLES)) -> dict:
        return {"role": auth.role.value}

    @app.post("/upload")
    def upload_ep(auth: AuthContext = require_roles(*OPERATOR_ROLES)) -> dict:
        return {"ok": True, "actor": auth.actor}

    @app.post("/validate")
    def validate_ep(auth: AuthContext = require_roles(*OPERATOR_ROLES)) -> dict:
        return {"ok": True}

    @app.post("/generate-plan")
    def plan_ep(auth: AuthContext = require_roles(*OPERATOR_ROLES)) -> dict:
        return {"ok": True}

    @app.post("/approve")
    def approve_ep(auth: AuthContext = require_roles(*APPROVER_ROLES)) -> dict:
        return {"ok": True}

    @app.post("/reject")
    def reject_ep(auth: AuthContext = require_roles(*APPROVER_ROLES)) -> dict:
        return {"ok": True}

    @app.post("/convert")
    def convert_ep(auth: AuthContext = require_roles(*ADMIN_ONLY)) -> dict:
        return {"ok": True}

    @app.post("/dry-run")
    def dry_run_ep(auth: AuthContext = require_roles(*OPERATOR_ROLES)) -> dict:
        return {"ok": True}

    @app.post("/run")
    def run_ep(auth: AuthContext = require_roles(*OPERATOR_ROLES)) -> dict:
        return {"ok": True}

    return TestClient(app)


def test_viewer_can_read_but_not_mutate() -> None:
    client = _app_with_gates()
    h = {"X-Admin-Token": "tok-viewer"}
    assert client.get("/read", headers=h).status_code == 200
    assert client.post("/upload", headers=h).status_code == 403
    assert client.post("/validate", headers=h).status_code == 403
    assert client.post("/generate-plan", headers=h).status_code == 403
    assert client.post("/approve", headers=h).status_code == 403
    assert client.post("/reject", headers=h).status_code == 403
    assert client.post("/dry-run", headers=h).status_code == 403
    assert client.post("/run", headers=h).status_code == 403
    assert client.post("/convert", headers=h).status_code == 403


def test_operator_can_operate_but_not_approve_or_convert() -> None:
    client = _app_with_gates()
    h = {"X-Admin-Token": "tok-operator"}
    assert client.get("/read", headers=h).status_code == 200
    assert client.post("/upload", headers=h).status_code == 200
    assert client.post("/validate", headers=h).status_code == 200
    assert client.post("/generate-plan", headers=h).status_code == 200
    assert client.post("/dry-run", headers=h).status_code == 200
    assert client.post("/run", headers=h).status_code == 200
    assert client.post("/approve", headers=h).status_code == 403
    assert client.post("/reject", headers=h).status_code == 403
    assert client.post("/convert", headers=h).status_code == 403


def test_approver_can_approve_but_not_operate_or_convert() -> None:
    client = _app_with_gates()
    h = {"X-Admin-Token": "tok-approver"}
    assert client.get("/read", headers=h).status_code == 200
    assert client.post("/approve", headers=h).status_code == 200
    assert client.post("/reject", headers=h).status_code == 200
    assert client.post("/upload", headers=h).status_code == 403
    assert client.post("/validate", headers=h).status_code == 403
    assert client.post("/generate-plan", headers=h).status_code == 403
    assert client.post("/dry-run", headers=h).status_code == 403
    assert client.post("/run", headers=h).status_code == 403
    assert client.post("/convert", headers=h).status_code == 403


def test_admin_can_do_everything_including_convert() -> None:
    client = _app_with_gates()
    h = {"X-Admin-Token": "tok-admin"}
    assert client.get("/read", headers=h).status_code == 200
    assert client.post("/upload", headers=h).status_code == 200
    assert client.post("/validate", headers=h).status_code == 200
    assert client.post("/generate-plan", headers=h).status_code == 200
    assert client.post("/approve", headers=h).status_code == 200
    assert client.post("/reject", headers=h).status_code == 200
    assert client.post("/dry-run", headers=h).status_code == 200
    assert client.post("/run", headers=h).status_code == 200
    assert client.post("/convert", headers=h).status_code == 200


def test_audit_log_stores_actor_and_role() -> None:
    db = MagicMock()
    entry = write_audit_log(
        db,
        actor="role:operator",
        action="upload",
        entity_type="import_batch",
        entity_id=1,
        role="operator",
        details={"event": "upload"},
    )
    assert entry.actor == "role:operator"
    payload = json.loads(entry.details or "{}")
    assert payload["auth_role"] == "operator"
    assert payload["event"] == "upload"
    assert db.add.called


def test_auth_modules_do_not_import_forbidden_execution_libs() -> None:
    root = Path(__file__).resolve().parents[2] / "app"
    for rel in ("auth.py", "main.py", "services/audit.py"):
        tree = ast.parse((root / rel).read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert not (imported & FORBIDDEN), f"{rel} imports {imported & FORBIDDEN}"


def test_job_approval_audit_includes_role() -> None:
    from app.constants.job_status import JobStatus
    from app.services.job_approval import JobApprovalService

    db = MagicMock()
    job = SimpleNamespace(
        id=7,
        status=JobStatus.DRY_RUN_SUCCESS.value,
        task_code="SSH_DISABLE_ROOT_LOGIN",
        plan_id=3,
        approved_by=None,
        approved_at=None,
    )
    db.get.return_value = job
    JobApprovalService(db).approve(7, reviewed_by="role:approver", role="approver")
    # write_audit_log was called via real function — inspect db.add AuditLog
    assert job.status == JobStatus.APPROVED.value
    assert job.approved_by == "role:approver"
    assert db.add.called
    audit_obj = db.add.call_args[0][0]
    details = json.loads(audit_obj.details)
    assert details["auth_role"] == "approver"

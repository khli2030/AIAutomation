"""Auth helper tests (Phase 1 + Phase 8A token resolution)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.auth import Role, _extract_token, require_admin_token, resolve_token
from app.config import Settings, get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_extract_token_headers() -> None:
    assert _extract_token(x_admin_token="  abc  ", authorization=None) == "abc"
    assert (
        _extract_token(x_admin_token=None, authorization="Bearer tok-1") == "tok-1"
    )
    assert _extract_token(x_admin_token=None, authorization="Basic x") is None


def test_require_admin_token_missing_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.auth.get_settings",
        lambda: Settings(
            admin_token="",
            viewer_token="",
            operator_token="",
            approver_token="",
            database_url="postgresql+psycopg://x:x@localhost/x",
        ),
    )
    with pytest.raises(HTTPException) as exc:
        require_admin_token(x_admin_token="anything", authorization=None)
    assert exc.value.status_code == 503


def test_require_admin_token_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.auth.get_settings",
        lambda: Settings(
            admin_token="secret-token",
            viewer_token="",
            operator_token="",
            approver_token="",
            database_url="postgresql+psycopg://x:x@localhost/x",
        ),
    )
    ctx = require_admin_token(x_admin_token="secret-token", authorization=None)
    assert ctx.role == Role.ADMIN
    ctx2 = require_admin_token(
        x_admin_token=None, authorization="Bearer secret-token"
    )
    assert ctx2.role == Role.ADMIN


def test_require_admin_token_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.auth.get_settings",
        lambda: Settings(
            admin_token="secret-token",
            database_url="postgresql+psycopg://x:x@localhost/x",
        ),
    )
    with pytest.raises(HTTPException) as exc:
        require_admin_token(x_admin_token="wrong", authorization=None)
    assert exc.value.status_code == 401


def test_resolve_role_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.auth.get_settings",
        lambda: Settings(
            admin_token="a",
            viewer_token="v",
            operator_token="o",
            approver_token="p",
            database_url="postgresql+psycopg://x:x@localhost/x",
        ),
    )
    assert resolve_token(x_admin_token="v").role == Role.VIEWER
    assert resolve_token(x_admin_token="o").role == Role.OPERATOR
    assert resolve_token(x_admin_token="p").role == Role.APPROVER
    assert resolve_token(x_admin_token="a").role == Role.ADMIN

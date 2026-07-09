"""Unit tests for ADMIN_TOKEN auth helper (Phase 1 hardening)."""

from __future__ import annotations

import os

import pytest
from fastapi import HTTPException

from app.auth import _extract_token, require_admin_token
from app.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_extract_token_headers() -> None:
    assert _extract_token(x_admin_token=" abc ", authorization=None) == "abc"
    assert _extract_token(x_admin_token=None, authorization="Bearer tok") == "tok"
    assert _extract_token(x_admin_token=None, authorization="Basic x") is None


def test_require_admin_token_missing_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_TOKEN", "")
    get_settings.cache_clear()
    with pytest.raises(HTTPException) as exc:
        require_admin_token(x_admin_token="anything", authorization=None)
    assert exc.value.status_code == 503


def test_require_admin_token_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_TOKEN", "secret-token")
    get_settings.cache_clear()
    require_admin_token(x_admin_token="secret-token", authorization=None)
    require_admin_token(x_admin_token=None, authorization="Bearer secret-token")


def test_require_admin_token_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_TOKEN", "secret-token")
    get_settings.cache_clear()
    with pytest.raises(HTTPException) as exc:
        require_admin_token(x_admin_token="nope", authorization=None)
    assert exc.value.status_code == 401

"""Admin token authentication for non-health API routes.

Phase 1 hardening: a single shared ADMIN_TOKEN from the environment.
This is not a full RBAC system — production needs stronger auth + TLS.
"""

from __future__ import annotations

import hmac
import secrets

from fastapi import Header, HTTPException, status

from app.config import get_settings


def require_admin_token(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    authorization: str | None = Header(default=None),
) -> None:
    """Require ADMIN_TOKEN via X-Admin-Token or Authorization: Bearer."""
    settings = get_settings()
    expected = (settings.admin_token or "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "ADMIN_TOKEN is not configured. "
                "Set a strong ADMIN_TOKEN in the environment before using the API."
            ),
        )

    provided = _extract_token(x_admin_token=x_admin_token, authorization=authorization)
    if provided is None or not hmac.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _extract_token(
    *,
    x_admin_token: str | None,
    authorization: str | None,
) -> str | None:
    if x_admin_token and x_admin_token.strip():
        return x_admin_token.strip()
    if authorization:
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
            return parts[1].strip()
    return None


def generate_admin_token_hint() -> str:
    """Helper for operators generating a token offline (not used at runtime)."""
    return secrets.token_urlsafe(32)

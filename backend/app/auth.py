"""MVP role-based token authentication (Phase 8A).

Tokens are shared secrets from the environment — not production SSO/OIDC.
Never hardcode tokens. Keep MOCK_MODE=true; this module never calls Ansible.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from enum import StrEnum

from fastapi import Depends, Header, HTTPException, Request, status

from app.config import Settings, get_settings


class Role(StrEnum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    APPROVER = "approver"
    ADMIN = "admin"


# Inclusive hierarchy: higher roles satisfy lower requirements.
ROLE_RANK: dict[Role, int] = {
    Role.VIEWER: 1,
    Role.OPERATOR: 2,
    Role.APPROVER: 3,
    Role.ADMIN: 4,
}


@dataclass(frozen=True)
class AuthContext:
    """Resolved identity for the current request."""

    role: Role
    actor: str
    token_name: str

    def allows(self, *required: Role) -> bool:
        """True if this role meets any of the required roles (hierarchy-aware).

        viewer ⊂ operator ⊂ approver ⊂ admin for *read* convenience is NOT used.
        Instead each endpoint lists exact allowed roles. Admin is always included
        by callers. This helper checks membership in the allowed set.
        """
        return self.role in required


@dataclass(frozen=True)
class _TokenBinding:
    role: Role
    env_name: str
    value: str


def _extract_token(
    *,
    x_admin_token: str | None,
    authorization: str | None,
) -> str | None:
    """Prefer X-Admin-Token (legacy header name); else Authorization: Bearer."""
    if x_admin_token and x_admin_token.strip():
        return x_admin_token.strip()
    if authorization:
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
            return parts[1].strip()
    return None


def _configured_tokens(settings: Settings) -> list[_TokenBinding]:
    """Build token→role map. Empty values are skipped (role disabled)."""
    candidates = [
        (Role.VIEWER, "VIEWER_TOKEN", settings.viewer_token),
        (Role.OPERATOR, "OPERATOR_TOKEN", settings.operator_token),
        (Role.APPROVER, "APPROVER_TOKEN", settings.approver_token),
        (Role.ADMIN, "ADMIN_TOKEN", settings.admin_token),
    ]
    out: list[_TokenBinding] = []
    for role, env_name, raw in candidates:
        value = (raw or "").strip()
        if value:
            out.append(_TokenBinding(role=role, env_name=env_name, value=value))
    return out


def resolve_token(
    *,
    x_admin_token: str | None = None,
    authorization: str | None = None,
    settings: Settings | None = None,
) -> AuthContext:
    """Resolve a request token to AuthContext or raise 401/503."""
    cfg = settings or get_settings()
    bindings = _configured_tokens(cfg)
    if not bindings:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "No API tokens configured. Set at least ADMIN_TOKEN "
                "(and optionally VIEWER_TOKEN, OPERATOR_TOKEN, APPROVER_TOKEN)."
            ),
        )

    provided = _extract_token(
        x_admin_token=x_admin_token,
        authorization=authorization,
    )
    if provided is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    for binding in bindings:
        if hmac.compare_digest(provided, binding.value):
            return AuthContext(
                role=binding.role,
                actor=f"role:{binding.role.value}",
                token_name=binding.env_name,
            )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_admin_token(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    authorization: str | None = Header(default=None),
) -> AuthContext:
    """Backward-compatible auth entrypoint used by middleware (any valid role)."""
    return resolve_token(
        x_admin_token=x_admin_token,
        authorization=authorization,
    )


def get_auth_context(request: Request) -> AuthContext:
    """Read AuthContext set by middleware; 401 if missing."""
    auth = getattr(request.state, "auth", None)
    if auth is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return auth


def require_roles(*allowed: Role):
    """FastAPI dependency: require one of the listed roles (admin must be listed)."""

    allowed_set = frozenset(allowed)

    def _dependency(request: Request) -> AuthContext:
        auth = get_auth_context(request)
        if auth.role not in allowed_set:
            names = ", ".join(sorted(r.value for r in allowed_set))
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient role. Requires one of: {names}",
            )
        return auth

    return Depends(_dependency)


# Convenience role sets matching Phase 8A rules.
READ_ROLES = (Role.VIEWER, Role.OPERATOR, Role.APPROVER, Role.ADMIN)
OPERATOR_ROLES = (Role.OPERATOR, Role.ADMIN)
APPROVER_ROLES = (Role.APPROVER, Role.ADMIN)
ADMIN_ONLY = (Role.ADMIN,)


def generate_admin_token_hint() -> str:
    """Helper for operators generating a token offline (not used at runtime)."""
    import secrets

    return secrets.token_urlsafe(32)

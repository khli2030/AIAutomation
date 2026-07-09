"""FastAPI application entrypoint (Phase 1 + Phase 8A RBAC hardening)."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.router import api_router
from app.auth import AuthContext, Role, resolve_token
from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description=(
        "Internal Linux Compliance Remediation Platform. "
        "Excel Remediation text is never executed; only approved Ansible playbooks run. "
        "Only /health is public; other endpoints require a role token "
        "(VIEWER_TOKEN / OPERATOR_TOKEN / APPROVER_TOKEN / ADMIN_TOKEN) "
        "via header X-Admin-Token or Authorization: Bearer. "
        "MVP shared-token auth — not production SSO."
    ),
    version="0.1.0",
    debug=settings.debug,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RoleTokenMiddleware(BaseHTTPMiddleware):
    """Authenticate all paths except /health; attach AuthContext to request.state."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        path = request.url.path.rstrip("/") or "/"
        if path == "/health":
            return await call_next(request)

        try:
            auth = resolve_token(
                x_admin_token=request.headers.get("X-Admin-Token"),
                authorization=request.headers.get("Authorization"),
            )
        except HTTPException as exc:
            return Response(
                content=json.dumps({"detail": exc.detail}),
                status_code=exc.status_code,
                media_type="application/json",
                headers=dict(exc.headers or {}),
            )
        request.state.auth = auth
        return await call_next(request)


app.add_middleware(RoleTokenMiddleware)

app.include_router(api_router)

# Top-level needs-review route (protected by middleware).
needs_review_router = APIRouter()


@needs_review_router.get("/needs-review")
def needs_review() -> dict[str, str]:
    """Convenience pointer — use GET /ai-suggestions?status=draft for Phase 4 reviews."""
    return {
        "detail": "Use GET /ai-suggestions (optional ?status=draft) for AI suggestion review.",
        "list_path": "/ai-suggestions",
    }


app.include_router(needs_review_router)


@app.get("/")
def root(request: Request) -> dict[str, str]:
    auth: AuthContext | None = getattr(request.state, "auth", None)
    return {
        "app": settings.app_name,
        "env": settings.app_env,
        "docs": "/docs",
        "phase": "8c",
        "auth": "MVP role tokens (VIEWER/OPERATOR/APPROVER/ADMIN) — not production SSO",
        "mock_mode": str(settings.mock_mode).lower(),
        "real_ansible_enabled": str(settings.real_ansible_enabled).lower(),
        "role": auth.role.value if auth else "",
        "actor": auth.actor if auth else "",
    }


@app.get("/auth/me")
def auth_me(request: Request) -> dict[str, str | bool]:
    """Return resolved role for the current token (Phase 8A)."""
    auth: AuthContext | None = getattr(request.state, "auth", None)
    if auth is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return {
        "role": auth.role.value,
        "actor": auth.actor,
        "token_name": auth.token_name,
        "mock_mode": bool(settings.mock_mode),
        "mvp_auth_warning": (
            "Shared role tokens in env/sessionStorage are MVP-only — "
            "not production authentication."
        ),
        "can_upload": auth.role in {Role.OPERATOR, Role.ADMIN},
        "can_validate": auth.role in {Role.OPERATOR, Role.ADMIN},
        "can_generate_plan": auth.role in {Role.OPERATOR, Role.ADMIN},
        "can_dry_run": auth.role in {Role.OPERATOR, Role.ADMIN},
        "can_run": auth.role in {Role.OPERATOR, Role.ADMIN},
        "can_approve_job": auth.role in {Role.APPROVER, Role.ADMIN},
        "can_reject_job": auth.role in {Role.APPROVER, Role.ADMIN},
        "can_approve_suggestion": auth.role in {Role.APPROVER, Role.ADMIN},
        "can_reject_suggestion": auth.role in {Role.APPROVER, Role.ADMIN},
        "can_convert_catalog": auth.role == Role.ADMIN,
        "can_ai_analyze": auth.role in {Role.OPERATOR, Role.ADMIN},
    }

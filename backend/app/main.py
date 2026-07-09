"""FastAPI application entrypoint (Phase 1 + security hardening)."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.router import api_router
from app.auth import require_admin_token
from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description=(
        "Internal Linux Compliance Remediation Platform. "
        "Excel Remediation text is never executed; only approved Ansible playbooks run. "
        "Only /health is public; all other endpoints require ADMIN_TOKEN "
        "(header X-Admin-Token or Authorization: Bearer)."
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


class AdminTokenMiddleware(BaseHTTPMiddleware):
    """Reject unauthenticated requests to all paths except /health."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        path = request.url.path.rstrip("/") or "/"
        if path == "/health":
            return await call_next(request)

        try:
            require_admin_token(
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
        return await call_next(request)


app.add_middleware(AdminTokenMiddleware)

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
def root() -> dict[str, str]:
    return {
        "app": settings.app_name,
        "env": settings.app_env,
        "docs": "/docs",
        "phase": "5",
        "auth": "ADMIN_TOKEN required for non-health endpoints",
        "mock_mode": str(settings.mock_mode).lower(),
    }

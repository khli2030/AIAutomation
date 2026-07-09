"""FastAPI application entrypoint."""

from fastapi import APIRouter, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description=(
        "Internal Linux Compliance Remediation Platform. "
        "Excel Remediation text is never executed; only approved Ansible playbooks run."
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

app.include_router(api_router)

# Top-level needs-review route as specified in the API list.
needs_review_router = APIRouter()


@needs_review_router.get("/needs-review", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def needs_review() -> None:
    raise HTTPException(status_code=501, detail="Not implemented yet (Phase 3/4)")


app.include_router(needs_review_router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "app": settings.app_name,
        "env": settings.app_env,
        "docs": "/docs",
        "phase": "2",
    }

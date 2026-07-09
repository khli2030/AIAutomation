"""API router aggregation — endpoint implementations land in later phases."""

from fastapi import APIRouter

from app.api import (
    ai_suggestions,
    ansible,
    dashboard,
    execution_jobs,
    execution_plans,
    health,
    imports,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(imports.router, prefix="/imports", tags=["imports"])
api_router.include_router(
    execution_plans.router, prefix="/execution-plans", tags=["execution-plans"]
)
api_router.include_router(
    execution_jobs.router, prefix="/execution-jobs", tags=["execution-jobs"]
)
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(
    ai_suggestions.router, prefix="/ai-suggestions", tags=["ai-suggestions"]
)
api_router.include_router(ansible.router, prefix="/ansible", tags=["ansible"])


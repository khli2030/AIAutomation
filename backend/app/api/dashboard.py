"""Dashboard and needs-review endpoints — Phase 7 UI support."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import READ_ROLES, AuthContext, require_roles
from app.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.dashboard import DashboardSummaryResponse
from app.services.dashboard import DashboardService

router = APIRouter()


@router.get("/summary", response_model=DashboardSummaryResponse)
def dashboard_summary(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    auth: AuthContext = require_roles(*READ_ROLES),
) -> DashboardSummaryResponse:
    """Aggregated import / record / job counters for the operator dashboard.

    Read-only. Never calls Ansible, MOCK execution, subprocess, or SSH.
    """
    return DashboardService(db, settings=settings).summary()

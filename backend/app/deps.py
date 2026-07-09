"""Shared FastAPI dependencies."""

from collections.abc import Generator

from sqlalchemy.orm import Session

from app.auth import require_admin_token
from app.db.session import get_db

__all__ = ["get_db", "require_admin_token", "Session", "Generator"]

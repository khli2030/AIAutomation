"""Shared FastAPI dependencies."""

from collections.abc import Generator

from sqlalchemy.orm import Session

from app.auth import (
    AuthContext,
    Role,
    get_auth_context,
    require_admin_token,
    require_roles,
)
from app.db.session import get_db

__all__ = [
    "get_db",
    "require_admin_token",
    "require_roles",
    "get_auth_context",
    "AuthContext",
    "Role",
    "Session",
    "Generator",
]

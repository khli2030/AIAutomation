"""Execution plan lifecycle statuses (Phase 5)."""

from enum import StrEnum


class PlanStatus(StrEnum):
    DRAFT = "draft"
    GENERATED = "generated"
    EMPTY = "empty"

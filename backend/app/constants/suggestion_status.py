"""AI remediation suggestion lifecycle statuses (Phase 4).

Suggestions are never executable. Only approved catalog playbooks may run.
"""

from enum import StrEnum


class SuggestionStatus(StrEnum):
    DRAFT = "draft"
    NEEDS_REVIEW = "needs_review"
    READY_FOR_REVIEW = "ready_for_review"
    UNSUPPORTED_CONTROL = "unsupported_control"
    APPROVED = "approved"
    REJECTED = "rejected"
    CONVERTED = "converted"


# Statuses allowed when AI first persists a suggestion (never approved/converted).
AI_DEFAULT_STATUSES: frozenset[str] = frozenset(
    {
        SuggestionStatus.DRAFT.value,
        SuggestionStatus.NEEDS_REVIEW.value,
    }
)

# Statuses that may be converted into remediation_catalog (human-approved only).
CONVERTIBLE_STATUSES: frozenset[str] = frozenset(
    {
        SuggestionStatus.APPROVED.value,
    }
)

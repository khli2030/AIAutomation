"""Job result type: dry_run vs run (Phase 6)."""

from enum import StrEnum


class JobResultType(StrEnum):
    DRY_RUN = "dry_run"
    RUN = "run"

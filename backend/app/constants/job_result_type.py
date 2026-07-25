"""Job result type: dry_run vs run (Phase 6) + real_dry_run (Phase 10A)."""

from enum import StrEnum


class JobResultType(StrEnum):
    DRY_RUN = "dry_run"
    RUN = "run"
    REAL_DRY_RUN = "real_dry_run"

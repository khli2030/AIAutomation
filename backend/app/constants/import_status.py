"""Import batch lifecycle statuses (Phase 2)."""

from enum import StrEnum


class ImportBatchStatus(StrEnum):
    UPLOADED = "uploaded"
    PARSING = "parsing"
    PARSED = "parsed"
    # Any parse failure (including missing columns) ends as failed.
    FAILED = "failed"
    # Kept as alias for older callers/tests; value is still "failed".
    PARSE_FAILED = "failed"
    COLUMNS_INVALID = "failed"

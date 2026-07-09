"""Import batch lifecycle statuses (Phase 2)."""

from enum import StrEnum


class ImportBatchStatus(StrEnum):
    UPLOADED = "uploaded"
    PARSING = "parsing"
    PARSED = "parsed"
    PARSE_FAILED = "parse_failed"
    COLUMNS_INVALID = "columns_invalid"

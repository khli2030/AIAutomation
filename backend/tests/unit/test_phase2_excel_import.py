"""Phase 2 tests: Excel upload, column validation, chunked parse, batch status."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from openpyxl import Workbook

from app.constants.excel_columns import EXCEL_REQUIRED_COLUMNS
from app.constants.import_status import ImportBatchStatus
from app.services.excel_parser import (
    ExcelColumnError,
    iter_excel_rows,
    validate_headers,
)
from app.services.import_persist import insert_parsed_chunk
from app.services.import_service import ImportUploadError, _safe_filename, validate_upload_file


def test_validate_headers_ok() -> None:
    mapping = validate_headers(list(EXCEL_REQUIRED_COLUMNS))
    assert mapping[list(EXCEL_REQUIRED_COLUMNS).index("Device Name")] == "device_name"
    assert mapping[list(EXCEL_REQUIRED_COLUMNS).index("Remediation")] == "remediation"


def test_missing_required_columns() -> None:
    headers = list(EXCEL_REQUIRED_COLUMNS)[:-2]
    with pytest.raises(ExcelColumnError) as exc:
        validate_headers(headers)
    assert "Remediation" in str(exc.value) or "Expected Configuration" in str(exc.value)


def test_invalid_file_extension() -> None:
    file = SimpleNamespace(filename="report.csv", content_type="text/csv")
    with pytest.raises(ImportUploadError) as exc:
        validate_upload_file(file)  # type: ignore[arg-type]
    assert ".xlsx" in str(exc.value)


def test_safe_filename() -> None:
    assert _safe_filename("../../etc/passwd.xlsx") == "passwd.xlsx"
    assert _safe_filename("noext") == "noext.xlsx"


def _write_xlsx(path: Path, rows: list[list[object]], headers: list[str] | None = None) -> None:
    wb = Workbook()
    ws = wb.active
    ws.append(headers or list(EXCEL_REQUIRED_COLUMNS))
    for row in rows:
        ws.append(row)
    wb.save(path)


def test_chunked_parsing(tmp_path: Path) -> None:
    path = tmp_path / "sample.xlsx"
    base = [""] * len(EXCEL_REQUIRED_COLUMNS)
    device_idx = list(EXCEL_REQUIRED_COLUMNS).index("Device Name")
    rem_idx = list(EXCEL_REQUIRED_COLUMNS).index("Remediation")
    status_idx = list(EXCEL_REQUIRED_COLUMNS).index("Overall Status")

    rows: list[list[object]] = []
    for i in range(5):
        row = list(base)
        row[device_idx] = f"host-{i}"
        row[rem_idx] = "Set PermitRootLogin no"  # stored only — never executed
        row[status_idx] = "Failed"
        rows.append(row)
    _write_xlsx(path, rows)

    chunks = list(iter_excel_rows(path, chunk_size=2))
    assert len(chunks) == 3
    assert sum(len(c) for c in chunks) == 5
    assert chunks[0][0].values["device_name"] == "host-0"
    assert chunks[0][0].values["remediation"] == "Set PermitRootLogin no"


def test_valid_upload_headers_and_parse(tmp_path: Path) -> None:
    path = tmp_path / "valid.xlsx"
    base = [""] * len(EXCEL_REQUIRED_COLUMNS)
    device_idx = list(EXCEL_REQUIRED_COLUMNS).index("Device Name")
    row = list(base)
    row[device_idx] = "srv-1"
    _write_xlsx(path, [row])

    chunks = list(iter_excel_rows(path, chunk_size=1000))
    assert len(chunks) == 1
    assert chunks[0][0].values["device_name"] == "srv-1"


def test_insert_chunk_counts_valid_and_invalid() -> None:
    db = MagicMock()
    from app.services.excel_parser import ParsedExcelRow

    good = ParsedExcelRow(
        row_number=2,
        values={field: None for field in __import__(
            "app.constants.excel_columns", fromlist=["EXCEL_COLUMN_MAP"]
        ).EXCEL_COLUMN_MAP.values()},
    )
    good.values["device_name"] = "host-ok"
    bad = ParsedExcelRow(
        row_number=3,
        values={field: None for field in good.values},
    )
    bad.values["device_name"] = None

    valid, invalid = insert_parsed_chunk(db, batch_id=1, chunk=[good, bad])
    assert valid == 1
    assert invalid == 1
    assert db.add_all.called


def test_batch_status_update_on_parse_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Simulate Celery parse updating batch counters/status without Redis/DB server."""
    from app.workers import tasks_import as ti

    path = tmp_path / "ok.xlsx"
    base = [""] * len(EXCEL_REQUIRED_COLUMNS)
    device_idx = list(EXCEL_REQUIRED_COLUMNS).index("Device Name")
    row = list(base)
    row[device_idx] = "host-1"
    _write_xlsx(path, [row])

    batch = SimpleNamespace(
        id=42,
        stored_path=str(path),
        status="uploaded",
        error_message=None,
        total_records=0,
        valid_records=0,
        invalid_records=0,
        total_rows=0,
        processed_rows=0,
    )

    class FakeSession:
        def get(self, model, batch_id):  # noqa: ANN001
            return batch

        def commit(self) -> None:
            return None

        def rollback(self) -> None:
            return None

        def close(self) -> None:
            return None

        def add(self, obj):  # noqa: ANN001
            return None

        def add_all(self, objs):  # noqa: ANN001
            return None

        def flush(self) -> None:
            return None

        def scalars(self, *args, **kwargs):  # noqa: ANN002, ANN003
            return MagicMock(all=lambda: [])

    monkeypatch.setattr(ti, "SessionLocal", FakeSession)
    monkeypatch.setattr(ti, "write_audit_log", lambda *a, **k: None)
    monkeypatch.setattr(
        ti,
        "insert_parsed_chunk",
        lambda db, batch_id, chunk: (len(chunk), 0),
    )

    result = ti.parse_excel_batch.run(42)
    assert result["status"] == ImportBatchStatus.PARSED.value
    assert result["total_records"] == 1
    assert result["valid_records"] == 1
    assert batch.status == ImportBatchStatus.PARSED.value
    assert batch.total_records == 1


def test_batch_status_columns_invalid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from app.workers import tasks_import as ti

    path = tmp_path / "bad.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["Device Name", "Remediation"])
    ws.append(["h1", "x"])
    wb.save(path)

    batch = SimpleNamespace(
        id=7,
        stored_path=str(path),
        status="uploaded",
        error_message=None,
        total_records=0,
        valid_records=0,
        invalid_records=0,
        total_rows=0,
        processed_rows=0,
    )

    class FakeSession:
        def get(self, model, batch_id):  # noqa: ANN001
            return batch

        def commit(self) -> None:
            return None

        def rollback(self) -> None:
            return None

        def close(self) -> None:
            return None

        def add(self, obj):  # noqa: ANN001
            return None

    monkeypatch.setattr(ti, "SessionLocal", FakeSession)
    monkeypatch.setattr(ti, "write_audit_log", lambda *a, **k: None)

    result = ti.parse_excel_batch.run(7)
    assert result["status"] == ImportBatchStatus.COLUMNS_INVALID.value
    assert batch.status == ImportBatchStatus.COLUMNS_INVALID.value
    assert "Missing required Excel columns" in (batch.error_message or "")


def test_mock_mode_unchanged() -> None:
    from app.config import Settings

    s = Settings(admin_token="t", database_url="postgresql+psycopg://x:x@localhost/x")
    assert s.mock_mode is True

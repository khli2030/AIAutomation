"""Unit tests for Excel header validation and chunked parsing."""

from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook

from app.constants.excel_columns import EXCEL_REQUIRED_COLUMNS
from app.services.excel_parser import (
    ExcelColumnError,
    cell_to_str,
    iter_excel_rows,
    validate_headers,
)
from app.services.record_hash import compute_record_hash


def test_validate_headers_ok() -> None:
    mapping = validate_headers(list(EXCEL_REQUIRED_COLUMNS))
    assert mapping[0] == "sector_name"
    assert mapping[list(EXCEL_REQUIRED_COLUMNS).index("Device Name")] == "device_name"
    assert mapping[list(EXCEL_REQUIRED_COLUMNS).index("Remediation")] == "remediation"


def test_validate_headers_missing() -> None:
    headers = list(EXCEL_REQUIRED_COLUMNS)[:-1]
    with pytest.raises(ExcelColumnError) as exc:
        validate_headers(headers)
    assert "Expected Configuration" in str(exc.value)


def test_cell_to_str_preserves_values() -> None:
    assert cell_to_str(None) is None
    assert cell_to_str("  abc  ") == "abc"
    assert cell_to_str(12345) == "12345"
    assert cell_to_str(10.0) == "10"


def test_record_hash_stable() -> None:
    h1 = compute_record_hash(
        device_name="HostA",
        qualys_control_id="123",
        source_check_id="SC-1",
        config_scan_id="CFG",
        expected_configuration="PermitRootLogin no",
    )
    h2 = compute_record_hash(
        device_name="hosta",
        qualys_control_id="123",
        source_check_id="SC-1",
        config_scan_id="CFG",
        expected_configuration="PermitRootLogin no",
    )
    assert h1 == h2
    assert len(h1) == 64


def _write_sample_xlsx(path: Path, rows: list[list[object]]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.append(list(EXCEL_REQUIRED_COLUMNS))
    for row in rows:
        ws.append(row)
    wb.save(path)


def test_iter_excel_rows_chunks(tmp_path: Path) -> None:
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

    _write_sample_xlsx(path, rows)

    chunks = list(iter_excel_rows(path, chunk_size=2))
    assert len(chunks) == 3
    assert sum(len(c) for c in chunks) == 5
    first = chunks[0][0]
    assert first.row_number == 2
    assert first.values["device_name"] == "host-0"
    assert first.values["remediation"] == "Set PermitRootLogin no"


def test_iter_excel_rows_rejects_bad_headers(tmp_path: Path) -> None:
    path = tmp_path / "bad.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["Device Name", "Remediation"])
    ws.append(["host-1", "something"])
    wb.save(path)

    with pytest.raises(ExcelColumnError):
        list(iter_excel_rows(path, chunk_size=10))

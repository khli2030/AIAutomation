"""Unit tests for upload filename safety helpers."""

from __future__ import annotations

from app.services.import_service import _safe_filename


def test_safe_filename_strips_path_and_odd_chars() -> None:
    assert _safe_filename("../../etc/passwd.xlsx") == "passwd.xlsx"
    assert _safe_filename("My Report (1).xlsx") == "My_Report_1_.xlsx"
    assert _safe_filename("noext") == "noext.xlsx"

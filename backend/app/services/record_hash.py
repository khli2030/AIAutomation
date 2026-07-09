"""Record hash helper (duplicate status marking is Phase 3)."""

from __future__ import annotations

import hashlib


def compute_record_hash(
    *,
    device_name: str | None,
    qualys_control_id: str | None,
    source_check_id: str | None,
    config_scan_id: str | None,
    expected_configuration: str | None,
) -> str:
    parts = [
        (device_name or "").strip().lower(),
        (qualys_control_id or "").strip().lower(),
        (source_check_id or "").strip().lower(),
        (config_scan_id or "").strip().lower(),
        (expected_configuration or "").strip(),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()

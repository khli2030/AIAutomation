"""Seed internal test assets for MVP / E2E mock workflow.

Assets are matched by Device Name during Phase 3 validation and Phase 5 plan
generation. environment / ansible_group come from assets only (never Excel).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.asset import Asset

# Deterministic lab hosts used by Phase 6.5 E2E mock workflow.
MVP_TEST_ASSETS: list[dict[str, object]] = [
    {
        "device_name": "e2e-linux-01",
        "ip_address": "10.20.0.11",
        "os_type": "linux",
        "environment": "test",
        "ansible_group": "linux_test",
        "ssh_user": "ansible",
        "credential_group": "lab_keys",
        "is_active": True,
    },
    {
        "device_name": "e2e-linux-02",
        "ip_address": "10.20.0.12",
        "os_type": "linux",
        "environment": "test",
        "ansible_group": "linux_test",
        "ssh_user": "ansible",
        "credential_group": "lab_keys",
        "is_active": True,
    },
    {
        "device_name": "e2e-linux-03",
        "ip_address": "10.20.0.13",
        "os_type": "linux",
        "environment": "staging",
        "ansible_group": "linux_staging",
        "ssh_user": "ansible",
        "credential_group": "lab_keys",
        "is_active": True,
    },
]


def seed_test_assets(db: Session) -> int:
    """Insert missing test assets. Returns number of inserted rows."""
    inserted = 0
    for item in MVP_TEST_ASSETS:
        existing = (
            db.query(Asset)
            .filter(Asset.device_name == item["device_name"])
            .first()
        )
        if existing is not None:
            # Keep E2E hosts active and metadata aligned with seed.
            for key, value in item.items():
                if key == "device_name":
                    continue
                setattr(existing, key, value)
            continue
        db.add(Asset(**item))  # type: ignore[arg-type]
        inserted += 1
    db.commit()
    return inserted

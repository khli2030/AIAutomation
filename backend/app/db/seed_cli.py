"""CLI helper to seed remediation_catalog and test assets."""

from app.db.seed_assets import seed_test_assets
from app.db.seed_remediation_catalog import seed_remediation_catalog
from app.db.session import SessionLocal


def main() -> None:
    db = SessionLocal()
    try:
        catalog_changed = seed_remediation_catalog(db)
        assets_inserted = seed_test_assets(db)
        print(
            f"Remediation catalog rows inserted/updated: {catalog_changed}. "
            f"Test assets inserted: {assets_inserted}."
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()

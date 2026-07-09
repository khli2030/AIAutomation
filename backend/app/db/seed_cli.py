"""CLI helper to seed remediation_catalog."""

from app.db.seed_remediation_catalog import seed_remediation_catalog
from app.db.session import SessionLocal


def main() -> None:
    db = SessionLocal()
    try:
        inserted = seed_remediation_catalog(db)
        print(f"Inserted {inserted} remediation_catalog rows.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

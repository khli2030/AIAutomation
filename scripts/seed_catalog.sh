#!/usr/bin/env bash
# Seed remediation_catalog after migrations.
# Usage (inside backend container): python -m scripts.seed_catalog
# Or from host with compose: docker compose exec backend python -m app.db.seed_cli

set -euo pipefail
cd "$(dirname "$0")/.."
echo "Use: docker compose exec backend python -c \"from app.db.session import SessionLocal; from app.db.seed_remediation_catalog import seed_remediation_catalog; db=SessionLocal(); print(seed_remediation_catalog(db))\""

# Phase 6.5 — End-to-End Mock Workflow Test

## Goal

Prove the full remediation path works with **`MOCK_MODE=true`** before any frontend or real Ansible work:

seed → Excel upload → parse → validate → `READY_FOR_PLAN` → execution plan →
`waiting_dry_run` → mock dry-run → `result_type=dry_run` → approve → mock run →
`result_type=run` → final status `success` / `failed` / `partially_failed`.

## Explicitly out of scope

- Real Ansible Runner / `ansible-playbook` / `subprocess` / SSH
- Frontend (Phase 7)
- Changing `MOCK_MODE` to `false`

## Artifacts

| Artifact | Purpose |
|----------|---------|
| `backend/tests/integration/test_phase65_e2e_mock_workflow.py` | Automated full-path API test (SQLite + sync parse) |
| `scripts/e2e_mock_workflow.sh` | Operator CLI against a running Compose stack |
| `backend/app/db/seed_assets.py` | Lab hosts `e2e-linux-01` … `03` |
| `python -m app.db.seed_cli` | Seeds catalog **and** test assets |

## Run automated E2E (no Docker)

```bash
cd backend
PYTHONPATH=. pytest tests/integration/test_phase65_e2e_mock_workflow.py -q
```

The integration fixture:

- Forces `MOCK_MODE=true` and a test `ADMIN_TOKEN`
- Creates an isolated SQLite schema
- Seeds enabled `SSH_DISABLE_ROOT_LOGIN` + test assets
- Patches Celery `parse_excel_batch.delay` to run synchronously

## Run CLI against Compose

```bash
cp .env.example .env   # set ADMIN_TOKEN; keep MOCK_MODE=true
docker compose up -d --build db redis backend celery-worker
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.db.seed_cli
./scripts/e2e_mock_workflow.sh
```

## Dashboard

`GET /dashboard/summary` may return **501** until Phase 7. The E2E test and script accept 200 or 501.

## Gate

Do **not** start frontend or real Ansible until this E2E mock workflow passes.

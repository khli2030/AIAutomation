# Phase 9C — Execution Audit + Safety Hardening

Traceable execution audits, plan summary counters, and CSV export **before** any real Ansible pilot.

## Safety defaults (unchanged)

| Setting | Default | Phase 9C |
|---------|---------|----------|
| `MOCK_MODE` | `true` | **Unchanged** |
| `REAL_ANSIBLE_ENABLED` | `false` | **Unchanged** |

Still true:

- No `ansible-runner`, subprocess, or SSH in mock mode
- Never execute raw Excel Remediation text
- Never execute AI suggestions directly
- Approve only after `dry_run_success`
- Run only after approval (`approved`)
- `dry_run_failed` cannot be approved or run

## Backend

### Audit events

Written into `audit_logs` (structured JSON in `details`) for:

- `dry_run_started` / `dry_run_retry_started`
- `dry_run_completed` / `dry_run_failed`
- `approved` / `rejected`
- `run_started` / `run_completed` / `run_failed`

Each event includes actor/role, `plan_id`, `job_id`, `batch_id`, action, old/new status, `mock_mode`, `real_ansible_enabled`, timestamp, and host summary counts when available.

Legacy Phase 6 `action` values (`dry_run`, `approve`, `reject`, `run`) are preserved; Phase 9C names live in `details.event`.

### Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/execution-plans/{plan_id}/audit` | Newest-first audit timeline |
| `GET` | `/execution-plans/{plan_id}/summary` | Jobs/targets/result counters + mode flags |
| `GET` | `/execution-plans/{plan_id}/results.csv` | Per-host results CSV export |

CSV columns: `plan_id, job_id, task_code, host, result_type, status, changed, stdout, stderr, message, created_at`.

## Frontend

**Plan Detail** (`/plans/[planId]`):

- Execution summary cards (jobs by status, targets, dry-run/run counts, MOCK/REAL mode)
- Jobs / Audit tabs (audit timeline)
- Export Results CSV

**Results** (`/jobs/[jobId]`):

- Export CSV (plan-scoped via `job.plan_id`)
- Existing result_type / status filters
- Expandable failed stdout/stderr

## Tests

- Backend: `backend/tests/unit/test_phase9c_execution_audit.py`
- Playwright: `frontend/e2e/phase9c-audit-summary.spec.ts` (mocked API; Phase 9B flow remains in `phase9b-workflow.spec.ts`)

## Out of scope

- Enabling real Ansible apply/run
- Changing execution gates or safety defaults
- Executing Excel Remediation or AI drafts

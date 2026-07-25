# Phase 10A — Real Ansible Pilot Preparation

Prepare a **limited** real Ansible check-mode pilot path without enabling broad production execution.

## Safety defaults (unchanged)

| Setting | Default |
|---------|---------|
| `MOCK_MODE` | `true` |
| `REAL_ANSIBLE_ENABLED` | `false` |
| `REAL_ANSIBLE_CHECK_MODE_ONLY` | `true` |
| `REAL_ANSIBLE_ALLOWED_HOSTS` | empty (nothing allowlisted) |
| `REAL_ANSIBLE_ALLOWED_TASK_CODES` | empty (nothing allowlisted) |
| `REAL_ANSIBLE_TIMEOUT_SECONDS` | `120` |

Optional pilot overrides (unset by default):

- `REAL_ANSIBLE_INVENTORY_PATH`
- `REAL_ANSIBLE_PRIVATE_KEY_PATH`
- `REAL_ANSIBLE_REMOTE_USER`

Still true:

- No ansible-runner / subprocess / SSH unless gates pass
- Never execute Excel Remediation text
- Never execute AI suggestions
- Approve only after `dry_run_success`; run only when `approved`
- Phase 10A does **not** add a production real-apply endpoint

## Backend

### Gate: `can_execute_real_ansible(...)`

Requires (as applicable):

- `REAL_ANSIBLE_ENABLED=true` and `MOCK_MODE=false`
- Host in `REAL_ANSIBLE_ALLOWED_HOSTS`
- Task code in `REAL_ANSIBLE_ALLOWED_TASK_CODES`
- Catalog-defined playbook only
- Check-mode / dry-run unless `REAL_ANSIBLE_CHECK_MODE_ONLY=false`
- Job `approved` before real run/apply (apply still blocked when check-mode-only)

### Endpoints

| Method | Path | Behavior |
|--------|------|----------|
| `GET` | `/ansible/safety-status` | Config + availability + reasons (no execution) |
| `POST` | `/ansible/connectivity-check` | Allowlisted ping; blocked by default |
| `POST` | `/execution-jobs/{id}/real-dry-run` | Check-mode only; `result_type=real_dry_run` |

### Audit events

- `real_connectivity_check_started` / `_completed` / `_failed`
- `real_dry_run_started` / `_completed` / `_failed`
- `real_execution_blocked`

### Results

`job_results.result_type` may be `real_dry_run` (string column; no breaking migration).

## Frontend

- **Safety / Ansible** page (`/safety`) — status cards + blocked reasons
- **Plan Detail** — Real Ansible blocked/available; “Real Ansible Dry Run (Check Mode)” only when available; confirmation modal
- **Results** — `real_dry_run` filter + expandable stdout/stderr
- **Audit** — real Ansible events in timeline

## Tests

- Backend: `backend/tests/unit/test_phase10a_real_ansible_pilot.py`
- Playwright: `frontend/e2e/phase10a-safety.spec.ts`

## Out of scope

- Enabling real apply/run for production
- Changing default safety flags
- Executing Excel Remediation or AI drafts

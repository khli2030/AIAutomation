# Phase 9B — Frontend Execution Workflow Controls

## Goal

Let operators complete the full remediation workflow from the UI without curl
or SQL:

Upload Excel → Validate Batch → Generate Plan → Open Plan → Bulk Dry Run →
Bulk Approve → Bulk Run → View Results

## Safety (unchanged)

| Rule | Status |
|------|--------|
| Backend real Ansible gates | Unchanged |
| `MOCK_MODE=true` default | Unchanged |
| `REAL_ANSIBLE_ENABLED=false` default | Unchanged |
| Never execute Excel Remediation text | Unchanged |
| Never execute AI-generated playbooks | Unchanged |
| Never bypass approval | Enforced in UI + API |
| Run only when `status=approved` | Enforced |
| Approve only when `status=dry_run_success` | Enforced |

## UI surfaces

### Import Summary (`/imports`)

- **Validate Batch** — operator/admin; enabled when batch is `parsed` or records
  still have unknown/null `validation_status`
- **Generate Plan** — operator/admin; enabled when `READY_FOR_PLAN > 0`
- **Refresh** — reloads batch + READY_FOR_PLAN hints
- Loading disables buttons; success/error messages after actions

### Execution Plans (`/plans`)

Shows Plan ID, Batch ID, Status, Job count, Target count, Created by,
Created at, and **View Jobs**.

### Plan Detail (`/plans/[planId]`)

- Plan summary + job status counts
- Jobs table with Dry Run / Approve / Reject / Run / Results (status + role gated)
- Bulk actions with confirmation modal:
  - Dry Run All Waiting Jobs (`waiting_dry_run` only)
  - Approve All Dry Run Success Jobs (`dry_run_success` only)
  - Run All Approved Jobs (`approved` only)
- Continues after individual failures; shows `completed/total` progress and summary

### Job Results (`/jobs/[jobId]`)

- Filter by `result_type` (`dry_run` / `run`) and status (`success` / `skipped` / `failed`)
- Counts summary
- Expandable stdout/stderr; failed rows highlighted

### MOCK_MODE banner

- Mock: `MOCK MODE: no SSH or Ansible execution is performed.`
- Real: `REAL EXECUTION MODE: actions may affect servers. Backend gates still apply.`

## Role gating (`/auth/me`)

| Role | Actions |
|------|---------|
| viewer | Read-only |
| operator | validate, generate plan, dry-run, run |
| approver | approve / reject |
| admin | all |

## Tests

```bash
cd frontend
npm install
npx playwright install chromium
npm run test:e2e
```

- `e2e/ui-mock-workflow.spec.ts` — original happy path (updated)
- `e2e/phase9b-workflow.spec.ts` — bulk gating, viewer vs admin, full UI flow

## Explicit non-goals

- Backend bulk endpoints (UI sequences per-job POSTs)
- Changing Ansible / MOCK_MODE defaults
- Enabling production real execution

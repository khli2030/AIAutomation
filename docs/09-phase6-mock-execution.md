# Phase 6 — Mock Dry Run and Mock Execution

## Scope

- `POST /execution-jobs/{job_id}/dry-run`
- `POST /execution-jobs/{job_id}/run`
- `GET /execution-jobs/{job_id}/results`

Uses `AnsibleExecutionService` **mock path only** (`MOCK_MODE=true` default).

## Explicitly out of scope

- Real Ansible Runner
- `ansible-playbook` / `ansible-runner` invocation
- `subprocess` / SSH
- AI `generated_playbook` for execution

## Dry-run

1. Allowed only when `status = waiting_dry_run`
2. Sets `dry_run_running`, then mock per-host results
3. Final: `dry_run_success` (all pass) or `dry_run_failed` (any fail / mixed)
4. Audit log

## Approve (unchanged gate)

- Allowed only when `status = dry_run_success`
- Sets `approved` + `approved_by` / `approved_at`

## Run

1. Allowed only when `status = approved`
2. Sets `running`, then mock per-host results
3. Final: `success` / `failed` / `partially_failed`
4. Audit log

## Safety

- Only enabled `remediation_catalog` playbook paths
- Never AI `generated_playbook`
- Disabled catalog entries raise error

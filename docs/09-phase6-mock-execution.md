# Phase 6 — Mock Dry Run and Mock Execution

## Scope

- `POST /execution-jobs/{job_id}/dry-run`
- `POST /execution-jobs/{job_id}/run`
- `GET /execution-jobs/{job_id}/results?result_type=dry_run|run`

Uses `AnsibleExecutionService` **mock path only** (`MOCK_MODE=true` default).

## Explicitly out of scope

- Real Ansible Runner (returns clear not-implemented when `MOCK_MODE=false`)
- `ansible-playbook` / `ansible-runner` invocation
- `subprocess` / SSH
- AI draft playbooks for execution

## job_results.result_type

| Value | Written by |
|-------|------------|
| `dry_run` | dry-run path |
| `run` | apply/run path |

- Dry-run replaces only previous `dry_run` rows (retry after `dry_run_failed` allowed).
- Run replaces only previous `run` rows — **never** overwrites dry-run results.
- `GET .../results?result_type=dry_run` or `?result_type=run` filters clearly.

## Dry-run

1. Allowed when `status` is `waiting_dry_run` or `dry_run_failed`
2. Sets `dry_run_running`, then mock per-host results (`result_type=dry_run`)
3. Final: `dry_run_success` (all pass) or `dry_run_failed` (any fail / mixed)
4. Audit log (`action=dry_run`)

## Approve

- Allowed only when `status = dry_run_success`
- Sets `approved` + `approved_by` / `approved_at`
- Audit log (`action=approve`)

## Reject

- Allowed for `waiting_dry_run`, `dry_run_failed`, `waiting_approval`
- Audit log (`action=reject`)

## Run

1. Allowed only when `status = approved`
2. Sets `running`, then mock per-host results (`result_type=run`)
3. Final: `success` / `failed` / `partially_failed`
4. Audit log (`action=run`)

## Safety

- Only enabled `remediation_catalog` playbook paths
- Never AI draft playbooks
- Disabled catalog entries raise error
- Migration: `0003_phase6_job_result_type`

## Pre-merge review checklist

1. Dry-run vs run distinguishable via `result_type`
2. GET results filterable by `result_type`
3. Repeat dry-run replaces dry_run rows only (or blocked when status disallows)
4. Run never overwrites dry_run results
5. Approve only after `dry_run_success`
6. Run only after `approved`
7. Disabled catalog never executed
8. AI draft playbooks never used
9. MOCK_MODE=true: no runner/playbook/subprocess/SSH
10. MOCK_MODE=false: clear not-implemented error
11. Audit logs for dry-run / approve / reject / run
12. Tests cover all above

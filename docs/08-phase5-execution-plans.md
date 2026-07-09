# Phase 5 — Execution Plan and Approval Workflow

## Scope

- `POST /imports/{batch_id}/generate-plan`
- `GET /execution-plans/{plan_id}`
- `GET /execution-plans/{plan_id}/jobs`
- `POST /execution-jobs/{job_id}/approve`
- `POST /execution-jobs/{job_id}/reject`

## Explicitly out of scope

- Ansible / MOCK execution
- Real Ansible Runner
- Dry-run and run endpoints (remain 501 until Phase 6)
- Changing `MOCK_MODE`
- Using AI `generated_playbook` for execution

## Plan generation rules

1. Include only `validation_status = READY_FOR_PLAN`
2. Exclude NEEDS_REVIEW, ASSET_NOT_FOUND, ALREADY_COMPLIANT, DUPLICATE, INVALID_RECORD, UNSUPPORTED_CONTROL
3. Join `remediation_catalog`; skip missing or disabled (`is_enabled=false`) task codes
4. Group by `task_code`, `environment`, `criticality`, `ansible_group`
5. Split groups into jobs of max 100 devices
6. Create jobs with `status = waiting_dry_run`
7. Create `execution_job_targets` per device
8. Audit `generate_plan`

## Approval rules

- Approve blocked unless `dry_run_success` / `waiting_approval`
- `waiting_dry_run` approve → 400 (dry-run not implemented in Phase 5)
- Reject allowed for `waiting_dry_run`, `dry_run_failed`, `waiting_approval`
- Audit approve / reject

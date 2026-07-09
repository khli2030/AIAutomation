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
4. Take `environment` / `ansible_group` from matched `assets` only (never Excel)
5. Skip when asset `environment` or `ansible_group` is missing (`skipped_missing_asset_metadata`)
6. Group by `task_code`, `environment`, `criticality`, `ansible_group`
7. Split groups into jobs of max 100 devices
8. Create jobs with `status = waiting_dry_run`
9. Create `execution_job_targets` per device
10. Audit `generate_plan`

## Approval rules

- Approve blocked unless `status = dry_run_success`
- `waiting_dry_run` approve → 400 (dry-run not implemented in Phase 5)
- Reject allowed for `waiting_dry_run`, `dry_run_failed`, `waiting_approval`
- Audit approve / reject

## Pre-merge review checklist

1. Only READY_FOR_PLAN included
2. Excluded statuses never planned
3. Catalog exists + `is_enabled=true` required
4. No AI `generated_playbook` / suggestions used
5. env/group from assets only
6. Missing env/group skipped with counter
7. Max 100 targets per job
8. Approve requires `dry_run_success`
9. Reject for waiting_dry_run / dry_run_failed / waiting_approval
10. No Ansible / MOCK / subprocess / SSH

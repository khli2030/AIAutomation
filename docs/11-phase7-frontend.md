# Phase 7 — Frontend Dashboard

## Scope

Next.js App Router operator UI + thin backend list/dashboard APIs.

## Backend additions (read-only / list)

- `GET /dashboard/summary` — counters + latest imports/jobs (`mock_mode` included)
- `GET /imports` — list batches
- `GET /imports/{id}/records?validation_status&task_code&device_name`
- `GET /execution-plans` — list plans
- `GET /execution-jobs` — list jobs (`?status=`)
- `GET /execution-jobs/{id}` — job detail

No Ansible / runner / subprocess / SSH changes. `MOCK_MODE` default remains `true`.

## Frontend

See [`frontend/README.md`](../frontend/README.md).

## Explicit non-goals

- Real Ansible execution
- Playbook editing
- Enabling AI-generated playbooks for execution
- Hardcoded `ADMIN_TOKEN`

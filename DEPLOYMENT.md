# Deployment guide — internal Ansible control server

This platform is **internal / on-prem only**. It does not use AWS or public cloud.

## Where real Ansible runs

**Real Ansible execution happens only after deploying to the internal Ansible control server** that already has:

- Ansible installed
- SSH access to target Linux hosts
- Approved playbooks under `ansible/playbooks/` (or `ANSIBLE_HOST_DIR`)
- SSH private keys available to the Celery worker (never committed to git)

Until that deployment and Phase 6 (Ansible Runner wiring) are complete, keep:

```bash
MOCK_MODE=true
```

With `MOCK_MODE=true`, `AnsibleExecutionService` returns fake but realistic per-host results and **never**:

- imports or calls `ansible-runner`
- runs `ansible-playbook`
- uses `subprocess` / shell
- opens SSH connections

The real adapter (`real_ansible_runner.py`) is only imported lazily when `MOCK_MODE=false`, and even then it currently raises “not implemented” until Phase 6.

## Environments

| Environment | `MOCK_MODE` | Ansible Runner | Notes |
|-------------|-------------|----------------|-------|
| Local laptop / CI without Ansible targets | `true` | Not used | Safe default |
| Internal Ansible control server (lab) | `true` until Phase 6 ready | Not used | Validate API/workflows |
| Internal Ansible control server (execution) | `false` (later) | Used | Only after Phase 6 + reviewed playbooks |

## Deploy steps (internal server)

1. Copy the repository onto the Ansible control host.
2. `cp .env.example .env` and set strong `ADMIN_TOKEN`, `SECRET_KEY`, `POSTGRES_PASSWORD`.
3. Keep `MOCK_MODE=true` until real Runner is implemented and tested.
4. Start stack:

```bash
docker compose up -d --build db redis backend celery-worker
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.db.seed_cli
```

5. Confirm health: `curl http://127.0.0.1:8000/health`
6. Only later (Phase 6): implement real Runner path, test dry-run on non-prod hosts, then consider `MOCK_MODE=false`.

## Safety reminders

- Excel `Remediation` text is never executed.
- Only `remediation_catalog` entries with `is_enabled=true` may run (default: `SSH_DISABLE_ROOT_LOGIN` only).
- Stub playbooks stay disabled.
- `ansible/` is mounted read-only; uploads/runtime stay under `./data`.
- Ports bind to `127.0.0.1` — not production-ready without TLS and stronger auth.

## What is not done yet

- Real `ansible-runner` / `ansible-playbook` invocation (`MOCK_MODE=false` currently raises a clear error)
- Phase 2 Excel import and later workflow phases

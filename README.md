# AIAutomation — Linux Compliance Remediation Platform

Internal on-prem platform for managing Linux compliance remediation via an existing Ansible control server.

**No AWS / no public cloud.** MVP runs platform + Celery + Ansible Runner on the same internal Ansible host.

> **WARNING — internal-only, not production-ready**
>
> This Phase 1 stack is for internal lab / controlled Ansible-host use only.
> Do **not** treat it as production until you have:
> - strong `ADMIN_TOKEN` / real authentication and authorization
> - TLS termination (reverse proxy) in front of the API
> - reviewed, enabled playbooks only (stubs stay disabled)
> - hardened secrets (no default DB passwords)
> - operational monitoring and backup for PostgreSQL
>
> Ports bind to `127.0.0.1` only. PostgreSQL and Redis are not exposed on the LAN.

## MOCK_MODE (important)

| Setting | Behaviour |
|---------|-----------|
| `MOCK_MODE=true` (default) | Fake per-host results only. **No** `ansible-runner`, **no** `ansible-playbook`, **no** `subprocess`/shell, **no** SSH. |
| `MOCK_MODE=false` | Reserved for the internal Ansible control server. Real Runner is **not implemented yet** and will refuse to run until Phase 6. |

**Real Ansible execution happens only after deploying to the internal Ansible control server.** See [`DEPLOYMENT.md`](DEPLOYMENT.md).

## Stack

| Layer | Technology |
|-------|------------|
| Backend | Python **FastAPI** |
| Database | PostgreSQL |
| Queue | Redis + Celery |
| Automation | Ansible + Ansible Runner (mock until Phase 6) |
| Frontend | Next.js (Phase 7; placeholder for now) |
| Deploy | Docker Compose (internal) |

## Safety principles

- Excel `Remediation` text is **never** executed as a command.
- Only approved **enabled** playbooks from `remediation_catalog` may run.
- By default only `SSH_DISABLE_ROOT_LOGIN` is enabled; stub playbooks are disabled.
- AI suggestions are draft-only and never auto-executed.
- Production execution (later phases) requires dry-run success + human approval.
- `ansible/` is mounted **read-only**; uploads/runtime artifacts stay under `./data`.

## Current status

**Phase 6.5 available:** end-to-end mock workflow test + `scripts/e2e_mock_workflow.sh` (seed → upload → parse → validate → plan → dry-run → approve → run). Keep `MOCK_MODE=true`. No frontend or real Ansible until this E2E passes.

Also includes Phase 1–6 (upload/parse/validate/AI drafts/plans/mock dry-run/run) and `MOCK_MODE` (default true — no real Ansible).

## Quick start (internal Ansible host)

```bash
cp .env.example .env
# REQUIRED: set strong ADMIN_TOKEN, SECRET_KEY, POSTGRES_PASSWORD
# Keep MOCK_MODE=true until Phase 6 on the Ansible control server

docker compose up -d --build db redis backend celery-worker
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.db.seed_cli
# seeds remediation_catalog + lab test assets (e2e-linux-01..)

# Full mock E2E (requires Celery worker + ADMIN_TOKEN):
./scripts/e2e_mock_workflow.sh
```

Upload example (requires ADMIN_TOKEN):

```bash
curl -X POST http://127.0.0.1:8000/imports/upload \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -F "file=@/path/to/compliance.xlsx" \
  -F "uploaded_by=operator1"
```

Health (public):

```bash
curl -s http://127.0.0.1:8000/health
```

Authenticated call example:

```bash
curl -s http://127.0.0.1:8000/ \
  -H "X-Admin-Token: $ADMIN_TOKEN"
```

Prefer SSH tunnel from another host:

```bash
ssh -L 8000:127.0.0.1:8000 user@ansible-control.internal
```

## Project layout

See [`docs/01-project-structure.md`](docs/01-project-structure.md), [`docs/02-phase1-files.md`](docs/02-phase1-files.md), [`docs/05-phase1-security-hardening.md`](docs/05-phase1-security-hardening.md), and [`DEPLOYMENT.md`](DEPLOYMENT.md).

## Phases

1. Structure + compose + models + Celery
2. Excel upload + chunked parse
3. Validation + classifier + asset match
4. AI analyzer interface + suggestions
5. Execution plans + approval + audit
6. Ansible Runner dry-run / run (mock path; real path later when `MOCK_MODE=false`)
6.5. E2E mock workflow test + CLI ← **current gate**
7. Frontend pages

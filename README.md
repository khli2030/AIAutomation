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

## Stack

| Layer | Technology |
|-------|------------|
| Backend | Python **FastAPI** |
| Database | PostgreSQL |
| Queue | Redis + Celery |
| Automation | Ansible + Ansible Runner |
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

**Phase 1 + security hardening (this branch):** project structure, docker-compose (loopback binds), FastAPI skeleton with `ADMIN_TOKEN` guard, SQLAlchemy models, Alembic, Celery, Ansible layout, reviewed SSH playbook only enabled.

## Quick start (internal Ansible host)

```bash
cp .env.example .env
# REQUIRED: set strong ADMIN_TOKEN, SECRET_KEY, POSTGRES_PASSWORD

docker compose up -d --build db redis backend celery-worker
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.db.seed_cli
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

API docs also require the token (browser extensions or curl). Prefer SSH tunnel from another host:

```bash
ssh -L 8000:127.0.0.1:8000 user@ansible-control.internal
```

## Project layout

See [`docs/01-project-structure.md`](docs/01-project-structure.md), [`docs/02-phase1-files.md`](docs/02-phase1-files.md), and [`docs/05-phase1-security-hardening.md`](docs/05-phase1-security-hardening.md).

## Phases

1. Structure + compose + models + Celery ← **current (hardened)**
2. Excel upload + chunked parse
3. Validation + classifier + asset match
4. AI analyzer interface + suggestions
5. Execution plans + approval + audit
6. Ansible Runner dry-run / run
7. Frontend pages

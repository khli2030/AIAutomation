# AIAutomation — Linux Compliance Remediation Platform

Internal on-prem platform for managing Linux compliance remediation via an existing Ansible control server.

**No AWS / no public cloud.** MVP runs platform + Celery + Ansible Runner on the same internal Ansible host.

## Stack

| Layer | Technology |
|-------|------------|
| Backend | Python **FastAPI** |
| Database | PostgreSQL |
| Queue | Redis + Celery |
| Automation | Ansible + Ansible Runner |
| Frontend | Next.js (Phase 7; placeholder for now) |
| Deploy | Docker Compose |

## Safety principles

- Excel `Remediation` text is **never** executed as a command.
- Only approved playbooks from `ansible/playbooks/` mapped via `remediation_catalog` may run.
- AI suggestions are draft-only and never auto-executed.
- Production requires dry-run success + human approval.

## Current status

**Phase 1 complete (this branch):** project structure, docker-compose, FastAPI skeleton, SQLAlchemy models, Alembic migration, Celery setup, Ansible folder + initial SSH playbook, AI provider interface (mock).

## Quick start (MVP)

```bash
cp .env.example .env
docker compose up -d --build db redis backend celery-worker
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.db.seed_cli
```

API docs: http://localhost:8000/docs  
Health: http://localhost:8000/health

Optional frontend placeholder:

```bash
docker compose --profile frontend up -d frontend
```

## Project layout

See [`docs/01-project-structure.md`](docs/01-project-structure.md) and [`docs/02-phase1-files.md`](docs/02-phase1-files.md).

## Phases

1. Structure + compose + models + Celery ← **current**
2. Excel upload + chunked parse
3. Validation + classifier + asset match
4. AI analyzer interface + suggestions
5. Execution plans + approval + audit
6. Ansible Runner dry-run / run
7. Frontend pages

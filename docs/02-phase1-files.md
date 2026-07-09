# Phase 1 — Files created and purpose

Phase 1 delivers the MVP skeleton only: structure, Docker Compose, FastAPI app shell, database models + Alembic migration, Celery wiring, Ansible folder layout, and a mock AI provider interface.

Business logic for upload/parse/classify/plan/execute is intentionally stubbed (`501` / `not_implemented`) for later phases.

## Root

| File | Purpose |
|------|---------|
| `README.md` | Project overview, stack, quick start |
| `.gitignore` | Ignore secrets, venv, runtime uploads, frontend build |
| `.env.example` | Non-secret env template (copy to `.env`) |
| `docker-compose.yml` | `db`, `redis`, `backend`, `celery-worker`, optional `frontend` |
| `docs/01-project-structure.md` | Architecture / folder rationale |
| `docs/02-phase1-files.md` | This file |

## Backend

| File | Purpose |
|------|---------|
| `backend/Dockerfile` | Shared image for API + Celery (includes ansible-core for worker) |
| `backend/requirements.txt` | Python dependencies |
| `backend/alembic.ini` | Alembic config |
| `backend/alembic/env.py` | Migration env using `Settings.database_url` |
| `backend/alembic/script.py.mako` | Migration template |
| `backend/alembic/versions/0001_initial_schema.py` | Creates all 10 required tables |
| `backend/app/main.py` | FastAPI app, CORS, routers |
| `backend/app/config.py` | Pydantic Settings from environment |
| `backend/app/deps.py` | Shared dependencies |
| `backend/app/db/session.py` | SQLAlchemy engine + session |
| `backend/app/db/seed_remediation_catalog.py` | Seed approved task_code → playbook map |
| `backend/app/db/seed_cli.py` | CLI entry for seeding catalog |
| `backend/app/models/*.py` | SQLAlchemy models for all tables |
| `backend/app/schemas/common.py` | Shared Pydantic base schemas |
| `backend/app/api/*.py` | Route stubs for required endpoints |
| `backend/app/workers/celery_app.py` | Celery app (Redis broker) |
| `backend/app/workers/tasks_*.py` | Task stubs (import/plan/execute/ai) |
| `backend/app/ai/provider.py` | AI analyzer interface + mock provider + prompt template |
| `backend/app/constants/*.py` | Record/job statuses, task codes, Excel columns |

## Ansible

| File | Purpose |
|------|---------|
| `ansible/ansible.cfg` | Control-node defaults |
| `ansible/inventories/{test,staging,production}.ini` | Inventory placeholders |
| `ansible/playbooks/ssh_disable_root_login.yml` | First safe playbook (backup + validate + reload) |
| `ansible/playbooks/*.yml` | Stubs for remaining MVP task codes |
| `ansible/group_vars/all.yml` | Shared vars placeholder (no secrets) |

## Frontend / data / scripts

| File | Purpose |
|------|---------|
| `frontend/Dockerfile` | Optional placeholder HTTP server (Phase 7 replaces with Next.js) |
| `frontend/README.md` | Notes for Phase 7 |
| `data/**/.gitkeep` | Runtime volume dirs for uploads / runner private data |
| `scripts/seed_catalog.sh` | Helper reminder for catalog seed |

## Safety notes encoded in Phase 1

1. No credentials in source — only `.env.example`.
2. API stubs do not execute Ansible or Excel text.
3. AI provider defaults to mock and never executes playbooks.
4. `remediation_catalog` is the only future source of playbook paths.
5. Celery worker mounts `./ansible` read-only and `./data` read-write.

# AIAutomation — Linux Compliance Remediation Platform

**Internal / on-prem only.** No AWS, no Azure, no GCP, no public cloud runtime.

The platform runs with **Docker Compose on an internal Linux Ansible control server** that already has SSH access to target hosts. Celery workers use that host’s Ansible playbooks, inventories, and SSH keys.

## Stack

| Layer | Technology | Where it runs |
|-------|------------|---------------|
| Backend | Python **FastAPI** | Docker Compose on Ansible host |
| Database | PostgreSQL | Docker Compose (local volume) |
| Queue | Redis + Celery | Docker Compose on same host |
| Automation | Ansible + Ansible Runner | Same internal Ansible control server |
| Frontend | Next.js (Phase 7 placeholder) | Optional Compose profile |
| Deploy | **Docker Compose (internal)** | Not cloud PaaS |

## Safety principles

- Excel `Remediation` text is **never** executed as a command.
- Only approved playbooks from `ansible/playbooks/` mapped via `remediation_catalog` may run.
- AI suggestions are mock/draft-only by default and never auto-executed.
- Production requires dry-run success + human approval.
- SSH private keys stay on the Ansible host (mounted read-only) — never in git or images.

## Internal quick start (Ansible control server)

```bash
cp .env.example .env
# edit POSTGRES_PASSWORD and SECRET_KEY

mkdir -p data/ansible-ssh
cp /path/to/ansible_control_key data/ansible-ssh/id_rsa
chmod 600 data/ansible-ssh/id_rsa

./scripts/internal_bootstrap.sh
# or:
# docker compose up -d --build db redis backend celery-worker
# docker compose exec backend alembic upgrade head
# docker compose exec backend python -m app.db.seed_cli
```

API (loopback on the Ansible host): http://127.0.0.1:8000/docs  
Health: http://127.0.0.1:8000/health

From another internal workstation, use an SSH tunnel:

```bash
ssh -L 8000:127.0.0.1:8000 user@ansible-control.internal
```

Upload example:

```bash
curl -X POST http://127.0.0.1:8000/imports/upload \
  -F "file=@/path/to/compliance.xlsx" \
  -F "uploaded_by=operator1"
```

Full internal setup guide: [`docs/04-internal-dev-environment.md`](docs/04-internal-dev-environment.md)

## Current status

- **Phase 1:** structure, Compose, models, Celery, Ansible layout
- **Phase 2:** Excel upload + chunked parse
- **Internal env hardening:** loopback binds, SSH key mounts, no cloud assumptions

## Project layout

See [`docs/01-project-structure.md`](docs/01-project-structure.md), [`docs/02-phase1-files.md`](docs/02-phase1-files.md), [`docs/03-phase2-excel-import.md`](docs/03-phase2-excel-import.md), [`docs/04-internal-dev-environment.md`](docs/04-internal-dev-environment.md).

## Phases

1. Structure + compose + models + Celery
2. Excel upload + chunked parse
3. Validation + classifier + asset match
4. AI analyzer interface + suggestions (mock / optional on-prem LLM only)
5. Execution plans + approval + audit
6. Ansible Runner dry-run / run
7. Frontend pages

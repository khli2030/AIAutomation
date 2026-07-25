# AIAutomation — Linux Compliance Remediation Platform

Internal on-prem platform for managing Linux compliance remediation via an existing Ansible control server.

**No AWS / no public cloud.** MVP runs platform + Celery + Ansible Runner on the same internal Ansible host.

> **WARNING — internal-only, not production-ready**
>
> This Phase 1 stack is for internal lab / controlled Ansible-host use only.
> Do **not** treat it as production until you have:
> - strong role tokens (`VIEWER_TOKEN` / `OPERATOR_TOKEN` / `APPROVER_TOKEN` / `ADMIN_TOKEN`) and later real SSO/OIDC
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
| Frontend | Next.js (Phase 7+; Phase 8A MVP RBAC) |
| Deploy | Docker Compose (internal) |

## Safety principles

- Excel `Remediation` text is **never** executed as a command.
- Only approved **enabled** playbooks from `remediation_catalog` may run.
- By default only `SSH_DISABLE_ROOT_LOGIN` is enabled; stub playbooks are disabled.
- AI suggestions are draft-only and never auto-executed.
- Production execution (later phases) requires dry-run success + human approval.
- `ansible/` is mounted **read-only**; uploads/runtime artifacts stay under `./data`.

## Current status

**Phase 9B available:** Frontend execution workflow controls (validate / plan / bulk dry-run / approve / run / results). See [`docs/16-phase9b-frontend-workflow-controls.md`](docs/16-phase9b-frontend-workflow-controls.md).

**Phase 9A available:** Top Qualys rule coverage expansion. See [`docs/15-phase9a-qualys-rule-coverage.md`](docs/15-phase9a-qualys-rule-coverage.md).

**Phase 8C available:** Lab-only real Ansible **dry-run** (ansible-runner `--check`). Real apply/run stays blocked. See [`docs/14-phase8c-lab-real-dry-run.md`](docs/14-phase8c-lab-real-dry-run.md).

**Phase 8C.5:** Lab real dry-run **smoke test** docs + checklist. See [`docs/14-phase8c5-lab-real-dry-run-smoke-test.md`](docs/14-phase8c5-lab-real-dry-run-smoke-test.md).

Also includes Phase 1–8B (API + Next.js + MVP RBAC + readiness gates).
Defaults remain `MOCK_MODE=true` and `REAL_ANSIBLE_ENABLED=false`.

## Quick start (internal Ansible host)

```bash
cp .env.example .env
# REQUIRED: set role tokens (at least ADMIN_TOKEN), SECRET_KEY, POSTGRES_PASSWORD
# Keep MOCK_MODE=true and REAL_ANSIBLE_ENABLED=false

docker compose up -d --build db redis backend celery-worker
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.db.seed_cli
# seeds remediation_catalog + lab test assets (e2e-linux-01..)

# Full mock E2E (requires Celery worker + ADMIN_TOKEN or OPERATOR_TOKEN):
./scripts/e2e_mock_workflow.sh
```

### Frontend (Phase 7 + 8A RBAC)

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
# open http://127.0.0.1:3000 → Settings / Login → paste a role token
```

Or: `docker compose --profile frontend up -d --build frontend`

See [`frontend/README.md`](frontend/README.md), [`docs/11-phase7-frontend.md`](docs/11-phase7-frontend.md), and [`docs/12-phase8a-rbac.md`](docs/12-phase8a-rbac.md).

Upload example (requires OPERATOR_TOKEN or ADMIN_TOKEN):

```bash
curl -X POST http://127.0.0.1:8000/imports/upload \
  -H "X-Admin-Token: $OPERATOR_TOKEN" \
  -F "file=@/path/to/compliance.xlsx" \
  -F "uploaded_by=operator1"
```

Health (public):

```bash
curl -s http://127.0.0.1:8000/health
```

Who am I (any role token):

```bash
curl -s http://127.0.0.1:8000/auth/me \
  -H "X-Admin-Token: $VIEWER_TOKEN"
```

Authenticated call example:

```bash
curl -s http://127.0.0.1:8000/ \
  -H "X-Admin-Token: $ADMIN_TOKEN"
```

Ansible preflight (read-only; does not execute):

```bash
curl -s http://127.0.0.1:8000/ansible/preflight \
  -H "X-Admin-Token: $VIEWER_TOKEN"
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
6.5. E2E mock workflow test + CLI
7. Frontend pages
7.5. UI E2E mock test (Playwright + manual)
8A. Minimal MVP RBAC (role tokens)
8B. Real Ansible readiness (lab/test gates + preflight)
8C. Lab-only real Ansible dry-run (ansible-runner --check)
8C.5. Lab real dry-run smoke test docs + checklist
9A. Top Qualys rule coverage expansion (classifier + catalog)
9B. Frontend execution workflow controls ← **current**
8. Full real Ansible apply/run (not started — keep defaults safe)

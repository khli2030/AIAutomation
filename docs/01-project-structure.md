# Step 1 — Project Structure Proposal

> Scope: structure only. No application code, Docker Compose, or schema yet.
> Assumption: platform + Celery worker + Ansible Runner run on the **same internal Ansible control server**.

## Design goals

- Keep Ansible artifacts (`playbooks/`, `inventories/`) as the **only** execution source of truth.
- Never execute Excel `Remediation` text as shell/commands.
- Allow Celery worker to mount/read `ansible/` safely.
- Keep FastAPI API thin; put parse/classify/plan/execute logic in dedicated services + Celery tasks.
- Remain expandable later to a remote Ansible host / AWX / AAP without rewriting domain logic.

## Proposed repository layout

```text
compliance-remediation-platform/
├── README.md
├── .env.example                          # non-secret defaults only
├── .gitignore
├── docker-compose.yml                    # Step 2
├── docs/
│   ├── 01-project-structure.md           # this document
│   ├── architecture.md                   # later: sequence diagrams, trust boundaries
│   └── security.md                       # later: approval, credentials, dry-run rules
│
├── ansible/                              # mounted into celery-worker (read-only preferred)
│   ├── ansible.cfg
│   ├── inventories/
│   │   ├── production.ini
│   │   ├── staging.ini
│   │   └── test.ini
│   ├── playbooks/
│   │   ├── ssh_disable_root_login.yml
│   │   ├── ssh_disable_x11_forwarding.yml
│   │   ├── ssh_set_max_sessions.yml
│   │   ├── set_pass_max_days.yml
│   │   ├── set_var_log_permissions.yml
│   │   ├── set_tmp_nodev.yml
│   │   ├── set_tmp_noexec.yml
│   │   ├── set_dev_shm_nodev.yml
│   │   └── set_dev_shm_noexec.yml
│   ├── group_vars/
│   │   └── all.yml
│   ├── host_vars/
│   └── roles/                            # optional shared roles later
│
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml                    # or requirements.txt
│   ├── alembic.ini
│   ├── alembic/
│   │   └── versions/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                       # FastAPI app factory
│   │   ├── config.py                     # settings from env (no secrets in code)
│   │   ├── deps.py                       # DB / auth dependencies
│   │   │
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── router.py                 # mounts all routers
│   │   │   ├── imports.py                # upload / batch / records / generate-plan
│   │   │   ├── execution_plans.py
│   │   │   ├── execution_jobs.py         # dry-run / approve / reject / run / results
│   │   │   ├── assets.py                 # later
│   │   │   └── dashboard.py              # later
│   │   │
│   │   ├── models/                       # SQLAlchemy / SQLModel tables
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── import_batch.py
│   │   │   ├── raw_import_record.py
│   │   │   ├── asset.py
│   │   │   ├── remediation_catalog.py
│   │   │   ├── execution_plan.py
│   │   │   ├── execution_job.py
│   │   │   ├── execution_job_target.py
│   │   │   ├── job_result.py
│   │   │   └── audit_log.py
│   │   │
│   │   ├── schemas/                      # Pydantic request/response models
│   │   │   ├── __init__.py
│   │   │   ├── imports.py
│   │   │   ├── records.py
│   │   │   ├── plans.py
│   │   │   ├── jobs.py
│   │   │   └── dashboard.py
│   │   │
│   │   ├── services/                     # domain logic (no FastAPI / Celery coupling)
│   │   │   ├── __init__.py
│   │   │   ├── excel_parser.py           # openpyxl read_only + chunking
│   │   │   ├── classifier.py             # Qualys/Source/text → task_code
│   │   │   ├── validator.py              # status / asset / duplicate / classify checks
│   │   │   ├── plan_generator.py         # READY_FOR_PLAN → jobs (batch by task/env/crit/group)
│   │   │   ├── inventory_sync.py         # import Ansible inventory → assets
│   │   │   ├── ansible_runner_service.py # approved playbooks only via Ansible Runner
│   │   │   ├── approval.py
│   │   │   └── audit.py
│   │   │
│   │   ├── workers/                      # Celery app + tasks
│   │   │   ├── __init__.py
│   │   │   ├── celery_app.py
│   │   │   ├── tasks_import.py           # parse + classify + validate
│   │   │   ├── tasks_plan.py
│   │   │   └── tasks_execute.py          # dry-run + real run
│   │   │
│   │   ├── classifiers/                  # rule packs (extensible)
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── rules_ssh.py
│   │   │   ├── rules_password.py
│   │   │   ├── rules_filesystem.py
│   │   │   └── rules_selinux.py
│   │   │
│   │   ├── constants/
│   │   │   ├── __init__.py
│   │   │   ├── record_status.py          # READY_FOR_PLAN, NEEDS_REVIEW, ...
│   │   │   ├── job_status.py
│   │   │   ├── task_codes.py
│   │   │   └── excel_columns.py
│   │   │
│   │   └── db/
│   │       ├── __init__.py
│   │       ├── session.py
│   │       └── seed_remediation_catalog.py
│   │
│   └── tests/
│       ├── unit/
│       └── integration/
│
├── frontend/                             # Next.js (or React + Vite)
│   ├── Dockerfile
│   ├── package.json
│   ├── src/
│   │   ├── app/                          # or pages/
│   │   │   ├── page.tsx                  # dashboard
│   │   │   ├── imports/
│   │   │   │   ├── page.tsx              # upload
│   │   │   │   └── [batchId]/page.tsx
│   │   │   ├── records/
│   │   │   ├── needs-review/
│   │   │   ├── plans/
│   │   │   ├── approvals/
│   │   │   └── jobs/
│   │   ├── components/
│   │   ├── lib/                          # API client
│   │   └── types/
│   └── public/
│
├── data/                                 # runtime volumes (gitignored)
│   ├── uploads/                          # uploaded Excel files
│   ├── ansible_private_data/             # Ansible Runner private_data_dir per job
│   └── tmp_inventories/                  # generated per-job inventories
│
└── scripts/
    ├── seed_dev.sh
    └── import_inventory_to_assets.py     # optional CLI helper
```

## Component responsibilities

| Path | Responsibility |
|------|----------------|
| `backend/app/api/` | HTTP only: authz checks, validation of IDs, enqueue work |
| `backend/app/services/` | Business rules: parse, classify, validate, plan, execute |
| `backend/app/workers/` | Celery entrypoints calling services |
| `backend/app/classifiers/` | Deterministic mapping rules → approved `task_code` |
| `ansible/playbooks/` | Approved remediation only; never generated from Excel |
| `ansible/inventories/` | Source for host/group mapping into `assets` |
| `data/` | Ephemeral runtime files; not source of truth |

## Docker Compose services (preview for Step 2)

| Service | Role | Notes |
|---------|------|-------|
| `backend` | FastAPI | No direct Ansible execution |
| `db` | PostgreSQL | Persistent volume |
| `redis` | Broker/result backend | Celery |
| `celery-worker` | Import + plan + Ansible Runner | Mount `./ansible` + `./data` |
| `frontend` | Optional UI | Talks to backend API only |

Important mount for `celery-worker` (same-server mode):

```text
./ansible  → /opt/ansible          (read-only recommended)
./data     → /var/lib/compliance   (read-write for uploads + runner private data)
```

Worker env (names only; values via `.env`):

- `ANSIBLE_HOME=/opt/ansible`
- `ANSIBLE_PLAYBOOKS_DIR=/opt/ansible/playbooks`
- `ANSIBLE_INVENTORIES_DIR=/opt/ansible/inventories`
- `RUNNER_PRIVATE_DATA_DIR=/var/lib/compliance/ansible_private_data`
- `UPLOAD_DIR=/var/lib/compliance/uploads`

## Data flow (same-server mode)

```text
Browser
  → Frontend
    → FastAPI (upload / approve / query)
      → PostgreSQL (metadata + audit)
      → Redis/Celery
        → Celery worker on Ansible control host
          → openpyxl read_only parse
          → classifier + validator
          → plan generator
          → Ansible Runner (check mode / apply)
            → approved playbook from ansible/playbooks/
            → inventory from ansible/inventories/ or temp job inventory
            → SSH to internal targets (existing Ansible access)
```

## Safety constraints encoded in structure

1. Excel `Remediation` column is input to **classifier only**, never to a shell executor.
2. Execution path is only: `task_code` → `remediation_catalog.playbook_path` → Ansible Runner.
3. No API endpoint under `api/` may accept or write playbook content.
4. Production jobs require dry-run success + approver action before `tasks_execute` can run apply mode.
5. Credentials live in Ansible/env/secret store — never in DB rows from Excel and never in source code.

## Why this layout

- **Clear trust boundary**: API process does not need Ansible SSH keys; worker does.
- **Chunked import ready**: parser service + Celery task isolated from request thread.
- **Catalog-driven execution**: `remediation_catalog` table maps `task_code` → playbook file under `ansible/playbooks/`.
- **Inventory bridge**: `inventory_sync` can populate/update `assets` from `ansible/inventories/*.ini`.
- **Future remote Ansible / AWX**: swap `ansible_runner_service` implementation; keep API/services/status model unchanged.

## Explicitly deferred to later steps

- Step 2: `docker-compose.yml` + Dockerfiles
- Step 3: DB schema / Alembic models
- Step 4+: API, Celery, classifier, plan, runner, playbooks, UI

## Review checklist for Step 1

Please confirm or adjust:

1. Backend package name: `backend/app` vs `backend/src/app`?
2. Frontend: **Next.js** (recommended default) or React + Vite?
3. Dependency management: **`pyproject.toml`** or `requirements.txt`?
4. Keep `ansible/` inside this repo (recommended for same-server start), or mount an existing host path like `/etc/ansible` via compose volume only?
5. Any existing inventory format beyond `.ini` (YAML inventory, dynamic inventory) that we must support in Step 3+?

After your review, Step 2 will create `docker-compose.yml` and service Dockerfiles only.

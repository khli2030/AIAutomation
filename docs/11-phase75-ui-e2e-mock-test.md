# Phase 7.5 — UI End-to-End Mock Test

## Goal

Prove the **operator UI** can drive the full mock remediation path with
**`MOCK_MODE=true`**, without real Ansible, ansible-runner, ansible-playbook,
subprocess, shell, or SSH.

This phase sits after Phase 7 (frontend) and Phase 6.5 (API E2E). Do **not**
start real Ansible integration until this UI mock workflow is accepted.

## Safety

| Rule | Status |
|------|--------|
| `MOCK_MODE=true` | Required |
| No ansible-runner / ansible-playbook | Required |
| No subprocess / shell / SSH from UI | Required |
| No playbook editor | Required |
| AI `generated_playbook` read-only / non-executable | Required |
| `ADMIN_TOKEN` not hardcoded in committed code | Required |

Playwright tests in this phase **intercept** backend HTTP with a stateful mock
so CI can run without Docker/Postgres. Manual steps below exercise the **real**
backend + frontend stack (still `MOCK_MODE=true`).

## How to start the backend

```bash
cd /path/to/AIAutomation
cp .env.example .env
# Set strong ADMIN_TOKEN and SECRET_KEY
# Keep MOCK_MODE=true

docker compose up -d --build db redis backend celery-worker
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.db.seed_cli
```

Health check:

```bash
curl -s http://127.0.0.1:8000/health
# {"status":"ok"}
```

Optional API smoke (Phase 6.5):

```bash
export ADMIN_TOKEN=...   # from .env
./scripts/e2e_mock_workflow.sh
```

## How to start the frontend

```bash
cd frontend
cp .env.example .env.local
# NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
# Do NOT commit ADMIN_TOKEN. Prefer Settings → sessionStorage.

npm install
npm run dev
```

Open `http://127.0.0.1:3000` → **Settings** → paste `ADMIN_TOKEN`.

Compose profile (optional):

```bash
docker compose --profile frontend up -d --build frontend
```

## Required environment variables

| Variable | Where | Purpose |
|----------|-------|---------|
| `MOCK_MODE=true` | backend `.env` | Force mock execution path |
| `ADMIN_TOKEN` | backend `.env` | API auth (never commit a real value) |
| `DATABASE_URL` | backend / compose | Postgres |
| `CELERY_BROKER_URL` | backend / compose | Redis for Excel parse |
| `NEXT_PUBLIC_API_URL` | frontend `.env.local` | Browser → API (`http://127.0.0.1:8000`) |
| `NEXT_PUBLIC_ADMIN_TOKEN` | frontend `.env.local` (optional, gitignored) | Lab-only; prefer sessionStorage |

**Auth note:** sessionStorage / `NEXT_PUBLIC_ADMIN_TOKEN` is **MVP / lab-only**,
not production authentication.

## Automated Playwright happy path

Runs against a local Next.js server. Backend calls are **mocked in-browser**
(no real Ansible). Still validates UI gates, banners, and page flow.

```bash
cd frontend
npm install
npx playwright install chromium   # once per machine
npm run test:e2e
```

What it covers (mapped to the required workflow):

1. Open Dashboard  
2. Confirm MOCK_MODE banner  
3. Upload sample Excel  
4. Open Import Summary  
5. Validate batch  
6. Confirm READY_FOR_PLAN (Records Review filters)  
7. Open Records Review  
8. Generate execution plan  
9. Open Execution Plans  
10. Open a job (Approvals)  
11. Run mock dry-run  
12. Confirm `result_type=dry_run` results  
13. Approve after `dry_run_success`  
14. Run mock execution  
15. Confirm `result_type=run` results  
16. Confirm final status `success` (mock)  
17. Confirm no playbook editor on any page  
18. Confirm AI `generated_playbook` is read-only / non-executable  

Artifacts: `frontend/playwright-report/` (gitignored).

## Manual UI test flow (real backend + frontend)

Use this when Compose is up and Celery can parse Excel.

### Preconditions

- Backend healthy on `127.0.0.1:8000`
- Frontend on `127.0.0.1:3000`
- Token set in Settings
- Catalog + lab assets seeded (`python -m app.db.seed_cli`)
- Sample hosts `e2e-linux-01` / `e2e-linux-02` present
- `MOCK_MODE` banner visible on every page

### Steps and expected results

| # | Action | Expected |
|---|--------|----------|
| 1 | Open `/` Dashboard | Counters load (or empty zeros); no errors |
| 2 | Check top banner | Orange **MOCK_MODE** banner: no ansible-runner/playbook/subprocess/SSH |
| 3 | `/upload` → choose Qualys-style `.xlsx` with PermitRootLogin rows for `e2e-linux-01/02` → Upload | Shows `batch_id`, status `uploaded`/`parsed` |
| 4 | Open Import Summary for that batch | `total_records` / `valid_records` / `invalid_records` / status visible |
| 5 | Click **Validate batch** (after `parsed`) | Summary shows `ready_for_plan ≥ 1` |
| 6 | Confirm READY_FOR_PLAN | Records Review filter `READY_FOR_PLAN` lists devices |
| 7 | Open Records Review | Filters work; Remediation / Expected Configuration display-only |
| 8 | Import Summary → **Generate plan** | Plan id shown; jobs created |
| 9 | Open Execution Plans | Plan lists job count / target count |
| 10 | Open job via Approvals | Job status `waiting_dry_run` |
| 11 | **Run mock dry-run** | Message includes `mock_mode=true`; status → `dry_run_success` |
| 12 | Dry-run results table | Hosts listed; `result_type=dry_run` |
| 13 | **Approve** | Enabled only after `dry_run_success`; status → `approved` |
| 14 | **Run mock execution** | Enabled only when `approved`; `mock_mode=true` |
| 15 | Job Results page | Separate **dry_run** and **run** sections |
| 16 | Final status | `success`, `failed`, or `partially_failed` |
| 17 | Spot-check all nav pages | No playbook edit/save controls |
| 18 | AI Suggestions | `generated_playbook (read-only)`; no execute; convert uses disabled catalog |

### Sample Excel tip

Reuse the generator from `scripts/e2e_mock_workflow.sh` (creates
`e2e-linux-01/02` + PermitRootLogin text), or upload any workbook matching
Phase 2 required columns.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Banner says set ADMIN_TOKEN | Token missing | Settings → paste token from backend `.env` |
| 401 on API calls | Wrong token / CORS | Match `ADMIN_TOKEN`; API URL `http://127.0.0.1:8000` |
| Upload stuck `uploaded`/`parsing` | Celery down | `docker compose up -d celery-worker` |
| Validate → `ASSET_NOT_FOUND` | Assets not seeded | `docker compose exec backend python -m app.db.seed_cli` |
| Generate plan → 0 jobs | No READY_FOR_PLAN or catalog disabled | Validate first; ensure `SSH_DISABLE_ROOT_LOGIN` enabled |
| Approve disabled | Dry-run not successful | Run mock dry-run; status must be `dry_run_success` |
| Run disabled | Not approved | Approve after dry-run success |
| Playwright fails starting Next | Port busy | `UI_E2E_PORT=3101 npm run test:e2e` |
| Playwright browser missing | Chromium not installed | `npx playwright install chromium` |

## Out of scope

- Real Ansible Runner / `MOCK_MODE=false`
- Production auth (SSO/OIDC)
- Frontend playbook authoring
- Enabling AI drafts for execution

## Related docs

- [`10-phase65-e2e-mock-workflow.md`](./10-phase65-e2e-mock-workflow.md) — API E2E
- [`11-phase7-frontend.md`](./11-phase7-frontend.md) — UI pages + list APIs
- [`frontend/README.md`](../frontend/README.md) — local frontend run

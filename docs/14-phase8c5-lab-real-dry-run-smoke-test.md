# Phase 8C.5 — Lab Real Dry-run Smoke Test

## Goal

Document a **manual lab smoke test** for Phase 8C real Ansible **dry-run only**
(`ansible-runner` with `--check`). Prove the guarded path works on the internal
Ansible control server without enabling production/staging or real apply/run.

This phase is **documentation + checklist only**. It does **not** implement
real apply/run and does **not** change default safety settings.

Companion checklist script (does **not** run Ansible unless you explicitly
confirm):

```bash
./scripts/lab_real_dry_run_checklist.sh
```

## Explicit non-goals

| Non-goal | Status |
|----------|--------|
| Real apply / run (`POST /execution-jobs/{id}/run` live path) | **Not implemented** — still blocked (`apply_blocked_phase8c`) |
| Enabling production or staging targets | **Blocked** |
| Changing defaults (`MOCK_MODE=true`, `REAL_ANSIBLE_ENABLED=false`) | **Unchanged** |
| Auto-running ansible-runner from the checklist script | **Forbidden** unless operator confirms |

## Safety summary

| Rule | Expected |
|------|----------|
| Check mode only (`cmdline="--check"`) | Required |
| No system changes from dry-run | Expected (Ansible check mode) |
| Production / staging targets | Blocked |
| `APP_ENV=production` | Blocked |
| Empty targets | Blocked (`missing_targets`) |
| AI `generated_playbook` / Excel Remediation text | Never executed |
| Defaults after the smoke test | Restore `MOCK_MODE=true`, `REAL_ANSIBLE_ENABLED=false` |

## Required environment variables (lab smoke only)

Set these **only** on the internal Ansible control server for the smoke window.
Do **not** commit them as defaults.

| Variable | Exact value for smoke | Notes |
|----------|----------------------|--------|
| `MOCK_MODE` | `false` | Required for real adapter |
| `REAL_ANSIBLE_ENABLED` | `true` | Second gate |
| `APP_ENV` | `lab` | Must be `lab` or `test` (`lab` preferred for this checklist) |

Also required (unchanged from normal ops):

| Variable | Purpose |
|----------|---------|
| `ADMIN_TOKEN` / `OPERATOR_TOKEN` | Auth for dry-run (`operator` or `admin`) |
| `VIEWER_TOKEN` (or any read role) | Preflight / results inspection |
| `RUNNER_PRIVATE_DATA_DIR` | Default `/var/lib/compliance/ansible_private_data` (host: `./data/...`) |
| `ANSIBLE_PLAYBOOKS_DIR` | Default `/opt/ansible/playbooks` |
| `ANSIBLE_INVENTORIES_DIR` | Default `/opt/ansible/inventories` |

Example `.env` fragment for the smoke window (lab host only):

```bash
APP_ENV=lab
MOCK_MODE=false
REAL_ANSIBLE_ENABLED=true
```

After the smoke test, restore safe defaults:

```bash
APP_ENV=development   # or lab with gates off
MOCK_MODE=true
REAL_ANSIBLE_ENABLED=false
```

Then recreate/restart backend and celery-worker so settings reload.

## Target environment rules

**All** job targets (and the job environment when set) must be `environment=lab`
or `environment=test`.

| Environment | Real dry-run |
|-------------|--------------|
| `lab` | Allowed |
| `test` | Allowed |
| `staging` | **Blocked** |
| `production` / `prod` | **Blocked** |

Seeded MVP assets (`python -m app.db.seed_cli`):

| Device | environment | Use for real dry-run? |
|--------|-------------|------------------------|
| `e2e-linux-01` | `test` | Yes |
| `e2e-linux-02` | `test` | Yes |
| `e2e-linux-03` | `staging` | **No** — will block real dry-run |

Inventory for lab/test maps to `ansible/inventories/test.ini` only. Ensure that
file lists the 1–3 lab hosts you intend to limit (placeholders alone will not
reach real SSH targets).

## Prerequisites

1. Internal Ansible control server (not a laptop mock-only setup).
2. Stack up: `db`, `redis`, `backend`, `celery-worker` (Celery not required for
   dry-run itself; needed if you create jobs via Excel import).
3. Migrations + seed:

   ```bash
   docker compose exec backend alembic upgrade head
   docker compose exec backend python -m app.db.seed_cli
   ```

4. Enabled catalog playbook present (default: `SSH_DISABLE_ROOT_LOGIN` →
   `ssh_disable_root_login.yml`).
5. Lab hosts reachable from the control server with the inventory SSH user
   (check mode still needs connectivity for facts/modules that contact hosts).
6. `ansible-runner` installed in the backend/celery image/venv.

## Checklist overview

1. Configure lab env vars (above) and restart API workers.
2. Run `GET /ansible/preflight` — must report readiness / no blockers for the
   real path you intend.
3. Create or select a **small** lab job with **1–3 targets** only (`lab`/`test`).
4. Confirm job status is `waiting_dry_run`.
5. Run real dry-run: `POST /execution-jobs/{id}/dry-run`.
6. Inspect `job_results` (`result_type=dry_run`), `audit_logs`, and runner
   artifacts under `RUNNER_PRIVATE_DATA_DIR`.
7. Confirm safe behaviour (check mode, no apply, prod/staging still blocked).
8. Restore `MOCK_MODE=true` and `REAL_ANSIBLE_ENABLED=false`.

Use the script to print this checklist and optionally call **preflight only**:

```bash
export ADMIN_TOKEN=...   # or OPERATOR_TOKEN / VIEWER_TOKEN for preflight
./scripts/lab_real_dry_run_checklist.sh
```

To have the script print the dry-run `curl` and optionally **execute** that
single HTTP dry-run call, you must set an explicit confirmation (see script
header). The script never invokes `ansible-playbook`, `ansible-runner`, or
subprocess Ansible directly.

---

## 1. Configure lab environment

On the Ansible control server:

```bash
cd /path/to/AIAutomation
# Edit .env — set exactly:
#   APP_ENV=lab
#   MOCK_MODE=false
#   REAL_ANSIBLE_ENABLED=true

docker compose up -d --build backend celery-worker
# Confirm settings inside the container:
docker compose exec backend printenv MOCK_MODE REAL_ANSIBLE_ENABLED APP_ENV
# Expect: false / true / lab
```

**Keep production/staging blocked:** do not set `APP_ENV=production`. Do not
include staging/production assets in the job.

---

## 2. Run `/ansible/preflight`

Read-only. Does **not** execute Ansible or ansible-runner.

```bash
export API_BASE="${API_BASE:-http://127.0.0.1:8000}"
export TOKEN="${VIEWER_TOKEN:-$ADMIN_TOKEN}"

curl -sS "${API_BASE}/ansible/preflight" \
  -H "X-Admin-Token: ${TOKEN}" | jq .
```

Expect roughly:

- `mock_mode`: `false`
- `real_ansible_enabled`: `true`
- `app_env`: `lab`
- `real_ansible_allowed`: `true`
- `blockers`: `[]`
- checks for ansible-runner availability, playbooks/inventories dirs, enabled
  catalog playbook files, writable runtime dirs

If `real_ansible_allowed` is `false`, **stop**. Fix blockers before dry-run.

---

## 3. Create or select a small lab job (1–3 targets)

### Preferred: reuse an existing `waiting_dry_run` job

```bash
# List jobs (operator/admin/viewer as allowed by your RBAC)
curl -sS "${API_BASE}/execution-jobs" \
  -H "X-Admin-Token: ${TOKEN}" | jq .
```

Pick a job where:

- `status` is `waiting_dry_run`
- target count is **1–3**
- every target `environment` is `lab` or `test`
- catalog task is enabled (e.g. `SSH_DISABLE_ROOT_LOGIN`)

### Create via mock E2E path then filter targets

You may generate a plan with the normal import → validate → plan flow
(`./scripts/e2e_mock_workflow.sh` while still in mock mode, **or** UI), then
ensure the resulting job only includes `e2e-linux-01` / `e2e-linux-02` (not
`e2e-linux-03` staging).

**Hard limit for this smoke test:** 1–3 hosts. Never dry-run against a large
inventory without `--limit` — the API always requires explicit job targets and
passes them as ansible-runner `limit`.

Inspect job detail:

```bash
JOB_ID=...   # set to your job id
curl -sS "${API_BASE}/execution-jobs/${JOB_ID}" \
  -H "X-Admin-Token: ${TOKEN}" | jq '{id, status, environment, dry_run_status, task_code}'
```

Confirm targets (via plan/job UI or DB) are only lab/test hosts.

---

## 4. Run real dry-run

Operator or admin role required.

```bash
export OPERATOR_TOKEN="${OPERATOR_TOKEN:-$ADMIN_TOKEN}"
JOB_ID=...   # waiting_dry_run job with 1–3 lab/test targets

curl -sS -X POST "${API_BASE}/execution-jobs/${JOB_ID}/dry-run" \
  -H "X-Admin-Token: ${OPERATOR_TOKEN}" | jq .
```

What the platform does (Phase 8C):

1. Gates: `MOCK_MODE=false`, `REAL_ANSIBLE_ENABLED=true`, `APP_ENV` in `{lab,test}`
2. All targets `environment` in `{lab,test}` (production/staging blocked)
3. Preflight must pass
4. Non-empty targets required
5. `ansible_runner.run(..., cmdline="--check", limit=<targets>)`
6. Persist `job_results` with `result_type=dry_run`
7. Audit: `real_dry_run_started` → `real_dry_run_completed` or `*_failed` / `*_blocked`

**Do not** call `POST /execution-jobs/{id}/run` for this smoke test. Real apply
remains blocked in Phase 8C.

---

## 5. Inspect results

### 5.1 `job_results` where `result_type=dry_run`

```bash
curl -sS "${API_BASE}/execution-jobs/${JOB_ID}/results?result_type=dry_run" \
  -H "X-Admin-Token: ${TOKEN}" | jq .
```

Expect per-host rows with `result_type=dry_run` (not invented success if host
events were missing — incomplete parse fails safely).

SQL (optional, on the DB container):

```bash
docker compose exec db psql -U compliance -d compliance -c \
  "SELECT id, execution_job_id, device_name, status, result_type
   FROM job_results
   WHERE execution_job_id = ${JOB_ID} AND result_type = 'dry_run'
   ORDER BY id;"
```

### 5.2 `audit_logs`

There is no dedicated public audit list API in MVP; inspect via SQL:

```bash
docker compose exec db psql -U compliance -d compliance -c \
  "SELECT id, actor, action, entity_type, entity_id, details, created_at
   FROM audit_logs
   WHERE entity_type = 'execution_job' AND entity_id = '${JOB_ID}'
   ORDER BY id DESC
   LIMIT 20;"
```

Look for JSON `event` values in `details`:

| Event | Meaning |
|-------|---------|
| `real_dry_run_started` | Gates passed; runner about to run |
| `real_dry_run_completed` | Persisted successfully |
| `real_dry_run_failed` | Runner / parse / unexpected error |
| `real_dry_run_blocked` | Safety gate refusal (before or instead of start) |

Blocked attempts for production/staging must **not** emit
`real_dry_run_started`.

### 5.3 ansible-runner artifacts

Private data dir pattern:

```text
{RUNNER_PRIVATE_DATA_DIR}/job-{JOB_ID}-dry-run/
```

Compose default: host `./data/ansible_private_data/job-{JOB_ID}-dry-run/`
(container `/var/lib/compliance/ansible_private_data/job-{JOB_ID}-dry-run/`).

```bash
JOB_ID=...
ls -la "./data/ansible_private_data/job-${JOB_ID}-dry-run/" || \
  docker compose exec backend ls -la \
    "/var/lib/compliance/ansible_private_data/job-${JOB_ID}-dry-run/"
```

Typical ansible-runner layout under that directory: `artifacts/`, stdout/stderr
captures, event JSON. Confirm check-mode invocation (no live apply cmdline).

---

## 6. Expected safe behaviour

| Behaviour | Pass criteria |
|-----------|----------------|
| No system changes | Ansible `--check` only; modules should not modify hosts |
| Check mode only | Runner kwargs include `cmdline="--check"` |
| Production/staging blocked | Jobs with those target envs refuse with blocked audit |
| No real apply | `POST .../run` still blocked for real path |
| Empty targets blocked | `missing_targets` — no unbounded inventory run |
| Incomplete host events | Fail safely (`host_parse_incomplete`) — no fake success |
| Defaults restored | After smoke: `MOCK_MODE=true`, `REAL_ANSIBLE_ENABLED=false` |

Optional negative checks (still lab only):

```bash
# Staging target job must fail closed (do not use production hosts).
# Expect 400 + real_dry_run_blocked — never real_dry_run_started.
```

---

## 7. Troubleshooting

### ansible-runner missing

**Symptoms:** preflight check fails; dry-run raises missing-runner error; no
silent fallback to `ansible-playbook`.

**Fix:** Install `ansible-runner` in the backend image/venv; rebuild containers;
re-run preflight until the availability check is OK.

### playbook missing

**Symptoms:** preflight `enabled_catalog_playbooks` fails; dry-run
`playbook_missing` / path error.

**Fix:** Ensure catalog `ansible_playbook_path` exists under
`ansible/playbooks` (mounted RO at `/opt/ansible/playbooks`). Only enabled
catalog entries are used — never AI drafts.

### inventory path blocked

**Symptoms:** `inventory_env_blocked` / `inventory_missing`; path traversal
blocked.

**Fix:** Job environment must map to lab/test → `test.ini` under
`ansible/inventories`. Do not point outside that tree. Production/staging
inventory files are not selected by the real dry-run path for lab/test jobs.

### host events incomplete

**Symptoms:** dry-run fails with `host_parse_incomplete` even if runner exited;
audit `real_dry_run_failed`.

**Fix:** Ensure `--limit` hosts appear in runner events
(`runner_on_ok` / `failed` / `skipped` / `unreachable`). Check connectivity,
inventory hostnames matching `device_name`, and artifact event logs. Do **not**
treat missing events as success.

### empty targets blocked

**Symptoms:** `missing_targets` — refusing unbounded inventory check-mode.

**Fix:** Attach 1–3 explicit job targets before dry-run. Never rely on full
inventory without limit.

### preflight failure

**Symptoms:** `real_ansible_allowed=false`; dry-run `preflight_failed`.

**Fix:** Read `blockers` from `GET /ansible/preflight`. Common causes: still
`MOCK_MODE=true`, `REAL_ANSIBLE_ENABLED=false`, wrong `APP_ENV`, missing dirs,
unreadable playbooks, non-writable `RUNNER_PRIVATE_DATA_DIR` /
`TMP_INVENTORY_DIR`, missing ansible-runner package.

---

## 8. Rollback / restore notes

Dry-run **should not** change target systems (check mode). Still document
restore steps:

1. **Platform settings:** set `MOCK_MODE=true` and `REAL_ANSIBLE_ENABLED=false`;
   restart `backend` and `celery-worker`.
2. **Confirm gates:** `GET /ansible/preflight` should show real Ansible blocked
   again when defaults are restored.
3. **Job state:** if a job is left in `dry_run_failed` / `waiting_dry_run`,
   reject or leave for operators — do not “fix” with real apply.
4. **Artifacts:** optional cleanup of
   `./data/ansible_private_data/job-*-dry-run/` after review (keep if auditing).
5. **If a module unexpectedly changed a host** (misconfigured playbook ignoring
   check mode): restore from your lab VM snapshot / config-management baseline.
   Prefer lab VMs with snapshots for this smoke test.
6. **Do not** enable production remediation to “undo” a lab test.

---

## Related docs

- [`docs/14-phase8c-lab-real-dry-run.md`](14-phase8c-lab-real-dry-run.md) — Phase 8C behaviour
- [`docs/13-phase8b-real-ansible-readiness.md`](13-phase8b-real-ansible-readiness.md) — gates + preflight
- [`docs/10-phase65-e2e-mock-workflow.md`](10-phase65-e2e-mock-workflow.md) — mock job creation path
- [`DEPLOYMENT.md`](../DEPLOYMENT.md) — control-server deployment

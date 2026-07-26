# Real Ansible Single-Host Lab Pilot (Phase 10C)

Controlled **single-host** lab pilot for connectivity checks and **check-mode**
real dry-run against explicitly allowlisted hosts.

This does **not** enable production execution or real apply/remediation.

## Safety defaults (do not change lightly)

| Setting | Default |
|---------|---------|
| `MOCK_MODE` | `true` |
| `REAL_ANSIBLE_ENABLED` | `false` |
| `REAL_ANSIBLE_CHECK_MODE_ONLY` | `true` |
| `REAL_ANSIBLE_PILOT_MODE` | `false` |
| `REAL_ANSIBLE_MAX_HOSTS_PER_RUN` | `1` |
| `REAL_ANSIBLE_AUTH_MODE` | `explicit` |
| `REAL_ANSIBLE_ALLOWED_HOSTS` | empty |
| `REAL_ANSIBLE_ALLOWED_TASK_CODES` | empty |

**Warnings**

- Never commit private keys or production inventory.
- Never put real secrets in `.env.example` or git.
- Excel Remediation text and AI suggestions are never executed.
- Phase 10C is single-host connectivity / check-mode only — **no real apply endpoint**.
- **Do not use production or critical hosts** for this pilot.

## Single-host pilot checklist

1. Provision **one** disposable Linux lab VM on an isolated network.
2. Install Python 3 and ensure SSH key auth from the Ansible control host.
3. Pick a stable inventory name (example: `lab-server-01`).
4. Copy example inventory locally — never commit the real inventory file.
5. Configure `.env` on the lab control host only (see example below).
6. Verify `GET /ansible/safety-status` and `GET /ansible/pilot-readiness`.
7. Run connectivity check against the single allowlisted host.
8. Run real dry-run only for a job with **one** target and an allowlisted task code.
9. Keep rollback settings ready (see below).

## Environment variable example

```bash
cp .env.example .env
# Edit .env on the lab control host — keep secrets out of git.
```

### Option A — explicit user/key (default)

```bash
MOCK_MODE=false
REAL_ANSIBLE_ENABLED=true
REAL_ANSIBLE_CHECK_MODE_ONLY=true
REAL_ANSIBLE_PILOT_MODE=true
REAL_ANSIBLE_MAX_HOSTS_PER_RUN=1
REAL_ANSIBLE_AUTH_MODE=explicit
APP_ENV=lab

REAL_ANSIBLE_ALLOWED_HOSTS=lab-server-01
REAL_ANSIBLE_ALLOWED_TASK_CODES=AIDE_INSTALL,SSH_MAX_AUTH_TRIES

REAL_ANSIBLE_INVENTORY_PATH=/var/lib/compliance/lab.ini
REAL_ANSIBLE_PRIVATE_KEY_PATH=/var/lib/compliance/keys/lab_id_ed25519
REAL_ANSIBLE_REMOTE_USER=labuser
REAL_ANSIBLE_TIMEOUT_SECONDS=120
```

### Option B — SSH config / inventory / agent (control host already has SSH)

Use when the Ansible control server already reaches lab hosts via `~/.ssh/config`,
inventory `ansible_user` / `ansible_ssh_private_key_file`, or ssh-agent — without
passing username/key on the CLI:

```bash
MOCK_MODE=false
REAL_ANSIBLE_ENABLED=true
REAL_ANSIBLE_CHECK_MODE_ONLY=true
REAL_ANSIBLE_PILOT_MODE=true
REAL_ANSIBLE_MAX_HOSTS_PER_RUN=1
REAL_ANSIBLE_AUTH_MODE=ssh_config
APP_ENV=lab

REAL_ANSIBLE_ALLOWED_HOSTS=lab-server-01
REAL_ANSIBLE_ALLOWED_TASK_CODES=AIDE_INSTALL,SSH_MAX_AUTH_TRIES

REAL_ANSIBLE_INVENTORY_PATH=/var/lib/compliance/lab.ini
# REMOTE_USER and PRIVATE_KEY_PATH are NOT required in ssh_config mode.
# Leave them unset; the API will not inject --user / --private-key.
REAL_ANSIBLE_TIMEOUT_SECONDS=120
```

In `ssh_config` mode, connectivity and real dry-run still require inventory,
allowlists, pilot mode, check-mode-only, and max-hosts enforcement. They never
expose private key contents in API responses.

Copy the example inventory and edit locally:

```bash
cp ansible/inventory/lab.example.ini /var/lib/compliance/lab.ini
# Edit hostnames/IPs for your lab only — never commit that file.
```

## Verify safety-status

```bash
curl -sS -H "X-Admin-Token: $ADMIN_TOKEN" \
  http://127.0.0.1:8000/ansible/safety-status | jq .
```

Expect when pilot is correctly configured:

- `pilot_mode=true`
- `max_hosts_per_run=1`
- `single_host_pilot_qualified=true`
- `real_execution_available=true`
- `check_mode_only=true`

Also:

```bash
curl -sS -H "X-Admin-Token: $ADMIN_TOKEN" \
  http://127.0.0.1:8000/ansible/lab-config-preview | jq .
```

`lab-config-preview` returns sanitized fields only (`pilot_ready`,
`pilot_readiness_errors`, allowlists, validation). It never returns private key
contents or secret path material.

## Verify pilot-readiness

```bash
curl -sS -H "X-Admin-Token: $ADMIN_TOKEN" \
  http://127.0.0.1:8000/ansible/pilot-readiness | jq .
```

Returns:

- `ready` true/false
- `mock_mode`, `real_ansible_enabled`, `check_mode_only`, `pilot_mode`
- `max_hosts_per_run`
- `allowed_hosts`, `allowed_task_codes`
- inventory / remote user / private key configured flags
- `errors`, `warnings`

With stock defaults, `ready=false` and errors explain why.

## Run connectivity-check

Operator/admin only. Blocked by default when pilot mode / real Ansible is disabled.
Enforces allowlist **and** `REAL_ANSIBLE_MAX_HOSTS_PER_RUN` (default 1).
Does **not** run any playbook.

```bash
curl -sS -X POST -H "X-Admin-Token: $OPERATOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"hosts":["lab-server-01"]}' \
  http://127.0.0.1:8000/ansible/connectivity-check | jq .
```

Behavior:

- Only allowlisted hosts may be checked
- Host count capped by `REAL_ANSIBLE_MAX_HOSTS_PER_RUN`
- Uses Ansible `ping` module (no playbook apply)
- Captures stdout/stderr
- Writes audit events (`real_connectivity_check_*` / `real_execution_blocked`)

## Run real dry-run

Check-mode only. Job must have ≤ `REAL_ANSIBLE_MAX_HOSTS_PER_RUN` targets,
allowlisted host(s), and allowlisted catalog task code. Never executes Excel
Remediation text or AI suggestions.

```bash
curl -sS -X POST -H "X-Admin-Token: $OPERATOR_TOKEN" \
  http://127.0.0.1:8000/execution-jobs/<job_id>/real-dry-run | jq .
```

Results are stored with `result_type=real_dry_run`. Audit events are written for
start/complete/block.

UI: Plan Detail shows **Real Ansible Dry Run — Single Host Check Mode** only when
pilot readiness is green and the job target count fits the max-hosts cap.

## Confirm blocked behavior (defaults)

With stock defaults (`MOCK_MODE=true`, `REAL_ANSIBLE_ENABLED=false`,
`REAL_ANSIBLE_PILOT_MODE=false`, empty allowlists):

- `GET /ansible/pilot-readiness` → `ready=false` + clear errors
- `GET /ansible/safety-status` → `real_execution_available=false` + reasons
- `GET /ansible/lab-config-preview` → `pilot_ready=false`, `validation_status=blocked`
- `POST /ansible/connectivity-check` → `blocked=true` + audit `real_execution_blocked`
- Jobs with more than one target → real dry-run blocked / UI button hidden
- No real apply endpoint exists

## Rollback / stop instructions

To immediately stop the pilot on the control host:

```bash
# Preferred: restore safe defaults in .env and restart the API
MOCK_MODE=true
REAL_ANSIBLE_ENABLED=false
REAL_ANSIBLE_PILOT_MODE=false
REAL_ANSIBLE_CHECK_MODE_ONLY=true
REAL_ANSIBLE_MAX_HOSTS_PER_RUN=1
REAL_ANSIBLE_ALLOWED_HOSTS=
REAL_ANSIBLE_ALLOWED_TASK_CODES=
```

Or unset lab inventory/key paths and restart. Connectivity and real dry-run will
block again; mock dry-run / approval flows remain available.

## Related docs

- [`docs/20-phase10c-single-host-pilot.md`](20-phase10c-single-host-pilot.md)
- [`docs/19-phase10b-lab-inventory-connectivity.md`](19-phase10b-lab-inventory-connectivity.md)
- [`docs/18-phase10a-real-ansible-pilot-prep.md`](18-phase10a-real-ansible-pilot-prep.md)
- [`docs/14-phase8c-lab-real-dry-run.md`](14-phase8c-lab-real-dry-run.md)

# Real Ansible Lab Connectivity Pilot (Phase 10B)

Lab-only preparation for **connectivity checks** against explicitly allowlisted hosts.
This does **not** enable production execution or real apply/remediation.

## Safety defaults (do not change lightly)

| Setting | Default |
|---------|---------|
| `MOCK_MODE` | `true` |
| `REAL_ANSIBLE_ENABLED` | `false` |
| `REAL_ANSIBLE_CHECK_MODE_ONLY` | `true` |
| `REAL_ANSIBLE_ALLOWED_HOSTS` | empty |
| `REAL_ANSIBLE_ALLOWED_TASK_CODES` | empty |

**Warnings**

- Never commit private keys or production inventory.
- Never put real secrets in `.env.example` or git.
- Excel Remediation text and AI suggestions are never executed.
- Phase 10B is connectivity / check-mode preparation only — no real apply endpoint.

## 1. Create a lab host

1. Provision a disposable Linux lab VM on an isolated network.
2. Install Python 3 and ensure SSH key auth from the Ansible control host.
3. Pick a stable inventory name (example: `lab-server-01`).
4. Do **not** reuse production hosts or production inventory files.

## 2. Configure `.env` locally (lab control host only)

```bash
cp .env.example .env
# Edit .env on the lab control host — keep secrets out of git.
```

For a controlled lab pilot (still check-mode / connectivity only):

```bash
MOCK_MODE=false
REAL_ANSIBLE_ENABLED=true
REAL_ANSIBLE_CHECK_MODE_ONLY=true
APP_ENV=lab

REAL_ANSIBLE_ALLOWED_HOSTS=lab-server-01
REAL_ANSIBLE_ALLOWED_TASK_CODES=AIDE_INSTALL,SSH_MAX_AUTH_TRIES

REAL_ANSIBLE_INVENTORY_PATH=/var/lib/compliance/lab.ini
REAL_ANSIBLE_PRIVATE_KEY_PATH=/var/lib/compliance/keys/lab_id_ed25519
REAL_ANSIBLE_REMOTE_USER=labuser
REAL_ANSIBLE_TIMEOUT_SECONDS=120
```

Copy the example inventory and edit locally:

```bash
cp ansible/inventory/lab.example.ini /var/lib/compliance/lab.ini
# Edit hostnames/IPs for your lab only — never commit that file.
```

## 3. Allowlisted hosts

`REAL_ANSIBLE_ALLOWED_HOSTS` is a comma-separated list. Examples:

```bash
REAL_ANSIBLE_ALLOWED_HOSTS=lab-server-01
REAL_ANSIBLE_ALLOWED_HOSTS=lab-server-01,10.10.10.15
```

Hosts not on this list are blocked for connectivity and real dry-run.

## 4. Allowlisted task codes

`REAL_ANSIBLE_ALLOWED_TASK_CODES` is a comma-separated list of catalog task codes:

```bash
REAL_ANSIBLE_ALLOWED_TASK_CODES=AIDE_INSTALL,SSH_MAX_AUTH_TRIES
```

Unknown codes (not in `remediation_catalog`) are rejected by lab config validation.
Never substitute Excel Remediation text or AI draft playbooks.

## 5. Run safety-status

```bash
curl -sS -H "X-Admin-Token: $ADMIN_TOKEN" \
  http://127.0.0.1:8000/ansible/safety-status | jq .
```

Also available:

```bash
curl -sS -H "X-Admin-Token: $ADMIN_TOKEN" \
  http://127.0.0.1:8000/ansible/lab-config-preview | jq .
```

`lab-config-preview` returns sanitized fields only (booleans + allowlists + validation errors).
It never returns private key contents or secret path material.

## 6. Run connectivity-check

Operator/admin only. Blocked by default when real Ansible is disabled.

```bash
curl -sS -X POST -H "X-Admin-Token: $OPERATOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"hosts":["lab-server-01"]}' \
  http://127.0.0.1:8000/ansible/connectivity-check | jq .
```

Behavior:

- Only allowlisted hosts may be checked
- Uses Ansible `ping` module (no playbook apply)
- Captures stdout/stderr
- Writes audit events (`real_connectivity_check_*` / `real_execution_blocked`)

## 7. Confirm blocked behavior (defaults)

With stock defaults (`MOCK_MODE=true`, `REAL_ANSIBLE_ENABLED=false`, empty allowlists):

- `GET /ansible/safety-status` → `real_execution_available=false` + clear reasons
- `GET /ansible/lab-config-preview` → `validation_status=blocked`
- `POST /ansible/connectivity-check` → `blocked=true` + audit `real_execution_blocked`
- Non-allowlisted hosts → blocked even if real Ansible is later enabled
- UI Safety page shows validation errors and disables connectivity when unavailable

## Related docs

- [`docs/18-phase10a-real-ansible-pilot-prep.md`](18-phase10a-real-ansible-pilot-prep.md)
- [`docs/14-phase8c-lab-real-dry-run.md`](14-phase8c-lab-real-dry-run.md)

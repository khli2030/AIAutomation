# Phase 11B — SSH Delegated Ansible Execution Mode

Temporary safe mode for local app development when the full stack cannot run
on the INFRA-OPS Ansible control node (Podman/Docker Hub/proxy limits).

## Defaults (unchanged safety posture)

- `MOCK_MODE=true`
- `REAL_ANSIBLE_ENABLED=false`
- `REAL_ANSIBLE_CHECK_MODE_ONLY=true`
- `REAL_ANSIBLE_PILOT_MODE=false`
- `REAL_ANSIBLE_EXECUTION_MODE=local`
- No real apply endpoint

## Execution modes

| Mode | Behavior |
|------|----------|
| `local` (default) | ansible-runner on the app host |
| `ssh_delegate` | SSH (`BatchMode=yes`) to INFRA-OPS; run `ansible` / `ansible-playbook` there |

## ssh_delegate settings

```bash
REAL_ANSIBLE_EXECUTION_MODE=ssh_delegate
REAL_ANSIBLE_CONTROL_NODE_HOST=infra-ops.example.internal
REAL_ANSIBLE_CONTROL_NODE_USER=ansible   # optional
REAL_ANSIBLE_CONTROL_NODE_WORKDIR=/opt/compliance
REAL_ANSIBLE_CONTROL_NODE_TIMEOUT_SECONDS=120

# Inventory / playbook paths are interpreted on the control node:
REAL_ANSIBLE_INVENTORY_PATH=/opt/compliance/lab.ini
REAL_ANSIBLE_AUTH_MODE=ssh_config
```

All existing gates still apply: enable flags, allowlists, max hosts, stub block,
high-risk block, check-mode only, no Excel/AI execution.

## Operator visibility

`GET /ansible/safety-status` and `GET /ansible/lab-config-preview` include:

- `execution_mode`
- `control_node_configured`
- `control_node_workdir`
- `delegate_available`
- blocking reasons when delegate is incomplete

Safety UI badge: **Local app / Remote Ansible Control Node**

## Secrets

Private key contents are never logged or returned in API responses.
`--private-key` path values are redacted in logs.

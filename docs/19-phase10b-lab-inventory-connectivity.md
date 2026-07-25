# Phase 10B — Lab Inventory + Controlled Connectivity Pilot

Builds on Phase 10A with stricter lab config validation and a sanitized
`lab-config-preview` for operators. Connectivity remains blocked by default.

See operator guide: [`docs/real-ansible-lab-pilot.md`](real-ansible-lab-pilot.md).

## Defaults (unchanged)

- `MOCK_MODE=true`
- `REAL_ANSIBLE_ENABLED=false`
- `REAL_ANSIBLE_CHECK_MODE_ONLY=true`
- Empty host/task-code allowlists
- No real apply endpoint

## What's new

- CSV allowlist parsing + format validation
- Timeout bounds 10–600 seconds
- When enabled: require inventory file, remote user, and private key file
- Unknown catalog task codes rejected
- `GET /ansible/lab-config-preview` (sanitized; no secrets)
- Safety UI: lab config preview, validation errors, gated connectivity button
- Example inventory: `ansible/inventory/lab.example.ini`

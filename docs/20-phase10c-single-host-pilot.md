# Phase 10C — Single Lab Host Connectivity + Real Dry Run Pilot

Builds on Phase 10B with an explicit single-host pilot gate
(`REAL_ANSIBLE_PILOT_MODE`) and `REAL_ANSIBLE_MAX_HOSTS_PER_RUN` (default 1).

See operator guide: [`docs/real-ansible-lab-pilot.md`](real-ansible-lab-pilot.md).

## Defaults (unchanged safety posture)

- `MOCK_MODE=true`
- `REAL_ANSIBLE_ENABLED=false`
- `REAL_ANSIBLE_CHECK_MODE_ONLY=true`
- `REAL_ANSIBLE_PILOT_MODE=false`
- `REAL_ANSIBLE_MAX_HOSTS_PER_RUN=1`
- Empty host/task-code allowlists
- No real apply endpoint

## What's new

- Pilot mode + max hosts per run settings
- `GET /ansible/pilot-readiness`
- safety-status / lab-config-preview pilot fields
- Connectivity + real dry-run enforce max hosts
- Safety UI Pilot Readiness panel
- Plan Detail single-host real dry-run label + host-count gate

## Explicitly out of scope

- Real apply / production run endpoint
- Multi-host production execution
- Executing Excel Remediation or AI suggestions

# Phase 8C — Lab-only Real Ansible Dry-run

## Scope

Implement **real dry-run only** via the ansible-runner Python API in check mode
(`--check`). Do **not** implement real apply/run.

## Defaults (unchanged / safe)

| Setting | Default |
|---------|---------|
| `MOCK_MODE` | `true` |
| `REAL_ANSIBLE_ENABLED` | `false` |

## Real dry-run allowed only when all are true

1. `MOCK_MODE=false`
2. `REAL_ANSIBLE_ENABLED=true`
3. `APP_ENV` is `lab` or `test`
4. All job targets have `environment` in `{lab, test}`
5. Preflight passes

Production / staging targets and `APP_ENV=production` remain blocked.

## Behaviour

- Uses `ansible_runner.run(..., cmdline="--check")` only
- No `ansible-playbook` shell fallback
- No `subprocess` / shell / paramiko
- Playbook path from enabled `remediation_catalog` only
- Never AI `generated_playbook`
- Never Excel Remediation text
- Persists `job_results` with `result_type=dry_run`
- Parses per-host events when present; if expected hosts exist but no usable
  host events are returned, **fails safely** (does not invent success)

## Audit events

| Event | When |
|-------|------|
| `real_dry_run_started` | After gates pass, before runner |
| `real_dry_run_completed` | After successful persistence |
| `real_dry_run_failed` | Runner/parse/unexpected errors |
| `real_dry_run_blocked` | Safety-gate refusals |

## Explicit non-goals

- Real apply / run
- Enabling real Ansible by default
- Production target execution

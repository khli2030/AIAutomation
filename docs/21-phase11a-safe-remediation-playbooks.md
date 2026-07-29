# Phase 11A — Real Safe Remediation Playbooks

Implements four reviewed SSH remediations with backup, `sshd -t` validation,
check-mode support, and **manual** rollback documentation.

## Implemented (only)

| Task code | Playbook | Expected value |
|-----------|----------|----------------|
| `SSH_MAX_AUTH_TRIES` | `ssh_max_auth_tries.yml` | `MaxAuthTries 4` |
| `SSH_LOG_LEVEL_INFO` | `ssh_log_level_info.yml` | `LogLevel INFO` |
| `SSH_CLIENT_ALIVE_INTERVAL` | `ssh_client_alive_interval.yml` | `ClientAliveInterval 300` |
| `SSH_IGNORE_RHOSTS_ENABLE` | `ssh_ignore_rhosts_enable.yml` | `IgnoreRhosts yes` |

Each playbook:

- Uses Ansible modules only (no shell for changes)
- Modifies only `/etc/ssh/sshd_config`
- Creates a timestamped backup before change
- Validates with `sshd -t -f %s` / `sshd -t`
- Reloads `sshd` only when the file changed and validation passes
- Supports check mode; idempotent; `serial: 1`
- Never uses Excel Remediation or AI suggestion text

## Explicitly not implemented

Package removal, mount/fstab, SELinux, `/tmp`, `/home`, rsync/x11 remove, and
root-login disable changes are **out of scope**. Remaining catalog stubs stay
blocked from real execution.

## Safety gates

- Stub markers (`Playbook stub`, `Placeholder — not implemented`) → real dry-run blocked
- High-risk deferred task codes → real execution blocked
- No real apply endpoint
- Defaults unchanged: `MOCK_MODE=true`, `REAL_ANSIBLE_ENABLED=false`,
  `REAL_ANSIBLE_CHECK_MODE_ONLY=true`, `REAL_ANSIBLE_PILOT_MODE=false`

## Catalog / readiness flags

For the four implemented remediations:

- `supports_backup = true`
- `supports_validation = true`
- `supports_rollback = manual` (no automated rollback)

Inspect via `GET /ansible/remediation-capabilities`.

## Rollback

See [`docs/remediation-rollback.md`](remediation-rollback.md).

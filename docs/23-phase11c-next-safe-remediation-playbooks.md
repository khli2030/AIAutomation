# Phase 11C — Next Safe Linux Remediation Playbooks

Implements four lower-risk Linux remediations with backup / permission capture,
validation where applicable, check-mode support, and **manual** rollback
documentation. Builds on Phase 11A SSH playbooks.

## Implemented (only these four in 11C)

| Task code | Playbook | Expected outcome |
|-----------|----------|------------------|
| `JOURNALD_COMPRESS_ENABLE` | `journald_compress_enable.yml` | `Compress=yes` (drop-in preferred) |
| `SHELL_TMOUT` | `shell_tmout.yml` | `TMOUT=600` via `/etc/profile.d/99-aiautomation-tmout.sh` |
| `CRONTAB_PERMISSIONS` | `crontab_permissions.yml` | `/etc/crontab` root:root `0600` |
| `CRON_DAILY_PERMISSIONS` | `cron_daily_permissions.yml` | `/etc/cron.daily` root:root `0700` |

Each playbook:

- Uses Ansible modules for changes (no shell for mutations)
- Backs up files or captures previous owner/group/mode before change
- Validates (grep / `bash -n` / assert) where applicable
- Restarts/reloads services only when changed and safe (`systemd-journald`)
- Supports check mode; idempotent; `serial: 1`
- Never uses Excel Remediation or AI suggestion text
- Does **not** create `/etc/crontab` or `/etc/cron.daily` when missing

## Explicitly not implemented

Package removal, mount/fstab, SELinux, `/tmp`, `/home`, rsync/x11 remove, and
root-login disable changes remain **out of scope**. Remaining catalog stubs
stay blocked from real execution.

## Safety gates

- Stub markers (`Playbook stub`, `Placeholder — not implemented`) → real dry-run blocked
- High-risk deferred task codes → real execution blocked
- No real apply endpoint
- Defaults unchanged: `MOCK_MODE=true`, `REAL_ANSIBLE_ENABLED=false`,
  `REAL_ANSIBLE_CHECK_MODE_ONLY=true`, `REAL_ANSIBLE_PILOT_MODE=false`

## Catalog / readiness flags

For the four Phase 11C remediations:

- `supports_backup = true`
- `supports_validation = true` (where applicable; all four include validation steps)
- `supports_rollback = manual` (no automated rollback)

Inspect via `GET /ansible/remediation-capabilities`.

## Rollback

See [`docs/remediation-rollback.md`](remediation-rollback.md).

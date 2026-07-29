# Remediation Rollback Guide (Phase 11A)

Phase 11A implements **manual** rollback only for the four safe SSH remediations.
There is **no automated rollback playbook** in this phase.

**Do not** use production or critical hosts for lab pilots.

## Shared SSH restore procedure

All four Phase 11A playbooks modify **only** `/etc/ssh/sshd_config` and create a
timestamped backup before changing it:

```text
/etc/ssh/sshd_config.bak-<ISO8601_BASIC_SHORT>
```

Example: `/etc/ssh/sshd_config.bak-20260729T183045`

### Find the backup

```bash
sudo ls -lt /etc/ssh/sshd_config.bak-*
```

Prefer the newest backup created immediately before the remediation run.

### Restore sshd_config

```bash
# Replace <backup> with the chosen backup path
sudo cp -a <backup> /etc/ssh/sshd_config
sudo chmod 600 /etc/ssh/sshd_config
```

### Validate

```bash
sudo sshd -t
# or explicitly:
sudo sshd -t -f /etc/ssh/sshd_config
```

Do **not** reload sshd until validation succeeds.

### Reload sshd

```bash
sudo systemctl reload sshd
# On some Debian/Ubuntu hosts the unit may be named ssh:
# sudo systemctl reload ssh
```

Confirm SSH access from a second session before closing the current one.

---

## SSH_MAX_AUTH_TRIES

| Item | Value |
|------|-------|
| Playbook | `ansible/playbooks/ssh_max_auth_tries.yml` |
| File changed | `/etc/ssh/sshd_config` |
| Setting | `MaxAuthTries 4` |
| Backup | `/etc/ssh/sshd_config.bak-*` |
| supports_backup | true |
| supports_validation | true |
| supports_rollback | **manual** |

Restore using the shared procedure above, then validate with `sshd -t` and reload.

## SSH_LOG_LEVEL_INFO

| Item | Value |
|------|-------|
| Playbook | `ansible/playbooks/ssh_log_level_info.yml` |
| File changed | `/etc/ssh/sshd_config` |
| Setting | `LogLevel INFO` |
| Backup | `/etc/ssh/sshd_config.bak-*` |
| supports_backup | true |
| supports_validation | true |
| supports_rollback | **manual** |

## SSH_CLIENT_ALIVE_INTERVAL

| Item | Value |
|------|-------|
| Playbook | `ansible/playbooks/ssh_client_alive_interval.yml` |
| File changed | `/etc/ssh/sshd_config` |
| Setting | `ClientAliveInterval 300` |
| Backup | `/etc/ssh/sshd_config.bak-*` |
| supports_backup | true |
| supports_validation | true |
| supports_rollback | **manual** |

## SSH_IGNORE_RHOSTS_ENABLE

| Item | Value |
|------|-------|
| Playbook | `ansible/playbooks/ssh_ignore_rhosts_enable.yml` |
| File changed | `/etc/ssh/sshd_config` |
| Setting | `IgnoreRhosts yes` |
| Backup | `/etc/ssh/sshd_config.bak-*` |
| supports_backup | true |
| supports_validation | true |
| supports_rollback | **manual** |

---

## What is not automated

- No automated rollback Ansible playbook
- No automatic restore on failed reload
- Stub playbooks (still containing `Playbook stub` / `Placeholder — not implemented`)
  are **blocked** from real dry-run / real execution
- High-risk remediations (package removal, mount/fstab, SELinux, `/tmp`, `/home`,
  etc.) remain unimplemented stubs and are blocked from real execution

## Related

- [`docs/21-phase11a-safe-remediation-playbooks.md`](21-phase11a-safe-remediation-playbooks.md)
- [`docs/real-ansible-lab-pilot.md`](real-ansible-lab-pilot.md)

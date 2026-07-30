# Remediation Rollback Guide (Phase 11A / 11C)

Phase 11A and 11C implement **manual** rollback only for the safe catalog
remediations listed below. There is **no automated rollback playbook**.

**Do not** use production or critical hosts for lab pilots.

---

## Phase 11A — SSH remediations

### Shared SSH restore procedure

All four Phase 11A playbooks modify **only** `/etc/ssh/sshd_config` and create a
timestamped backup before changing it:

```text
/etc/ssh/sshd_config.bak-<ISO8601_BASIC_SHORT>
```

Example: `/etc/ssh/sshd_config.bak-20260729T183045`

#### Find the backup

```bash
sudo ls -lt /etc/ssh/sshd_config.bak-*
```

Prefer the newest backup created immediately before the remediation run.

#### Restore sshd_config

```bash
# Replace <backup> with the chosen backup path
sudo cp -a <backup> /etc/ssh/sshd_config
sudo chmod 600 /etc/ssh/sshd_config
```

#### Validate

```bash
sudo sshd -t
# or explicitly:
sudo sshd -t -f /etc/ssh/sshd_config
```

Do **not** reload sshd until validation succeeds.

#### Reload sshd

```bash
sudo systemctl reload sshd
# On some Debian/Ubuntu hosts the unit may be named ssh:
# sudo systemctl reload ssh
```

Confirm SSH access from a second session before closing the current one.

### SSH_MAX_AUTH_TRIES

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

### SSH_LOG_LEVEL_INFO

| Item | Value |
|------|-------|
| Playbook | `ansible/playbooks/ssh_log_level_info.yml` |
| File changed | `/etc/ssh/sshd_config` |
| Setting | `LogLevel INFO` |
| Backup | `/etc/ssh/sshd_config.bak-*` |
| supports_backup | true |
| supports_validation | true |
| supports_rollback | **manual** |

### SSH_CLIENT_ALIVE_INTERVAL

| Item | Value |
|------|-------|
| Playbook | `ansible/playbooks/ssh_client_alive_interval.yml` |
| File changed | `/etc/ssh/sshd_config` |
| Setting | `ClientAliveInterval 300` |
| Backup | `/etc/ssh/sshd_config.bak-*` |
| supports_backup | true |
| supports_validation | true |
| supports_rollback | **manual** |

### SSH_IGNORE_RHOSTS_ENABLE

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

## Phase 11C — lower-risk Linux remediations

### JOURNALD_COMPRESS_ENABLE

| Item | Value |
|------|-------|
| Playbook | `ansible/playbooks/journald_compress_enable.yml` |
| Preferred change | `/etc/systemd/journald.conf.d/99-aiautomation.conf` |
| Fallback change | `/etc/systemd/journald.conf` (`Compress=yes`) |
| Backup | drop-in `.bak-*` and/or `journald.conf.bak-*` / lineinfile backup |
| supports_backup | true |
| supports_validation | true |
| supports_rollback | **manual** |

#### Revert drop-in (preferred path)

```bash
# If a drop-in backup exists, restore it:
sudo ls -lt /etc/systemd/journald.conf.d/99-aiautomation.conf.bak-*
sudo cp -a <backup> /etc/systemd/journald.conf.d/99-aiautomation.conf

# Or remove the managed drop-in entirely to fall back to defaults / main conf:
sudo rm -f /etc/systemd/journald.conf.d/99-aiautomation.conf
```

#### Revert main journald.conf (fallback path)

```bash
sudo ls -lt /etc/systemd/journald.conf.bak-*
sudo cp -a <backup> /etc/systemd/journald.conf
# Or manually set Compress back to the prior value (often commented #Compress=yes)
```

#### Apply journald config

```bash
sudo systemctl restart systemd-journald
```

Confirm journald is running: `systemctl is-active systemd-journald`.

### SHELL_TMOUT

| Item | Value |
|------|-------|
| Playbook | `ansible/playbooks/shell_tmout.yml` |
| File | `/etc/profile.d/99-aiautomation-tmout.sh` |
| Setting | `export TMOUT=600` |
| Backup | `/etc/profile.d/99-aiautomation-tmout.sh.bak-*` (if file existed) |
| supports_backup | true |
| supports_validation | true |
| supports_rollback | **manual** |

#### Remove or restore the TMOUT profile script

```bash
# Preferred: remove the managed script (new shells will not inherit TMOUT from it)
sudo rm -f /etc/profile.d/99-aiautomation-tmout.sh

# Or restore a prior backup if one was created:
sudo ls -lt /etc/profile.d/99-aiautomation-tmout.sh.bak-*
sudo cp -a <backup> /etc/profile.d/99-aiautomation-tmout.sh
sudo chown root:root /etc/profile.d/99-aiautomation-tmout.sh
sudo chmod 0644 /etc/profile.d/99-aiautomation-tmout.sh
sudo bash -n /etc/profile.d/99-aiautomation-tmout.sh
```

Already-open shells keep their current `TMOUT` until restarted.

### CRONTAB_PERMISSIONS

| Item | Value |
|------|-------|
| Playbook | `ansible/playbooks/crontab_permissions.yml` |
| Path | `/etc/crontab` (must already exist; playbook does not create it) |
| Desired | owner `root`, group `root`, mode `0600` |
| Previous values | printed in playbook output as `previous_owner` / `previous_group` / `previous_mode` |
| supports_backup | true (permission capture) |
| supports_validation | true |
| supports_rollback | **manual** |

#### Restore previous permissions

Use the `previous_*` values from the remediation job output (or an audit note):

```bash
# Example — replace OWNER/GROUP/MODE with captured values:
sudo chown OWNER:GROUP /etc/crontab
sudo chmod MODE /etc/crontab

# Verify:
stat -c '%a %U %G' /etc/crontab
```

If previous values were not captured, restore from your host baseline / CMDB
policy for `/etc/crontab` (commonly `root:root` `600` or site-specific).

### CRON_DAILY_PERMISSIONS

| Item | Value |
|------|-------|
| Playbook | `ansible/playbooks/cron_daily_permissions.yml` |
| Path | `/etc/cron.daily` (must already exist; playbook does not create it) |
| Desired | owner `root`, group `root`, mode `0700` |
| Previous values | printed as `previous_owner` / `previous_group` / `previous_mode` |
| supports_backup | true (permission capture) |
| supports_validation | true |
| supports_rollback | **manual** |

#### Restore previous permissions

```bash
# Example — replace OWNER/GROUP/MODE with captured values:
sudo chown OWNER:GROUP /etc/cron.daily
sudo chmod MODE /etc/cron.daily

# Verify:
stat -c '%a %U %G' /etc/cron.daily
```

---

## What is not automated

- No automated rollback Ansible playbook
- No automatic restore on failed service restart/reload
- Stub playbooks (still containing `Playbook stub` / `Placeholder — not implemented`)
  are **blocked** from real dry-run / real execution
- High-risk remediations (package removal, mount/fstab, SELinux, `/tmp`, `/home`,
  root-login disable, etc.) remain unimplemented stubs and are blocked from
  real execution

## Related

- [`docs/21-phase11a-safe-remediation-playbooks.md`](21-phase11a-safe-remediation-playbooks.md)
- [`docs/23-phase11c-next-safe-remediation-playbooks.md`](23-phase11c-next-safe-remediation-playbooks.md)
- [`docs/real-ansible-lab-pilot.md`](real-ansible-lab-pilot.md)

# Phase 9A — Top Qualys Rule Coverage Expansion

## Goal

Reduce `NEEDS_REVIEW` volume by adding **deterministic** classifier mappings and
`remediation_catalog` entries for the most common Qualys controls.

Mappings go through **classifier `task_code` + `remediation_catalog` only**.
Excel Remediation text is never executed. AI-generated playbooks are never used
for execution.

## Safety (unchanged)

| Rule | Status |
|------|--------|
| Never execute raw Excel Remediation text | Required |
| Never use AI `generated_playbook` for execution | Required |
| `MOCK_MODE=true` default | Unchanged |
| `REAL_ANSIBLE_ENABLED=false` default | Unchanged |
| No subprocess / shell / SSH / Paramiko / ansible-runner in mock mode | Unchanged |
| Production / staging real-Ansible gates | Unchanged |

Phase 9A catalog entries may be **`is_enabled=true`** so mock `generate-plan`
can include them. Real Ansible still requires existing Phase 8B/8C gates.

## Classification order

1. **Exact `qualys_control_id`** lookup (`QUALYS_CONTROL_ID_MAP`)
2. **Conservative text fallback** on the six classifier fields
3. Else → `NEEDS_REVIEW` (`is_recognized=false`)

## Exact Qualys ID mappings

| Qualys ID | task_code |
|-----------|-----------|
| 1072 | `PASSWORD_MIN_AGE` |
| 5957 | `SYSCTL_IPV4_SECURE_REDIRECTS_DISABLE` |
| 7500 | `SYSCTL_IPV6_ACCEPT_RA_DISABLE` |
| 17132 | `JOURNALD_COMPRESS_ENABLE` |
| 2236 | `SSH_IGNORE_RHOSTS_ENABLE` |
| 3598 | `SSH_LOG_LEVEL_INFO` |
| 2234 | `SSH_MAX_AUTH_TRIES` |
| 5222 | `SSH_CLIENT_ALIVE_INTERVAL` |
| 2678 | `SHELL_TMOUT` |
| 5154 | `CRONTAB_PERMISSIONS` |
| 7341 | `CRON_DAILY_PERMISSIONS` |
| 7343 | `CRON_HOURLY_PERMISSIONS` |
| 7345 | `CRON_WEEKLY_PERMISSIONS` |
| 7347 | `CRON_MONTHLY_PERMISSIONS` |
| 22693 | `RSYNC_REMOVE` |
| 21959 | `X11_SERVER_REMOVE` |
| 7411 | `AIDE_INSTALL` |
| 7403 | `HOME_PARTITION_NODEV` |

## Intentionally not auto-classified

| Qualys ID | Intended name | Why |
|-----------|---------------|-----|
| 6896 | HOME_DIR_PERMISSIONS | Per-user home directory review — not a safe generic remediation |
| 7394 | TMP_PARTITION_REQUIRED | Creating/migrating a `/tmp` partition is not a simple safe remediation |

These remain **`NEEDS_REVIEW`** (manual operator review). They are listed in
`MANUAL_REVIEW_QUALYS_CONTROL_IDS` and must stay out of `QUALYS_CONTROL_ID_MAP`.

## Expected configurations (catalog intent)

| task_code | Expected configuration |
|-----------|------------------------|
| `PASSWORD_MIN_AGE` | `PASS_MIN_DAYS 1` |
| `SYSCTL_IPV4_SECURE_REDIRECTS_DISABLE` | `net.ipv4.conf.all.secure_redirects = 0` |
| `SYSCTL_IPV6_ACCEPT_RA_DISABLE` | `net.ipv6.conf.default.accept_ra = 0` |
| `JOURNALD_COMPRESS_ENABLE` | `Compress=yes` |
| `SSH_IGNORE_RHOSTS_ENABLE` | `IgnoreRhosts yes` |
| `SSH_LOG_LEVEL_INFO` | `LogLevel INFO` |
| `SSH_MAX_AUTH_TRIES` | `MaxAuthTries 4` or stricter |
| `SSH_CLIENT_ALIVE_INTERVAL` | `ClientAliveInterval 300` |
| `SHELL_TMOUT` | `TMOUT=600` |
| `CRONTAB_PERMISSIONS` | `chmod 600 /etc/crontab` |
| `CRON_DAILY_PERMISSIONS` | `chmod 700 /etc/cron.daily` |
| `CRON_HOURLY_PERMISSIONS` | `chmod 700 /etc/cron.hourly` |
| `CRON_WEEKLY_PERMISSIONS` | `chmod 700 /etc/cron.weekly` |
| `CRON_MONTHLY_PERMISSIONS` | `chmod 700 /etc/cron.monthly` |
| `RSYNC_REMOVE` | remove rsync package |
| `X11_SERVER_REMOVE` | remove `xorg-x11-server*` packages |
| `AIDE_INSTALL` | install aide package |
| `HOME_PARTITION_NODEV` | ensure `/home` fstab entry has `nodev` |

## Catalog + playbooks

Seed: `backend/app/db/seed_remediation_catalog.py`  
Playbooks (stubs under `ansible/playbooks/`):

- `password_min_age.yml`
- `sysctl_ipv4_secure_redirects_disable.yml`
- `sysctl_ipv6_accept_ra_disable.yml`
- `journald_compress_enable.yml`
- `ssh_ignore_rhosts_enable.yml`
- `ssh_log_level_info.yml`
- `ssh_max_auth_tries.yml`
- `ssh_client_alive_interval.yml`
- `shell_tmout.yml`
- `crontab_permissions.yml`
- `cron_daily_permissions.yml`
- `cron_hourly_permissions.yml`
- `cron_weekly_permissions.yml`
- `cron_monthly_permissions.yml`
- `rsync_remove.yml`
- `x11_server_remove.yml`
- `aide_install.yml`
- `home_partition_nodev.yml`

Stubs use `ansible.builtin.debug` placeholders. Mock execution does not run them
via ansible-runner. Replace stubs with reviewed playbooks before relying on real
lab dry-run for these controls.

## Operator steps (see READY_FOR_PLAN increase)

```bash
docker compose up -d --build backend celery-worker
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.db.seed_cli
# Re-upload / re-validate the Qualys batch
# READY_FOR_PLAN should rise; NEEDS_REVIEW should fall for mapped IDs
# 6896 and 7394 should still be NEEDS_REVIEW
```

## Tests

- `backend/tests/unit/test_phase9a_qualys_coverage.py`
- Existing mock dry-run/run safety tests are intentionally unchanged

## Explicit non-goals

- Real apply/run for new playbooks
- Changing `MOCK_MODE` / `REAL_ANSIBLE_ENABLED` defaults
- Auto-classifying 6896 / 7394
- Executing Excel remediation text

# Phase 1 security hardening

Applied on top of Phase 1 before merge. No Phase 2 features.

## Changes

| Item | Change |
|------|--------|
| Port binds | Backend `8000`, Postgres `5432`, Redis `6379` → `127.0.0.1` only |
| LAN exposure | Postgres/Redis not published on non-loopback interfaces |
| API auth | `ADMIN_TOKEN` required for all routes except `/health` |
| Ansible host keys | `host_key_checking = True`; override via `ANSIBLE_HOST_KEY_CHECKING` |
| Image | Removed `sshpass` (SSH keys only) |
| Catalog | Only `SSH_DISABLE_ROOT_LOGIN` `is_enabled=True`; stubs disabled |
| Mounts | `./ansible` read-only; uploads/runtime under `./data` only |

## Auth usage

```bash
# Public
curl http://127.0.0.1:8000/health

# Protected
curl http://127.0.0.1:8000/docs -H "X-Admin-Token: $ADMIN_TOKEN"
# or
curl http://127.0.0.1:8000/ -H "Authorization: Bearer $ADMIN_TOKEN"
```

If `ADMIN_TOKEN` is empty, protected routes return `503`.

## Still not production-ready

Token auth is a shared secret, not RBAC. Add TLS, stronger identity, and reviewed playbooks before any broader internal rollout.

# Phase 8B — Real Ansible Readiness (lab/test only)

## Scope

Add a guarded real Ansible adapter and `GET /ansible/preflight` **without** enabling
real execution by default. Keep `MOCK_MODE=true` and `REAL_ANSIBLE_ENABLED=false`.

## Defaults (safe)

| Setting | Default | Meaning |
|---------|---------|---------|
| `MOCK_MODE` | `true` | Mock adapter only; never imports ansible-runner |
| `REAL_ANSIBLE_ENABLED` | `false` | Second gate; real path stays blocked |
| `APP_ENV` | `development` | Not in `{lab, test}` → real blocked |

## Real Ansible allowed only when all are true

1. `MOCK_MODE=false`
2. `REAL_ANSIBLE_ENABLED=true`
3. `APP_ENV` is `lab` or `test`
4. All job targets have `environment` in `{lab, test}`

**Production real execution remains blocked** (`APP_ENV=production` or target
`environment=production` / `staging`).

## Safety rules

- Never execute AI `generated_playbook`
- Only enabled `remediation_catalog` playbook paths
- Playbook paths must resolve under `ansible/playbooks` (traversal blocked)
- Inventory paths must resolve under `ansible/inventories`
- No arbitrary shell / `ansible-playbook` CLI fallback
- No Excel Remediation text execution
- If `ansible-runner` is missing → clear error (no silent fallback)
- Blocked attempts write audit logs (`event=blocked`, actor/role when available)

## Adapter

- Mock path: unchanged (`AnsibleExecutionService._execute_mock`)
- Real path: lazy `app.services.real_ansible_runner.run_with_ansible_runner`
  after safety gates in `app.services.ansible_safety`

## Preflight

`GET /ansible/preflight` (authenticated, read roles) reports:

- MOCK_MODE / REAL_ANSIBLE_ENABLED / APP_ENV
- ansible-runner availability
- ansible project / playbooks / inventories dirs
- enabled catalog playbook files exist
- AI drafts are not executable
- playbooks readable; runtime artifact dirs writable

Does **not** execute Ansible.

## Explicit non-goals

- Enabling real Ansible by default
- Production target execution
- Full per-host result persistence for real runs (readiness first)
- Using AI drafts or remediation text as commands

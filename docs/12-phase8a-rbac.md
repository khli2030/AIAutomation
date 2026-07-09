# Phase 8A — Minimal RBAC (before real Ansible)

## Scope

Replace the single `ADMIN_TOKEN`-only gate with MVP shared role tokens from the environment. Keep `MOCK_MODE=true`. **Do not** call `ansible-runner`, `ansible-playbook`, subprocess, shell, or SSH.

## Roles

| Role | Capabilities |
|------|----------------|
| **viewer** | Read dashboard, imports, records, plans, jobs, results |
| **operator** | Upload Excel, validate batch, generate plan, dry-run, run approved jobs, AI analyze |
| **approver** | Approve/reject jobs; approve/reject AI suggestions |
| **admin** | Everything, including convert AI suggestion → disabled catalog |

## Environment variables

```bash
VIEWER_TOKEN=...
OPERATOR_TOKEN=...
APPROVER_TOKEN=...
ADMIN_TOKEN=...
```

Empty values disable that role. At least one token (typically `ADMIN_TOKEN`) must be set or the API returns 503.

Send any role token via legacy header `X-Admin-Token` or `Authorization: Bearer`.

## Authorization rules

1. `/health` — public
2. Read-only endpoints — viewer / operator / approver / admin
3. Upload — operator / admin
4. Validate batch — operator / admin
5. Generate plan — operator / admin
6. Dry-run — operator / admin
7. Job approve — approver / admin
8. Job reject — approver / admin
9. Run approved job — operator / admin
10. AI suggestion approve/reject — approver / admin
11. Convert AI suggestion to catalog — **admin only**

`GET /auth/me` returns the resolved role plus capability flags for the UI.

## Audit

Sensitive actions write `audit_logs` with:

- `actor` — e.g. `role:operator`
- `details.auth_role` — e.g. `operator`

Covered actions: upload, validate, generate_plan, dry_run, approve, reject, run,
AI analyze (`ai-analyze-needs-review`), AI approve/reject, convert-to-catalog.

## Separation of duties (production requirement)

**Not enforced in Phase 8A.** Shared role tokens do not uniquely identify a human, so blocking “the same actor who generated a plan from approving its jobs” is not practical with MVP tokens.

**Production requirement:** when real identity (SSO/OIDC) lands, prevent the plan creator from approving jobs from that plan (and prefer distinct humans for operate vs approve). Documented here so it is not forgotten before real Ansible.

## Frontend

- Settings / Login stores a role token in `sessionStorage` (MVP-only).
- Sidebar shows current role via `/auth/me`.
- Mutating buttons are disabled when the role lacks capability.
- Tokens are never hardcoded.
- Warning: sessionStorage / shared env tokens are **not** production authentication.

## Explicit non-goals

- Real Ansible / Runner / SSH
- SSO / OIDC / per-user sessions
- Enforcing separation of duties on shared tokens
- Enabling AI-generated playbooks for execution

# Compliance Remediation — Frontend (Phase 7 + 8A)

Internal Next.js operator console for the Linux Compliance Remediation Platform.

## Safety

- Backend must keep **`MOCK_MODE=true`**.
- UI never calls ansible-runner, ansible-playbook, subprocess, shell, or SSH.
- Excel Remediation text is display-only.
- AI `generated_playbook` is read-only; convert-to-catalog always sends `enable: false`.
- No playbook editor.
- **Role tokens are never hardcoded** — paste into Settings / Login (sessionStorage) or set `NEXT_PUBLIC_ADMIN_TOKEN` only in gitignored `.env.local`.
- **sessionStorage token is MVP / lab-only** — not production authentication. Production needs real auth (SSO/OIDC/RBAC) behind TLS.

## Auth (Phase 8A)

Paste any of `VIEWER_TOKEN` / `OPERATOR_TOKEN` / `APPROVER_TOKEN` / `ADMIN_TOKEN`. The UI calls `/auth/me` to show the current role and disable buttons the role cannot use. See [`docs/12-phase8a-rbac.md`](../docs/12-phase8a-rbac.md).

## Local run

Prerequisites: backend API on `http://127.0.0.1:8000` with role tokens set.

```bash
cd frontend
cp .env.example .env.local
# edit NEXT_PUBLIC_API_URL if needed; do not commit .env.local

npm install
npm run dev
```

Open `http://127.0.0.1:3000`, go to **Settings / Login**, paste a role token from the backend `.env`.

### Compose (optional profile)

```bash
docker compose --profile frontend up -d --build frontend
```

Compose sets `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000` (browser → host loopback API).

## Pages

| Route | Purpose |
|-------|---------|
| `/` | Dashboard counters + latest imports/jobs |
| `/upload` | Upload `.xlsx` (operator/admin) |
| `/imports` | Batch summary, validate, generate plan (operator/admin) |
| `/records` | Filter records; show remediation / expected config |
| `/needs-review` | NEEDS_REVIEW list + AI analyze (operator/admin) |
| `/ai-suggestions` | Approve / reject (approver/admin); convert admin-only |
| `/plans` | List plans + jobs |
| `/approvals` | Mock dry-run/run (operator/admin); approve/reject (approver/admin) |
| `/jobs/[id]` | Dry-run vs run results via `result_type` |
| `/settings` | Role token login + `/auth/me` role display |

## Tests

```bash
npm test
npm run build

# Phase 7.5 UI E2E (Playwright + mocked MOCK_MODE API — no real Ansible)
npx playwright install chromium   # once
npm run test:e2e
```

Full manual UI workflow (real backend + frontend): see
[`docs/11-phase75-ui-e2e-mock-test.md`](../docs/11-phase75-ui-e2e-mock-test.md).

## Manual test checklist

1. Set a role token in Settings; confirm role badge + MOCK_MODE banner.
2. As viewer: confirm mutate buttons disabled; reads work.
3. As operator: upload → validate → plan → dry-run → run; approve disabled.
4. As approver: approve/reject jobs and suggestions; upload/convert disabled.
5. As admin: convert-to-catalog (`is_enabled=false`) works.
6. Confirm no playbook edit controls exist anywhere.

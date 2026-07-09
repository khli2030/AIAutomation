# Compliance Remediation — Frontend (Phase 7)

Internal Next.js operator console for the Linux Compliance Remediation Platform.

## Safety

- Backend must keep **`MOCK_MODE=true`**.
- UI never calls ansible-runner, ansible-playbook, subprocess, shell, or SSH.
- Excel Remediation text is display-only.
- AI `generated_playbook` is read-only; convert-to-catalog always sends `enable: false`.
- No playbook editor.
- **`ADMIN_TOKEN` is never hardcoded** — paste into Settings (sessionStorage) or set `NEXT_PUBLIC_ADMIN_TOKEN` only in gitignored `.env.local`.
- **sessionStorage token is MVP / lab-only** — not production authentication. Production needs real auth (SSO/OIDC/RBAC) behind TLS; do not treat the shared admin token as a security boundary.

## Local run

Prerequisites: backend API on `http://127.0.0.1:8000` with `ADMIN_TOKEN` set.

```bash
cd frontend
cp .env.example .env.local
# edit NEXT_PUBLIC_API_URL if needed; do not commit .env.local

npm install
npm run dev
```

Open `http://127.0.0.1:3000`, go to **Settings**, paste `ADMIN_TOKEN` from the backend `.env`.

### Compose (optional profile)

```bash
docker compose --profile frontend up -d --build frontend
```

Compose sets `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000` (browser → host loopback API).

## Pages

| Route | Purpose |
|-------|---------|
| `/` | Dashboard counters + latest imports/jobs |
| `/upload` | Upload `.xlsx`, show `batch_id` + status |
| `/imports` | Batch summary, validate, generate plan |
| `/records` | Filter records; show remediation / expected config |
| `/needs-review` | NEEDS_REVIEW list + AI analyze |
| `/ai-suggestions` | Approve / reject / convert (disabled catalog) |
| `/plans` | List plans + jobs |
| `/approvals` | Mock dry-run, approve after success, reject, mock run |
| `/jobs/[id]` | Dry-run vs run results via `result_type` |
| `/settings` | API URL (read-only) + token sessionStorage |

## Tests

```bash
npm test
npm run build
```

## Manual test checklist

1. Set token in Settings; confirm MOCK_MODE banner.
2. Upload sample Excel → note `batch_id`.
3. Import Summary → wait for `parsed` → Validate → Generate plan.
4. Records Review → filter by `READY_FOR_PLAN` / device.
5. Needs Review → AI analyze (mock) → AI Suggestions approve/reject/convert (`is_enabled=false`).
6. Plans → open jobs → Job Approval → mock dry-run → confirm `result_type=dry_run` → Approve → mock run.
7. Job Results → dry_run and run sections separate; expand stdout/stderr.
8. Confirm no playbook edit controls exist anywhere.

#!/usr/bin/env bash
# Phase 8C.5 — Lab real dry-run smoke checklist helper.
#
# Default behaviour: print the manual checklist and optionally call
# GET /ansible/preflight (read-only; does not execute Ansible).
#
# This script does NOT invoke ansible-runner, ansible-playbook, subprocess,
# shell Ansible, or SSH. It will not POST dry-run unless you explicitly confirm.
#
# Usage:
#   export ADMIN_TOKEN=...          # or VIEWER_TOKEN / OPERATOR_TOKEN
#   ./scripts/lab_real_dry_run_checklist.sh
#
# Optional env:
#   API_BASE                 default http://127.0.0.1:8000
#   RUN_PREFLIGHT=1          call GET /ansible/preflight (default: 1)
#   JOB_ID                   job id for printed dry-run curl example
#   CONFIRM_LAB_DRY_RUN=yes  REQUIRED to actually POST /execution-jobs/{id}/dry-run
#                            Also requires JOB_ID and an interactive "yes" prompt
#                            (or CONFIRM_LAB_DRY_RUN_I_UNDERSTAND=yes to skip prompt
#                            in non-interactive lab automation — still needs
#                            CONFIRM_LAB_DRY_RUN=yes).
#
# Safety: production/staging must stay blocked by the API. Do not set
# APP_ENV=production. Prefer APP_ENV=lab with MOCK_MODE=false and
# REAL_ANSIBLE_ENABLED=true only for the smoke window, then restore defaults.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_BASE="${API_BASE:-http://127.0.0.1:8000}"
ADMIN_TOKEN="${ADMIN_TOKEN:-}"
OPERATOR_TOKEN="${OPERATOR_TOKEN:-}"
VIEWER_TOKEN="${VIEWER_TOKEN:-}"
RUN_PREFLIGHT="${RUN_PREFLIGHT:-1}"
JOB_ID="${JOB_ID:-}"
CONFIRM_LAB_DRY_RUN="${CONFIRM_LAB_DRY_RUN:-}"
CONFIRM_LAB_DRY_RUN_I_UNDERSTAND="${CONFIRM_LAB_DRY_RUN_I_UNDERSTAND:-}"

step() {
  echo
  echo "============================================================"
  echo " $1"
  echo "============================================================"
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

load_token_from_env_file() {
  local key="$1"
  local val=""
  if [[ -f "${ROOT}/.env" ]]; then
    val="$(grep -E "^${key}=" "${ROOT}/.env" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" || true)"
  fi
  printf '%s' "${val}"
}

if [[ -z "${ADMIN_TOKEN}" ]]; then
  ADMIN_TOKEN="$(load_token_from_env_file ADMIN_TOKEN)"
fi
if [[ -z "${OPERATOR_TOKEN}" ]]; then
  OPERATOR_TOKEN="$(load_token_from_env_file OPERATOR_TOKEN)"
fi
if [[ -z "${VIEWER_TOKEN}" ]]; then
  VIEWER_TOKEN="$(load_token_from_env_file VIEWER_TOKEN)"
fi

# Prefer viewer for read-only preflight; fall back to admin/operator.
READ_TOKEN="${VIEWER_TOKEN:-${ADMIN_TOKEN:-${OPERATOR_TOKEN:-}}}"
OP_TOKEN="${OPERATOR_TOKEN:-${ADMIN_TOKEN:-}}"

need_cmd curl
need_cmd jq

step "Phase 8C.5 — Lab real dry-run smoke checklist (manual)"
cat <<'EOF'
This helper prints the smoke checklist. It does NOT run Ansible automatically.

Required lab smoke env (set on control server .env, then restart backend/celery):
  MOCK_MODE=false
  REAL_ANSIBLE_ENABLED=true
  APP_ENV=lab

All job targets must have environment=lab or environment=test.
Production and staging targets remain blocked. Do not enable production/staging.

After smoke test, restore:
  MOCK_MODE=true
  REAL_ANSIBLE_ENABLED=false

Full documentation:
  docs/14-phase8c5-lab-real-dry-run-smoke-test.md
EOF

step "Checklist (operator steps)"
cat <<'EOF'
[ ] 1. On Ansible control server only: set MOCK_MODE=false, REAL_ANSIBLE_ENABLED=true, APP_ENV=lab
[ ] 2. Restart backend + celery-worker; confirm printenv shows those three values
[ ] 3. GET /ansible/preflight → real_ansible_allowed=true, blockers=[]
[ ] 4. Create/select a waiting_dry_run job with 1–3 targets (lab|test only)
[ ] 5. Exclude staging/production assets (e.g. do not use e2e-linux-03)
[ ] 6. POST /execution-jobs/{id}/dry-run (operator/admin) — check mode only
[ ] 7. Inspect GET .../results?result_type=dry_run
[ ] 8. Inspect audit_logs for real_dry_run_started / completed (or blocked/failed)
[ ] 9. Inspect ansible-runner artifacts under RUNNER_PRIVATE_DATA_DIR/job-{id}-dry-run/
[ ] 10. Confirm: no apply/run, check mode only, prod/staging still blocked
[ ] 11. Restore MOCK_MODE=true and REAL_ANSIBLE_ENABLED=false; restart services
[ ] 12. Do NOT implement or call real apply for this phase
EOF

step "Expected safe behaviour"
cat <<'EOF'
- ansible-runner cmdline is --check only (no system changes expected)
- production/staging targets blocked by API gates
- empty targets blocked (missing_targets)
- incomplete host events fail safely (host_parse_incomplete)
- real apply/run remains blocked (apply_blocked_phase8c)
EOF

step "Health check (public)"
health="$(curl -sS "${API_BASE}/health" || true)"
echo "${health}" | jq . >/dev/null 2>&1 || fail "Health endpoint not reachable at ${API_BASE}/health"
echo "${health}" | jq .

if [[ "${RUN_PREFLIGHT}" == "1" ]]; then
  [[ -n "${READ_TOKEN}" ]] || fail "A read token is required for preflight (VIEWER_TOKEN, ADMIN_TOKEN, or OPERATOR_TOKEN)"
  step "GET /ansible/preflight (read-only — does not execute Ansible)"
  preflight="$(curl -sS "${API_BASE}/ansible/preflight" -H "X-Admin-Token: ${READ_TOKEN}")"
  echo "${preflight}" | jq .
  allowed="$(echo "${preflight}" | jq -r '.real_ansible_allowed // false')"
  if [[ "${allowed}" != "true" ]]; then
    echo
    echo "NOTE: real_ansible_allowed is not true. Fix blockers before any dry-run."
    echo "Common blockers: MOCK_MODE still true, REAL_ANSIBLE_ENABLED false, APP_ENV not lab|test,"
    echo "missing ansible-runner, missing playbook/inventory paths, unwritable artifact dirs."
  fi
else
  step "Skipping preflight (RUN_PREFLIGHT=${RUN_PREFLIGHT})"
fi

step "Printed dry-run command (NOT executed unless explicitly confirmed)"
if [[ -z "${JOB_ID}" ]]; then
  JOB_ID_PLACEHOLDER="<JOB_ID>"
else
  JOB_ID_PLACEHOLDER="${JOB_ID}"
fi

cat <<EOF
# Manual real dry-run (operator/admin). Review docs first.
# Requires lab gates: MOCK_MODE=false REAL_ANSIBLE_ENABLED=true APP_ENV=lab
# Job must have 1–3 targets with environment=lab|test only.

curl -sS -X POST "${API_BASE}/execution-jobs/${JOB_ID_PLACEHOLDER}/dry-run" \\
  -H "X-Admin-Token: \$OPERATOR_TOKEN" | jq .

# Inspect dry-run results:
curl -sS "${API_BASE}/execution-jobs/${JOB_ID_PLACEHOLDER}/results?result_type=dry_run" \\
  -H "X-Admin-Token: \$VIEWER_TOKEN" | jq .

# Artifacts (compose default on host):
#   ./data/ansible_private_data/job-${JOB_ID_PLACEHOLDER}-dry-run/
EOF

if [[ "${CONFIRM_LAB_DRY_RUN}" == "yes" ]]; then
  step "Explicit confirmation path — POST dry-run via HTTP API only"
  [[ -n "${JOB_ID}" ]] || fail "JOB_ID is required when CONFIRM_LAB_DRY_RUN=yes"
  [[ -n "${OP_TOKEN}" ]] || fail "OPERATOR_TOKEN or ADMIN_TOKEN required to POST dry-run"

  echo "You set CONFIRM_LAB_DRY_RUN=yes."
  echo "This will call POST ${API_BASE}/execution-jobs/${JOB_ID}/dry-run"
  echo "(platform may invoke ansible-runner --check on the server)."
  echo "This script still will not call ansible-playbook or ansible-runner CLI."

  if [[ "${CONFIRM_LAB_DRY_RUN_I_UNDERSTAND}" != "yes" ]]; then
    if [[ ! -t 0 ]]; then
      fail "Non-interactive shell: set CONFIRM_LAB_DRY_RUN_I_UNDERSTAND=yes in addition to CONFIRM_LAB_DRY_RUN=yes, or run interactively"
    fi
    read -r -p "Type yes to proceed with HTTP dry-run only: " answer
    [[ "${answer}" == "yes" ]] || fail "Aborted — dry-run not executed"
  fi

  echo "Posting dry-run for job ${JOB_ID}..."
  result="$(curl -sS -X POST "${API_BASE}/execution-jobs/${JOB_ID}/dry-run" \
    -H "X-Admin-Token: ${OP_TOKEN}")"
  echo "${result}" | jq . 2>/dev/null || echo "${result}"
else
  step "Dry-run NOT executed (safe default)"
  cat <<'EOF'
To execute the HTTP dry-run from this script you must set:
  CONFIRM_LAB_DRY_RUN=yes
  JOB_ID=<id>
and confirm interactively (or CONFIRM_LAB_DRY_RUN_I_UNDERSTAND=yes).

Example:
  CONFIRM_LAB_DRY_RUN=yes JOB_ID=123 ./scripts/lab_real_dry_run_checklist.sh
EOF
fi

step "Done"
echo "See docs/14-phase8c5-lab-real-dry-run-smoke-test.md for troubleshooting and rollback."

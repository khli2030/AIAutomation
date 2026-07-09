#!/usr/bin/env bash
# Phase 6.5 — End-to-end mock workflow via HTTP API (MOCK_MODE=true).
#
# Prerequisites:
#   docker compose up -d --build db redis backend celery-worker
#   docker compose exec backend alembic upgrade head
#   docker compose exec backend python -m app.db.seed_cli
#
# Usage:
#   export ADMIN_TOKEN=...   # same as .env
#   ./scripts/e2e_mock_workflow.sh
#
# Optional env:
#   API_BASE     default http://127.0.0.1:8000
#   SAMPLE_XLSX  path to an existing .xlsx (otherwise a temp sample is generated)
#
# Safety: does not invoke ansible-runner, ansible-playbook, subprocess Ansible, or SSH.
# Relies on the API MOCK_MODE=true path only.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_BASE="${API_BASE:-http://127.0.0.1:8000}"
ADMIN_TOKEN="${ADMIN_TOKEN:-}"
TMP_DIR="$(mktemp -d)"
SAMPLE_XLSX="${SAMPLE_XLSX:-}"
CLEANUP_SAMPLE=0

cleanup() {
  if [[ "${CLEANUP_SAMPLE}" -eq 1 && -n "${SAMPLE_XLSX}" && -f "${SAMPLE_XLSX}" ]]; then
    rm -f "${SAMPLE_XLSX}"
  fi
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

step() {
  echo
  echo "============================================================"
  echo " STEP $1: $2"
  echo "============================================================"
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

need_cmd curl
need_cmd python3
need_cmd jq

if [[ -z "${ADMIN_TOKEN}" && -f "${ROOT}/.env" ]]; then
  ADMIN_TOKEN="$(grep -E '^ADMIN_TOKEN=' "${ROOT}/.env" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"
fi
[[ -n "${ADMIN_TOKEN}" ]] || fail "ADMIN_TOKEN is required (export it or set in .env)"

auth_hdr=(-H "X-Admin-Token: ${ADMIN_TOKEN}")

api() {
  local method="$1"
  local path="$2"
  shift 2
  curl -sS -X "${method}" "${API_BASE}${path}" "${auth_hdr[@]}" "$@"
}

json_field() {
  jq -er "$1"
}

echo "E2E mock workflow against ${API_BASE} (MOCK_MODE expected true)"

# ---------------------------------------------------------------------------
step 0 "Health check (public)"
# ---------------------------------------------------------------------------
health="$(curl -sS "${API_BASE}/health" || true)"
echo "${health}" | jq . >/dev/null 2>&1 || fail "Health endpoint not reachable at ${API_BASE}/health"
echo "${health}" | jq .

# ---------------------------------------------------------------------------
step 1 "Seed remediation_catalog + test assets"
# ---------------------------------------------------------------------------
if command -v docker >/dev/null 2>&1 && docker compose -f "${ROOT}/docker-compose.yml" ps --status running 2>/dev/null | grep -q backend; then
  docker compose -f "${ROOT}/docker-compose.yml" exec -T backend python -m app.db.seed_cli
else
  echo "Docker backend not detected — assuming catalog/assets already seeded."
  echo "If validation fails with ASSET_NOT_FOUND, run:"
  echo "  docker compose exec backend python -m app.db.seed_cli"
fi

# ---------------------------------------------------------------------------
step 2 "Create sample Excel with valid compliance records"
# ---------------------------------------------------------------------------
if [[ -z "${SAMPLE_XLSX}" || ! -f "${SAMPLE_XLSX}" ]]; then
  SAMPLE_XLSX="${TMP_DIR}/e2e_compliance.xlsx"
  CLEANUP_SAMPLE=1
  PYTHONPATH="${ROOT}/backend" python3 - "${SAMPLE_XLSX}" <<'PY'
from io import BytesIO
from pathlib import Path
import sys
from openpyxl import Workbook
from app.constants.excel_columns import EXCEL_REQUIRED_COLUMNS

out = Path(sys.argv[1])
wb = Workbook()
ws = wb.active
ws.append(list(EXCEL_REQUIRED_COLUMNS))
cols = list(EXCEL_REQUIRED_COLUMNS)
for device, cid in (("e2e-linux-01", "CTRL-ROOT-01"), ("e2e-linux-02", "CTRL-ROOT-02")):
    row = [""] * len(cols)
    row[cols.index("Device Name")] = device
    row[cols.index("Overall Status")] = "Failed"
    row[cols.index("Criticality")] = "High"
    row[cols.index("Qualys Control ID")] = cid
    row[cols.index("Source Check ID")] = f"SRC-{cid}"
    row[cols.index("Control Description")] = "SSH PermitRootLogin must be no"
    row[cols.index("RATIONALE")] = "Prevent direct root SSH access"
    row[cols.index("Remediation")] = "Set PermitRootLogin no in sshd_config"
    row[cols.index("Expected Configuration")] = "PermitRootLogin no"
    row[cols.index("Config Scan ID")] = f"SCAN-{cid}"
    ws.append(row)
buf = BytesIO()
wb.save(buf)
out.write_bytes(buf.getvalue())
print(f"Wrote {out} ({out.stat().st_size} bytes)")
PY
fi
echo "Sample Excel: ${SAMPLE_XLSX}"

# ---------------------------------------------------------------------------
step 3 "Upload Excel"
# ---------------------------------------------------------------------------
upload_json="$(api POST /imports/upload \
  -F "file=@${SAMPLE_XLSX};type=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" \
  -F "uploaded_by=e2e-script")"
echo "${upload_json}" | jq .
BATCH_ID="$(echo "${upload_json}" | json_field '.batch.id')"
echo "batch_id=${BATCH_ID}"

# ---------------------------------------------------------------------------
step 4 "Wait for parse (Celery)"
# ---------------------------------------------------------------------------
PARSED=0
for _ in $(seq 1 60); do
  batch_json="$(api GET "/imports/${BATCH_ID}")"
  status="$(echo "${batch_json}" | json_field '.status')"
  echo "  status=${status}"
  if [[ "${status}" == "parsed" ]]; then
    PARSED=1
    echo "${batch_json}" | jq .
    break
  fi
  if [[ "${status}" == "failed" ]]; then
    echo "${batch_json}" | jq .
    fail "Parse failed"
  fi
  sleep 1
done
[[ "${PARSED}" -eq 1 ]] || fail "Timed out waiting for parse"

# ---------------------------------------------------------------------------
step 5 "Validate records"
# ---------------------------------------------------------------------------
validate_json="$(api POST "/imports/${BATCH_ID}/validate")"
echo "${validate_json}" | jq .
READY="$(echo "${validate_json}" | json_field '.ready_for_plan')"
[[ "${READY}" -ge 1 ]] || fail "Expected ready_for_plan >= 1, got ${READY}"

# ---------------------------------------------------------------------------
step 6 "Confirm READY_FOR_PLAN records"
# ---------------------------------------------------------------------------
records_json="$(api GET "/imports/${BATCH_ID}/records?limit=100")"
echo "${records_json}" | jq .
ready_count="$(echo "${records_json}" | jq '[.items[] | select(.validation_status=="READY_FOR_PLAN")] | length')"
[[ "${ready_count}" -ge 1 ]] || fail "No READY_FOR_PLAN records"

# ---------------------------------------------------------------------------
step 7 "Generate execution plan"
# ---------------------------------------------------------------------------
plan_json="$(api POST "/imports/${BATCH_ID}/generate-plan?created_by=e2e-script")"
echo "${plan_json}" | jq .
PLAN_ID="$(echo "${plan_json}" | json_field '.plan.id')"
JOB_COUNT="$(echo "${plan_json}" | json_field '.plan.job_count')"
[[ "${JOB_COUNT}" -ge 1 ]] || fail "Expected job_count >= 1"

# ---------------------------------------------------------------------------
step 8 "Confirm jobs waiting_dry_run"
# ---------------------------------------------------------------------------
jobs_json="$(api GET "/execution-plans/${PLAN_ID}/jobs")"
echo "${jobs_json}" | jq .
waiting="$(echo "${jobs_json}" | jq '[.items[] | select(.status=="waiting_dry_run")] | length')"
[[ "${waiting}" -ge 1 ]] || fail "Expected waiting_dry_run jobs"

JOB_IDS="$(echo "${jobs_json}" | jq -r '.items[].id')"

for JOB_ID in ${JOB_IDS}; do
  # ---------------------------------------------------------------------------
  step 9 "Mock dry-run job ${JOB_ID}"
  # ---------------------------------------------------------------------------
  dry_json="$(api POST "/execution-jobs/${JOB_ID}/dry-run")"
  echo "${dry_json}" | jq .
  dry_status="$(echo "${dry_json}" | json_field '.status')"
  mock_mode="$(echo "${dry_json}" | json_field '.mock_mode')"
  [[ "${mock_mode}" == "true" ]] || fail "mock_mode must be true"
  [[ "${dry_status}" == "dry_run_success" ]] || fail "Expected dry_run_success, got ${dry_status}"

  # ---------------------------------------------------------------------------
  step 10 "Confirm dry_run results for job ${JOB_ID}"
  # ---------------------------------------------------------------------------
  dry_results="$(api GET "/execution-jobs/${JOB_ID}/results?result_type=dry_run")"
  echo "${dry_results}" | jq .
  dry_total="$(echo "${dry_results}" | json_field '.total')"
  [[ "${dry_total}" -ge 1 ]] || fail "Expected dry_run results"
  bad_type="$(echo "${dry_results}" | jq '[.items[] | select(.result_type != "dry_run")] | length')"
  [[ "${bad_type}" -eq 0 ]] || fail "Non-dry_run rows in dry_run filter"

  # ---------------------------------------------------------------------------
  step 11 "Approve job ${JOB_ID}"
  # ---------------------------------------------------------------------------
  approve_json="$(api POST "/execution-jobs/${JOB_ID}/approve" \
    -H "Content-Type: application/json" \
    -d '{"reviewed_by":"e2e-script"}')"
  echo "${approve_json}" | jq .
  [[ "$(echo "${approve_json}" | json_field '.status')" == "approved" ]] || fail "Approve failed"

  # ---------------------------------------------------------------------------
  step 12 "Mock run job ${JOB_ID}"
  # ---------------------------------------------------------------------------
  run_json="$(api POST "/execution-jobs/${JOB_ID}/run")"
  echo "${run_json}" | jq .
  run_status="$(echo "${run_json}" | json_field '.status')"
  [[ "$(echo "${run_json}" | json_field '.mock_mode')" == "true" ]] || fail "mock_mode must be true"
  case "${run_status}" in
    success|failed|partially_failed) ;;
    *) fail "Unexpected final status: ${run_status}" ;;
  esac

  # ---------------------------------------------------------------------------
  step 13 "Confirm run results for job ${JOB_ID}"
  # ---------------------------------------------------------------------------
  run_results="$(api GET "/execution-jobs/${JOB_ID}/results?result_type=run")"
  echo "${run_results}" | jq .
  run_total="$(echo "${run_results}" | json_field '.total')"
  [[ "${run_total}" -ge 1 ]] || fail "Expected run results"
  bad_run="$(echo "${run_results}" | jq '[.items[] | select(.result_type != "run")] | length')"
  [[ "${bad_run}" -eq 0 ]] || fail "Non-run rows in run filter"

  # ---------------------------------------------------------------------------
  step 14 "Confirm final job status for job ${JOB_ID}"
  # ---------------------------------------------------------------------------
  final_status="$(echo "${run_results}" | json_field '.job_status')"
  echo "final job_status=${final_status}"
  case "${final_status}" in
    success|failed|partially_failed) ;;
    *) fail "Unexpected job_status: ${final_status}" ;;
  esac
done

# ---------------------------------------------------------------------------
step 15 "Dashboard summary (optional / Phase 7)"
# ---------------------------------------------------------------------------
dash_code="$(curl -sS -o "${TMP_DIR}/dash.json" -w "%{http_code}" \
  -H "X-Admin-Token: ${ADMIN_TOKEN}" "${API_BASE}/dashboard/summary" || true)"
echo "HTTP ${dash_code}"
if [[ -f "${TMP_DIR}/dash.json" ]]; then
  cat "${TMP_DIR}/dash.json"
  echo
fi
if [[ "${dash_code}" == "200" ]]; then
  echo "Dashboard counters returned (Phase 7+)."
elif [[ "${dash_code}" == "501" ]]; then
  echo "Dashboard not implemented yet (501) — accepted for Phase 6.5."
else
  echo "WARNING: unexpected dashboard status ${dash_code} (continuing)"
fi

echo
echo "============================================================"
echo " E2E MOCK WORKFLOW PASSED"
echo "============================================================"

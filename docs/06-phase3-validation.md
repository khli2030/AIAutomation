# Phase 3 — Record validation and rule-based classifier

## Scope

- `POST /imports/{batch_id}/validate`
- Works only on existing `raw_import_records`
- Sets `validation_status`, `task_code`, `record_hash`, `validation_error`
- Returns summary counters

## Explicitly out of scope

- AI Analyzer
- Execution plan generation
- Ansible / MOCK execution

## Status outcomes

`READY_FOR_PLAN`, `NEEDS_REVIEW`, `ASSET_NOT_FOUND`, `ALREADY_COMPLIANT`,
`DUPLICATE`, `INVALID_RECORD`, `UNSUPPORTED_CONTROL`

## Guardrails (merge checklist)

1. Unknown remediation → `NEEDS_REVIEW` only (never `READY_FOR_PLAN`)
2. `ASSET_NOT_FOUND` never becomes `READY_FOR_PLAN` (even with known task_code)
3. `ALREADY_COMPLIANT` never becomes `READY_FOR_PLAN`
4. `DUPLICATE` never becomes `READY_FOR_PLAN` (first hash wins)
5. `INVALID_RECORD` never becomes `READY_FOR_PLAN`
6. Classifier combines: `qualys_control_id`, `source_check_id`, `control_description`,
   `rationale`, `remediation`, `expected_configuration`
7. Validate path does not import/call Ansible, MOCK execution, AI Analyzer, or plan logic

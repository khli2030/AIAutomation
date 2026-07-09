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

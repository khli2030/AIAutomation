# Phase 2 — Excel upload and chunked Celery parse

## Scope

- `POST /imports/upload` (.xlsx only)
- Store under `UPLOAD_DIR/{batch_id}/` (host: `./data/uploads/{batch_id}/`)
- Celery parse with `openpyxl(read_only=True, data_only=True)`
- Chunk size default **1000**
- Required column validation + snake_case normalization
- Insert into `raw_import_records`
- Update `import_batches`: `total_records`, `valid_records`, `invalid_records`, `status`

## Explicitly not in Phase 2

- Remediation classification / task_code assignment
- Execution plan generation
- Real Ansible execution (`MOCK_MODE` unchanged)

## Status values

`uploaded` → `parsing` → `parsed` | `failed`

Any parse error (missing columns, I/O, unexpected exception) sets `import_batches.status = failed`.

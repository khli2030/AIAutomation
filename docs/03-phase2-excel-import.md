# Phase 2 — Excel upload and chunked parse

## What was added

| File | Purpose |
|------|---------|
| `backend/app/api/imports.py` | `POST /imports/upload`, `GET /imports/{id}`, `GET /imports/{id}/records` |
| `backend/app/services/excel_parser.py` | openpyxl `read_only` streaming + required column validation |
| `backend/app/services/import_service.py` | Safe upload storage + `import_batches` creation |
| `backend/app/services/import_persist.py` | Chunk insert into `raw_import_records` |
| `backend/app/services/record_hash.py` | SHA-256 hash helper (duplicate marking in Phase 3) |
| `backend/app/services/audit.py` | Audit log writer (`upload` / `parse`) |
| `backend/app/workers/tasks_import.py` | Celery parse job |
| `backend/app/schemas/imports.py` | Pydantic response models |
| `backend/alembic/versions/0002_drop_record_hash_unique.py` | Allow storing duplicate rows |
| `backend/tests/unit/test_excel_parser.py` | Parser / header / hash tests |

## Flow

```text
POST /imports/upload (.xlsx)
  → save under UPLOAD_DIR
  → create import_batches (status=uploaded)
  → audit: upload
  → Celery parse_excel_batch.delay(batch_id)
      → status=parsing
      → openpyxl read_only + chunk insert
      → status=parsed | columns_invalid | parse_failed
      → audit: parse
GET /imports/{batch_id}
GET /imports/{batch_id}/records?limit=&offset=
```

## Safety

- Remediation column is stored as text only — never executed.
- Only `.xlsx` uploads accepted.
- Filenames sanitized; files stored under UUID-prefixed names.
- Parse failures are recorded on the batch with `error_message`.

## Out of scope (Phase 3+)

Classification, asset matching, duplicate status marking, generate-plan.

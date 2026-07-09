# Phase 4 — AI Remediation Suggestions

## Scope

- `POST /imports/{batch_id}/ai-analyze-needs-review`
- `GET /ai-suggestions`
- `GET /ai-suggestions/{suggestion_id}`
- `POST /ai-suggestions/{suggestion_id}/approve`
- `POST /ai-suggestions/{suggestion_id}/reject`
- `POST /ai-suggestions/{suggestion_id}/convert-to-catalog`

MVP uses **mock AI provider only** (no external OpenAI/Claude calls).

## Explicitly out of scope

- Ansible / MOCK execution
- Execution plan generation
- Changing `MOCK_MODE`
- Auto-enabling catalog playbooks

## Safety rules

1. AI analyzes only `validation_status = NEEDS_REVIEW` records.
2. AI never executes anything.
3. AI never writes directly to `remediation_catalog`.
4. Suggestions are created as `draft` (or `unsupported_control`) in `ai_remediation_suggestions`.
5. Even confidence ≥ 0.90 requires human review.
6. SSH / SELinux / fstab / mount / permissions changes always require review.
7. AI-generated playbooks are never executable directly.
8. Only approved `remediation_catalog` playbooks with `is_enabled=true` may execute (later phases).
9. `convert-to-catalog` requires an **approved** suggestion.
10. Converted catalog entries are **disabled by default** unless an admin explicitly sets `enable=true`.

## Pre-merge review checklist

1. AI Analyzer only processes `NEEDS_REVIEW` records
2. Ignores `READY_FOR_PLAN`, `ASSET_NOT_FOUND`, `ALREADY_COMPLIANT`, `DUPLICATE`, `INVALID_RECORD`
3. AI provider is mock only (`get_ai_provider()` always returns `MockAIProvider`)
4. No external AI API calls (no openai/httpx/requests/urllib)
5. `generated_playbook` stored only as text on `ai_remediation_suggestions`
6. `generated_playbook` never written to `ansible/playbooks` (no filesystem writes)
7. `convert-to-catalog` requires approved suggestion
8. Converted `remediation_catalog` entry is disabled by default
9. approve/reject only change suggestion status (+ audit); no catalog write
10. No Ansible / subprocess / SSH / execution-plan logic on Phase 4 path

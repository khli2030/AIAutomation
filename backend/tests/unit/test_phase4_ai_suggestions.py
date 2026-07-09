"""Phase 4 tests: AI analyzer + suggestion review safety rules."""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.ai.provider import MockAIProvider
from app.constants.record_status import RecordStatus
from app.constants.suggestion_status import SuggestionStatus
from app.services.ai_analyzer import AIAnalyzerService, map_provider_result_to_suggestion_fields
from app.services.ai_suggestions import AISuggestionError, AISuggestionService

FORBIDDEN_IMPORT_ROOTS = {
    "ansible_execution",
    "real_ansible_runner",
    "subprocess",
    "ansible_runner",
    "paramiko",
    "openai",
}


def _imported_roots(module_file: str) -> set[str]:
    tree = ast.parse(Path(module_file).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            parts = node.module.split(".")
            imported.add(parts[0])
            imported.add(parts[-1])
            if len(parts) >= 2:
                imported.add(".".join(parts[-2:]))
    return imported


def _record(**kwargs: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "id": 1,
        "batch_id": 10,
        "row_number": 2,
        "device_name": "host-1",
        "validation_status": RecordStatus.NEEDS_REVIEW.value,
        "qualys_control_id": "Q-UNK",
        "source_check_id": "S-UNK",
        "control_description": "Custom control",
        "rationale": "Unknown rationale",
        "remediation": "Do something proprietary",
        "expected_configuration": "custom value",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _suggestion(**kwargs: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "id": 5,
        "raw_record_id": 1,
        "suggested_task_code": "AI_CUSTOM_CONTROL_1",
        "confidence": 0.91,
        "risk_level": "high",
        "target_file": "/etc/ssh/sshd_config",
        "setting_name": "CustomSetting",
        "expected_value": "yes",
        "ansible_module": "ansible.builtin.lineinfile",
        "generated_playbook": "# DRAFT ONLY\n- hosts: all\n",
        "validation_notes": "review me",
        "safety_warnings": "Human review required",
        "rollback_strategy": "restore backup",
        "status": SuggestionStatus.DRAFT.value,
        "reviewed_by": None,
        "reviewed_at": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class ScalarsResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values

    def first(self):
        return self._values[0] if self._values else None


def test_mock_provider_returns_structured_json() -> None:
    result = MockAIProvider().analyze(
        {
            "remediation": "Set PermitRootLogin no",
            "expected_configuration": "PermitRootLogin no",
        }
    )
    assert "classification" in result
    assert "remediation_plan" in result
    assert "safety" in result
    assert "ansible_draft" in result
    assert result["meta"]["provider"] == "mock"
    assert result["meta"]["executable"] is False
    assert result["safety"]["approval_required"] is True


def test_ai_suggestions_saved_as_draft_even_high_confidence() -> None:
    record = _record(remediation="Set PermitRootLogin no")
    result = MockAIProvider().analyze(
        {
            "remediation": record.remediation,
            "expected_configuration": "PermitRootLogin no",
        }
    )
    assert result["classification"]["confidence"] >= 0.90
    fields = map_provider_result_to_suggestion_fields(result, record=record)
    assert fields["status"] == SuggestionStatus.DRAFT.value
    assert "still requires human review" in (fields["safety_warnings"] or "").lower()
    assert "ssh" in (fields["safety_warnings"] or "").lower()


def test_analyze_batch_only_needs_review() -> None:
    records = [
        _record(id=1, validation_status=RecordStatus.NEEDS_REVIEW.value),
        _record(id=2, validation_status=RecordStatus.READY_FOR_PLAN.value),
        _record(id=3, validation_status=RecordStatus.ASSET_NOT_FOUND.value),
        _record(id=4, validation_status=RecordStatus.ALREADY_COMPLIANT.value),
    ]
    db = MagicMock()
    db.get.return_value = SimpleNamespace(id=10)
    db.scalars.return_value = ScalarsResult(records)

    service = AIAnalyzerService(db, provider=MockAIProvider())
    summary = service.analyze_batch_needs_review(10)

    assert summary.needs_review_records == 1
    assert summary.analyzed == 1
    assert summary.suggestions_created == 1
    assert summary.skipped_non_needs_review == 3
    from app.models.ai_remediation_suggestion import AIRemediationSuggestion

    suggestions = [
        c.args[0]
        for c in db.add.call_args_list
        if isinstance(c.args[0], AIRemediationSuggestion)
    ]
    assert len(suggestions) == 1
    assert suggestions[0].raw_record_id == 1
    assert suggestions[0].status == SuggestionStatus.DRAFT.value


def test_ready_for_plan_ignored() -> None:
    db = MagicMock()
    service = AIAnalyzerService(db, provider=MockAIProvider())
    result = service.analyze_record(
        _record(validation_status=RecordStatus.READY_FOR_PLAN.value)
    )
    assert result is None
    db.add.assert_not_called()


def test_asset_not_found_ignored() -> None:
    db = MagicMock()
    service = AIAnalyzerService(db, provider=MockAIProvider())
    result = service.analyze_record(
        _record(validation_status=RecordStatus.ASSET_NOT_FOUND.value)
    )
    assert result is None
    db.add.assert_not_called()


def test_already_compliant_ignored() -> None:
    db = MagicMock()
    service = AIAnalyzerService(db, provider=MockAIProvider())
    result = service.analyze_record(
        _record(validation_status=RecordStatus.ALREADY_COMPLIANT.value)
    )
    assert result is None
    db.add.assert_not_called()


def test_approve_changes_status_only() -> None:
    suggestion = _suggestion(status=SuggestionStatus.DRAFT.value)
    db = MagicMock()
    db.get.return_value = suggestion
    service = AISuggestionService(db)
    out = service.approve(5, reviewed_by="alice")
    assert out.status == SuggestionStatus.APPROVED.value
    assert out.reviewed_by == "alice"
    assert out.reviewed_at is not None
    # Must not create catalog entries on approve.
    assert db.add.call_count == 1  # audit log only
    db.commit.assert_called_once()


def test_reject_changes_status_only() -> None:
    suggestion = _suggestion(status=SuggestionStatus.DRAFT.value)
    db = MagicMock()
    db.get.return_value = suggestion
    service = AISuggestionService(db)
    out = service.reject(5, reviewed_by="bob")
    assert out.status == SuggestionStatus.REJECTED.value
    assert out.reviewed_by == "bob"
    assert db.add.call_count == 1  # audit only
    db.commit.assert_called_once()


def test_convert_requires_approved_suggestion() -> None:
    suggestion = _suggestion(status=SuggestionStatus.DRAFT.value)
    db = MagicMock()
    db.get.return_value = suggestion
    service = AISuggestionService(db)
    with pytest.raises(AISuggestionError, match="approved"):
        service.convert_to_catalog(5)
    db.commit.assert_not_called()


def test_convert_to_catalog_disabled_by_default() -> None:
    suggestion = _suggestion(
        status=SuggestionStatus.APPROVED.value,
        suggested_task_code="AI_NEW_CONTROL_XYZ",
    )
    db = MagicMock()
    db.get.return_value = suggestion
    db.scalars.return_value = ScalarsResult([])  # no existing catalog row

    # Capture catalog object added before suggestion status flip.
    added_catalogs: list[object] = []

    def _add(obj: object) -> None:
        added_catalogs.append(obj)

    db.add.side_effect = _add

    service = AISuggestionService(db)
    sug_out, catalog = service.convert_to_catalog(5, reviewed_by="admin")

    assert sug_out.status == SuggestionStatus.CONVERTED.value
    assert catalog.is_enabled is False
    assert catalog.task_code == "AI_NEW_CONTROL_XYZ"
    assert catalog.requires_approval is True
    assert catalog.requires_dry_run is True
    assert "ai_drafts/" in catalog.ansible_playbook_path


def test_convert_rejects_needs_review_task_code() -> None:
    suggestion = _suggestion(
        status=SuggestionStatus.APPROVED.value,
        suggested_task_code="NEEDS_REVIEW",
    )
    db = MagicMock()
    db.get.return_value = suggestion
    with pytest.raises(AISuggestionError, match="concrete task_code"):
        AISuggestionService(db).convert_to_catalog(5)


def test_generated_playbook_not_executable() -> None:
    """AI draft playbooks must never be treated as executable catalog playbooks."""
    record = _record(remediation="Set PermitRootLogin no")
    result = MockAIProvider().analyze({"remediation": record.remediation})
    fields = map_provider_result_to_suggestion_fields(result, record=record)
    playbook = fields["generated_playbook"] or ""
    assert "DRAFT ONLY" in playbook or playbook == ""
    assert fields["status"] != SuggestionStatus.APPROVED.value
    assert fields["status"] != SuggestionStatus.CONVERTED.value

    # convert path stores draft path under ai_drafts/ and keeps disabled
    suggestion = _suggestion(
        status=SuggestionStatus.APPROVED.value,
        suggested_task_code="AI_PLAYBOOK_SAFE_1",
        generated_playbook=playbook,
    )
    db = MagicMock()
    db.get.return_value = suggestion
    db.scalars.return_value = ScalarsResult([])
    _sug, catalog = AISuggestionService(db).convert_to_catalog(5)
    assert catalog.is_enabled is False
    # AnsibleExecutionService gates on is_enabled — disabled means not executable.


def test_phase4_modules_no_ansible_subprocess_ssh() -> None:
    import app.api.ai_suggestions as api_mod
    import app.api.imports as imports_mod
    import app.services.ai_analyzer as analyzer_mod
    import app.services.ai_suggestions as suggestions_mod
    import app.ai.provider as provider_mod

    for mod in (analyzer_mod, suggestions_mod, api_mod, provider_mod, imports_mod):
        roots = _imported_roots(mod.__file__)
        for forbidden in FORBIDDEN_IMPORT_ROOTS:
            assert forbidden not in roots, f"{mod.__name__} imports {forbidden}"

    # Analyzer must not import execution services.
    analyzer_src = Path(analyzer_mod.__file__).read_text(encoding="utf-8")
    assert "AnsibleExecutionService" not in analyzer_src
    assert "dry_run_job" not in analyzer_src
    assert "run_job" not in analyzer_src
    assert "RemediationCatalog" not in analyzer_src  # never writes catalog directly

    suggestions_src = Path(suggestions_mod.__file__).read_text(encoding="utf-8")
    assert "AnsibleExecutionService" not in suggestions_src
    assert "import subprocess" not in suggestions_src
    assert "from subprocess" not in suggestions_src


def test_ai_never_writes_catalog_during_analyze() -> None:
    from app.models.ai_remediation_suggestion import AIRemediationSuggestion
    from app.models.remediation_catalog import RemediationCatalog

    db = MagicMock()
    db.get.return_value = SimpleNamespace(id=10)
    db.scalars.return_value = ScalarsResult(
        [_record(id=1, validation_status=RecordStatus.NEEDS_REVIEW.value)]
    )
    AIAnalyzerService(db, provider=MockAIProvider()).analyze_batch_needs_review(10)
    added_objs = [c.args[0] for c in db.add.call_args_list]
    assert any(isinstance(obj, AIRemediationSuggestion) for obj in added_objs)
    assert not any(isinstance(obj, RemediationCatalog) for obj in added_objs)

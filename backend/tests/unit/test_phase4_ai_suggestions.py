"""Phase 4 tests: AI analyzer + suggestion review safety rules."""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.ai.provider import MockAIProvider, get_ai_provider
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
    "httpx",
    "requests",
    "urllib",
    "anthropic",
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
        _record(id=5, validation_status=RecordStatus.DUPLICATE.value),
        _record(id=6, validation_status=RecordStatus.INVALID_RECORD.value),
    ]
    db = MagicMock()
    db.get.return_value = SimpleNamespace(id=10)
    db.scalars.return_value = ScalarsResult(records)

    service = AIAnalyzerService(db, provider=MockAIProvider())
    summary = service.analyze_batch_needs_review(10)

    assert summary.needs_review_records == 1
    assert summary.analyzed == 1
    assert summary.suggestions_created == 1
    assert summary.skipped_non_needs_review == 5
    from app.models.ai_remediation_suggestion import AIRemediationSuggestion

    suggestions = [
        c.args[0]
        for c in db.add.call_args_list
        if isinstance(c.args[0], AIRemediationSuggestion)
    ]
    assert len(suggestions) == 1
    assert suggestions[0].raw_record_id == 1
    assert suggestions[0].status == SuggestionStatus.DRAFT.value


@pytest.mark.parametrize(
    "status",
    [
        RecordStatus.READY_FOR_PLAN.value,
        RecordStatus.ASSET_NOT_FOUND.value,
        RecordStatus.ALREADY_COMPLIANT.value,
        RecordStatus.DUPLICATE.value,
        RecordStatus.INVALID_RECORD.value,
    ],
)
def test_non_needs_review_statuses_ignored(status: str) -> None:
    db = MagicMock()
    service = AIAnalyzerService(db, provider=MockAIProvider())
    result = service.analyze_record(_record(validation_status=status))
    assert result is None
    db.add.assert_not_called()


def test_get_ai_provider_always_mock() -> None:
    """MVP: even when AI_ENABLED / non-mock settings are set, provider stays mock."""
    fake = SimpleNamespace(ai_enabled=True, ai_provider="openai", ai_api_key="sk-test")
    with patch("app.ai.provider.get_settings", return_value=fake):
        provider = get_ai_provider()
    assert isinstance(provider, MockAIProvider)


def test_provider_module_has_no_external_api_calls() -> None:
    import app.ai.provider as provider_mod

    src = Path(provider_mod.__file__).read_text(encoding="utf-8")
    roots = _imported_roots(provider_mod.__file__)
    for forbidden in ("openai", "httpx", "requests", "urllib", "anthropic", "aiohttp"):
        assert forbidden not in roots
        assert f"import {forbidden}" not in src
        assert f"from {forbidden}" not in src
    assert "api.openai.com" not in src
    assert "api.anthropic.com" not in src


def test_generated_playbook_stored_as_text_on_suggestion_only() -> None:
    from app.models.ai_remediation_suggestion import AIRemediationSuggestion

    db = MagicMock()
    record = _record(
        id=7,
        validation_status=RecordStatus.NEEDS_REVIEW.value,
        remediation="Set PermitRootLogin no",
    )
    suggestion = AIAnalyzerService(db, provider=MockAIProvider()).analyze_record(record)
    assert suggestion is not None
    assert isinstance(suggestion, AIRemediationSuggestion)
    assert isinstance(suggestion.generated_playbook, str)
    assert suggestion.generated_playbook  # non-empty draft text
    assert "DRAFT ONLY" in suggestion.generated_playbook


def test_generated_playbook_never_written_to_ansible_playbooks(tmp_path: Path) -> None:
    """Analyze + convert must not write any files under ansible/playbooks."""
    playbooks_dir = tmp_path / "ansible" / "playbooks"
    playbooks_dir.mkdir(parents=True)
    before = {p.name for p in playbooks_dir.iterdir()}

    db = MagicMock()
    db.get.return_value = SimpleNamespace(id=10)
    db.scalars.return_value = ScalarsResult(
        [
            _record(
                id=1,
                validation_status=RecordStatus.NEEDS_REVIEW.value,
                remediation="Set PermitRootLogin no",
            )
        ]
    )

    # Patch common filesystem write entry points; Phase 4 must not use them.
    with (
        patch("builtins.open", side_effect=AssertionError("open() must not be used")),
        patch.object(Path, "write_text", side_effect=AssertionError("write_text forbidden")),
        patch.object(Path, "write_bytes", side_effect=AssertionError("write_bytes forbidden")),
    ):
        AIAnalyzerService(db, provider=MockAIProvider()).analyze_batch_needs_review(10)

        suggestion = _suggestion(
            status=SuggestionStatus.APPROVED.value,
            suggested_task_code="AI_NO_DISK_WRITE",
            generated_playbook="# DRAFT ONLY\n",
        )
        db2 = MagicMock()
        db2.get.return_value = suggestion
        db2.scalars.return_value = ScalarsResult([])
        AISuggestionService(db2).convert_to_catalog(5)

    after = {p.name for p in playbooks_dir.iterdir()}
    assert after == before


def test_approve_changes_status_only() -> None:
    from app.models.remediation_catalog import RemediationCatalog

    suggestion = _suggestion(status=SuggestionStatus.DRAFT.value)
    original_playbook = suggestion.generated_playbook
    db = MagicMock()
    db.get.return_value = suggestion
    service = AISuggestionService(db)
    out = service.approve(5, reviewed_by="alice")
    assert out.status == SuggestionStatus.APPROVED.value
    assert out.reviewed_by == "alice"
    assert out.reviewed_at is not None
    assert out.generated_playbook == original_playbook
    added = [c.args[0] for c in db.add.call_args_list]
    assert not any(isinstance(obj, RemediationCatalog) for obj in added)
    assert db.add.call_count == 1  # audit log only
    db.commit.assert_called_once()


def test_reject_changes_status_only() -> None:
    from app.models.remediation_catalog import RemediationCatalog

    suggestion = _suggestion(status=SuggestionStatus.DRAFT.value)
    original_playbook = suggestion.generated_playbook
    db = MagicMock()
    db.get.return_value = suggestion
    service = AISuggestionService(db)
    out = service.reject(5, reviewed_by="bob")
    assert out.status == SuggestionStatus.REJECTED.value
    assert out.reviewed_by == "bob"
    assert out.generated_playbook == original_playbook
    added = [c.args[0] for c in db.add.call_args_list]
    assert not any(isinstance(obj, RemediationCatalog) for obj in added)
    assert db.add.call_count == 1  # audit only
    db.commit.assert_called_once()


def test_convert_requires_approved_suggestion() -> None:
    for status in (
        SuggestionStatus.DRAFT.value,
        SuggestionStatus.NEEDS_REVIEW.value,
        SuggestionStatus.REJECTED.value,
    ):
        suggestion = _suggestion(status=status)
        db = MagicMock()
        db.get.return_value = suggestion
        with pytest.raises(AISuggestionError, match="approved"):
            AISuggestionService(db).convert_to_catalog(5)
        db.commit.assert_not_called()


def test_convert_to_catalog_disabled_by_default() -> None:
    suggestion = _suggestion(
        status=SuggestionStatus.APPROVED.value,
        suggested_task_code="AI_NEW_CONTROL_XYZ",
    )
    db = MagicMock()
    db.get.return_value = suggestion
    db.scalars.return_value = ScalarsResult([])  # no existing catalog row

    service = AISuggestionService(db)
    sug_out, catalog = service.convert_to_catalog(5, reviewed_by="admin")

    assert sug_out.status == SuggestionStatus.CONVERTED.value
    assert catalog.is_enabled is False
    assert catalog.task_code == "AI_NEW_CONTROL_XYZ"
    assert catalog.requires_approval is True
    assert catalog.requires_dry_run is True
    assert "ai_drafts/" in catalog.ansible_playbook_path
    # Path is a DB string only — not under ansible/playbooks executable tree.
    assert not catalog.ansible_playbook_path.startswith("ansible/playbooks")


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


def test_phase4_modules_no_ansible_subprocess_ssh_or_plans() -> None:
    import app.api.ai_suggestions as api_mod
    import app.api.imports as imports_mod
    import app.services.ai_analyzer as analyzer_mod
    import app.services.ai_suggestions as suggestions_mod
    import app.ai.provider as provider_mod
    import app.workers.tasks_ai as tasks_mod

    for mod in (analyzer_mod, suggestions_mod, api_mod, provider_mod, tasks_mod):
        roots = _imported_roots(mod.__file__)
        for forbidden in FORBIDDEN_IMPORT_ROOTS:
            assert forbidden not in roots, f"{mod.__name__} imports {forbidden}"
        assert "execution_plans" not in roots
        assert "execution_plan" not in roots
        assert "plan_service" not in roots

    imports_roots = _imported_roots(imports_mod.__file__)
    for forbidden in ("ansible_execution", "real_ansible_runner", "subprocess", "paramiko"):
        assert forbidden not in imports_roots

    analyzer_src = Path(analyzer_mod.__file__).read_text(encoding="utf-8")
    assert "AnsibleExecutionService" not in analyzer_src
    assert "dry_run_job" not in analyzer_src
    assert "run_job" not in analyzer_src
    assert "RemediationCatalog" not in analyzer_src  # never writes catalog directly
    assert "open(" not in analyzer_src
    assert "write_text" not in analyzer_src

    suggestions_src = Path(suggestions_mod.__file__).read_text(encoding="utf-8")
    assert "AnsibleExecutionService" not in suggestions_src
    assert "import subprocess" not in suggestions_src
    assert "from subprocess" not in suggestions_src
    assert "open(" not in suggestions_src
    assert "write_text" not in suggestions_src
    # convert stores path string only; must not write playbook YAML to disk
    assert "generated_playbook" in suggestions_src  # referenced in audit only / not written
    assert "Path(" not in suggestions_src


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

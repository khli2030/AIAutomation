"""Phase 8B real Ansible readiness — safety gates, preflight, path validation."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.config import Settings, get_settings
from app.services.ansible_execution import (
    AnsibleExecutionError,
    AnsibleExecutionService,
    MockModeViolationError,
)
from app.services.ansible_safety import (
    RealAnsibleBlockedError,
    assert_job_targets_allow_real_ansible,
    assert_settings_allow_real_ansible,
    build_preflight_report,
    resolve_playbook_path,
    safe_resolve_under,
)


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _settings(**kwargs: object) -> Settings:
    defaults: dict[str, object] = {
        "mock_mode": True,
        "real_ansible_enabled": False,
        "app_env": "development",
        "admin_token": "test",
        "database_url": "postgresql+psycopg://x:x@localhost/x",
        "ansible_home": str(Path("/workspace/ansible")),
        "ansible_playbooks_dir": str(Path("/workspace/ansible/playbooks")),
        "ansible_inventories_dir": str(Path("/workspace/ansible/inventories")),
        "upload_dir": "/tmp/compliance-uploads",
        "runner_private_data_dir": "/tmp/compliance-runner",
        "tmp_inventory_dir": "/tmp/compliance-tmp-inv",
    }
    defaults.update(kwargs)
    return Settings(**defaults)  # type: ignore[arg-type]


def test_defaults_keep_mock_and_real_disabled() -> None:
    settings = Settings(
        admin_token="t",
        database_url="postgresql+psycopg://x:x@localhost/x",
    )
    assert settings.mock_mode is True
    assert settings.real_ansible_enabled is False


def test_mock_mode_true_uses_mock_only(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    sys.modules.pop("app.services.real_ansible_runner", None)
    db = MagicMock()
    job = SimpleNamespace(
        id=1,
        task_code="SSH_DISABLE_ROOT_LOGIN",
        status="waiting_dry_run",
        dry_run_status=None,
        started_at=None,
        finished_at=None,
        environment="test",
        targets=[],
    )
    catalog = SimpleNamespace(
        task_code="SSH_DISABLE_ROOT_LOGIN",
        is_enabled=True,
        ansible_playbook_path="ssh_disable_root_login.yml",
    )
    service = AnsibleExecutionService(db, settings=_settings(mock_mode=True))
    monkeypatch.setattr(service, "_load_job", lambda _id: job)
    monkeypatch.setattr(service, "_assert_catalog_allows", lambda _code: catalog)
    summary = service.dry_run_job(1)
    assert summary.mock_mode is True
    assert "app.services.real_ansible_runner" not in sys.modules


def test_real_ansible_enabled_false_blocks() -> None:
    with pytest.raises(RealAnsibleBlockedError, match="REAL_ANSIBLE_ENABLED=false"):
        assert_settings_allow_real_ansible(
            _settings(mock_mode=False, real_ansible_enabled=False, app_env="lab")
        )


def test_mock_false_and_real_disabled_blocks_execution() -> None:
    db = MagicMock()
    service = AnsibleExecutionService(
        db,
        settings=_settings(mock_mode=False, real_ansible_enabled=False, app_env="lab"),
    )
    job = SimpleNamespace(id=1, task_code="SSH_DISABLE_ROOT_LOGIN", environment="test")
    with pytest.raises(AnsibleExecutionError, match="REAL_ANSIBLE_ENABLED=false"):
        service._execute_real(job=job, mode="dry_run")
    # Blocked attempt audited
    assert db.add.called
    audit = db.add.call_args[0][0]
    details = json.loads(audit.details)
    assert details["event"] == "blocked"
    assert details["used_ai_generated_playbook"] is False
    assert details["used_remediation_text"] is False


def test_app_env_production_blocks() -> None:
    with pytest.raises(RealAnsibleBlockedError, match="APP_ENV"):
        assert_settings_allow_real_ansible(
            _settings(
                mock_mode=False,
                real_ansible_enabled=True,
                app_env="production",
            )
        )


def test_production_target_blocks() -> None:
    with pytest.raises(RealAnsibleBlockedError, match="production"):
        assert_job_targets_allow_real_ansible(job_environment="production")


def test_staging_target_blocks() -> None:
    with pytest.raises(RealAnsibleBlockedError, match="staging"):
        assert_job_targets_allow_real_ansible(job_environment="staging")


def test_lab_and_test_targets_allowed_for_readiness() -> None:
    assert_job_targets_allow_real_ansible(job_environment="lab")
    assert_job_targets_allow_real_ansible(job_environment="test")


def test_path_traversal_in_playbook_blocked(tmp_path: Path) -> None:
    playbooks = tmp_path / "playbooks"
    playbooks.mkdir()
    settings = _settings(ansible_playbooks_dir=str(playbooks))
    with pytest.raises(RealAnsibleBlockedError, match="traversal|Absolute"):
        resolve_playbook_path(settings, "../etc/passwd")
    with pytest.raises(RealAnsibleBlockedError, match="traversal|Absolute"):
        safe_resolve_under(playbooks, "../../secret.yml", kind="playbook")


def test_missing_playbook_clear_error(tmp_path: Path) -> None:
    playbooks = tmp_path / "playbooks"
    playbooks.mkdir()
    settings = _settings(ansible_playbooks_dir=str(playbooks))
    with pytest.raises(RealAnsibleBlockedError, match="not found"):
        resolve_playbook_path(settings, "does_not_exist.yml")


def test_ai_generated_playbook_never_used_by_adapter() -> None:
    from app.services import real_ansible_runner as real_mod

    src = Path(real_mod.__file__).read_text(encoding="utf-8")
    assert "generated_playbook" in src  # mentioned as forbidden
    assert "never" in src.lower()
    assert "Remediation" in src or "remediation text" in src.lower()
    # Adapter must require catalog playbook path, not AI fields.
    assert "ansible_playbook_path" in src
    assert "from app.models.ai_remediation_suggestion" not in src


def test_no_raw_remediation_text_execution() -> None:
    import ast

    import app.services.ansible_execution as ae_mod
    import app.services.real_ansible_runner as real_mod

    for mod in (ae_mod, real_mod):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert "used_remediation_text" in src or "remediation text" in src.lower()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Forbid os.system(...) / subprocess.* calls in these modules.
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr in {
                    "system",
                    "Popen",
                    "run",
                    "call",
                    "check_call",
                    "check_output",
                }:
                    # Allow ansible_runner.run only inside real_ansible_runner.
                    if mod is real_mod and func.attr == "run":
                        continue
                    # Attribute on Name: os.system / subprocess.run
                    if isinstance(func.value, ast.Name) and func.value.id in {
                        "os",
                        "subprocess",
                    }:
                        raise AssertionError(
                            f"Forbidden call {func.value.id}.{func.attr} in {mod.__file__}"
                        )
        assert "shell=True" not in src
        assert "from subprocess" not in src
        assert "import subprocess" not in src


def test_preflight_returns_expected_checks(tmp_path: Path) -> None:
    playbooks = tmp_path / "playbooks"
    inventories = tmp_path / "inventories"
    home = tmp_path / "ansible"
    playbooks.mkdir()
    inventories.mkdir()
    home.mkdir()
    (playbooks / "ssh_disable_root_login.yml").write_text("---\n")
    (inventories / "test.ini").write_text("[linux_test]\n")

    settings = _settings(
        mock_mode=True,
        real_ansible_enabled=False,
        app_env="development",
        ansible_home=str(home),
        ansible_playbooks_dir=str(playbooks),
        ansible_inventories_dir=str(inventories),
        upload_dir=str(tmp_path / "uploads"),
        runner_private_data_dir=str(tmp_path / "runner"),
        tmp_inventory_dir=str(tmp_path / "tmpinv"),
    )
    report = build_preflight_report(
        settings, enabled_catalog_paths=["ssh_disable_root_login.yml"]
    )
    names = {c.name for c in report.checks}
    for required in (
        "mock_mode",
        "real_ansible_enabled",
        "app_env",
        "ansible_runner",
        "ansible_project_dir",
        "playbooks_dir",
        "inventories_dir",
        "enabled_catalog_playbooks",
        "ai_draft_playbooks_not_executable",
        "playbooks_readable",
        "runtime_artifacts_writable",
    ):
        assert required in names
    assert report.mock_mode is True
    assert report.real_ansible_enabled is False
    assert report.real_ansible_allowed is False
    assert any("MOCK_MODE" in b for b in report.blockers)


def test_preflight_lab_ready_when_gates_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    playbooks = tmp_path / "playbooks"
    inventories = tmp_path / "inventories"
    home = tmp_path / "ansible"
    playbooks.mkdir()
    inventories.mkdir()
    home.mkdir()
    (playbooks / "ok.yml").write_text("---\n")
    (inventories / "test.ini").write_text("[linux_test]\n")

    monkeypatch.setattr(
        "app.services.ansible_safety.ansible_runner_available",
        lambda: (True, "ansible-runner importable"),
    )
    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        app_env="lab",
        ansible_home=str(home),
        ansible_playbooks_dir=str(playbooks),
        ansible_inventories_dir=str(inventories),
        upload_dir=str(tmp_path / "uploads"),
        runner_private_data_dir=str(tmp_path / "runner"),
        tmp_inventory_dir=str(tmp_path / "tmpinv"),
    )
    report = build_preflight_report(settings, enabled_catalog_paths=["ok.yml"])
    assert report.real_ansible_allowed is True
    assert report.blockers == []


def test_execute_real_blocks_production_target_and_audits() -> None:
    db = MagicMock()
    service = AnsibleExecutionService(
        db,
        settings=_settings(
            mock_mode=False,
            real_ansible_enabled=True,
            app_env="lab",
        ),
    )
    job = SimpleNamespace(
        id=42,
        task_code="SSH_DISABLE_ROOT_LOGIN",
        environment="production",
        targets=[],
    )
    catalog = SimpleNamespace(
        task_code="SSH_DISABLE_ROOT_LOGIN",
        is_enabled=True,
        ansible_playbook_path="ssh_disable_root_login.yml",
    )
    with pytest.raises(AnsibleExecutionError, match="production"):
        service._execute_real(job=job, mode="dry_run", catalog=catalog)
    audit = db.add.call_args[0][0]
    details = json.loads(audit.details)
    assert details["event"] == "blocked"
    assert details["job_environment"] == "production"


def test_missing_ansible_runner_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.ansible_safety import assert_ansible_runner_available, AnsibleRunnerMissingError

    monkeypatch.setattr(
        "app.services.ansible_safety.ansible_runner_available",
        lambda: (False, "ansible-runner is not installed"),
    )
    with pytest.raises(AnsibleRunnerMissingError, match="ansible-runner is not installed"):
        assert_ansible_runner_available()


def test_mock_mode_true_still_blocks_real_path() -> None:
    db = MagicMock()
    service = AnsibleExecutionService(db, settings=_settings(mock_mode=True))
    job = SimpleNamespace(id=1, task_code="X", environment="test")
    with pytest.raises(MockModeViolationError):
        service._execute_real(job=job, mode="dry_run")


def test_preflight_does_not_import_ansible_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guarantee 7/19: preflight must not load ansible_runner into sys.modules."""
    import sys
    import types

    sys.modules.pop("ansible_runner", None)
    # Pretend the package exists without importing it.
    fake_spec = types.SimpleNamespace(name="ansible_runner")
    monkeypatch.setattr(
        "importlib.util.find_spec",
        lambda name: fake_spec if name == "ansible_runner" else None,
    )
    from app.services.ansible_safety import ansible_runner_available, build_preflight_report

    ok, detail = ansible_runner_available()
    assert ok is True
    assert "ansible_runner" not in sys.modules

    report = build_preflight_report(
        _settings(mock_mode=True),
        enabled_catalog_paths=[],
    )
    assert any(c.name == "ansible_runner" and c.ok for c in report.checks)
    assert "ansible_runner" not in sys.modules

    # Mock path must still be safe after preflight (clear leftover real adapter
    # imports from other tests in this process).
    sys.modules.pop("app.services.real_ansible_runner", None)
    service = AnsibleExecutionService(
        MagicMock(), settings=_settings(mock_mode=True)
    )
    service._assert_mock_mode_safe()


def test_symlink_escape_from_playbooks_blocked(tmp_path: Path) -> None:
    playbooks = tmp_path / "playbooks"
    outside = tmp_path / "outside"
    playbooks.mkdir()
    outside.mkdir()
    secret = outside / "secret.yml"
    secret.write_text("---\n")
    link = playbooks / "escape.yml"
    link.symlink_to(secret)

    settings = _settings(ansible_playbooks_dir=str(playbooks))
    with pytest.raises(RealAnsibleBlockedError, match="traversal|escapes"):
        resolve_playbook_path(settings, "escape.yml")


def test_real_apply_blocked_in_phase8b(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Live apply must not call ansible_runner.run in Phase 8B."""
    playbooks = tmp_path / "playbooks"
    inventories = tmp_path / "inventories"
    playbooks.mkdir()
    inventories.mkdir()
    (playbooks / "ok.yml").write_text("---\n")
    (inventories / "test.ini").write_text("[linux_test]\n")

    monkeypatch.setattr(
        "app.services.ansible_safety.ansible_runner_available",
        lambda: (True, "ansible-runner package found (not imported)"),
    )
    from app.services.real_ansible_runner import run_with_ansible_runner

    job = SimpleNamespace(id=9, environment="lab", targets=[])
    catalog = SimpleNamespace(
        task_code="T",
        is_enabled=True,
        ansible_playbook_path="ok.yml",
    )
    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        app_env="lab",
        ansible_playbooks_dir=str(playbooks),
        ansible_inventories_dir=str(inventories),
    )
    with pytest.raises(RealAnsibleBlockedError, match="blocks real apply"):
        run_with_ansible_runner(job=job, mode="apply", catalog=catalog, settings=settings)


def test_real_dry_run_readiness_does_not_call_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    playbooks = tmp_path / "playbooks"
    inventories = tmp_path / "inventories"
    playbooks.mkdir()
    inventories.mkdir()
    (playbooks / "ok.yml").write_text("---\n")
    (inventories / "test.ini").write_text("[linux_test]\n")

    monkeypatch.setattr(
        "app.services.ansible_safety.ansible_runner_available",
        lambda: (True, "ansible-runner package found (not imported)"),
    )
    import sys

    sys.modules.pop("ansible_runner", None)
    from app.services.real_ansible_runner import run_with_ansible_runner

    job = SimpleNamespace(id=9, environment="test", targets=[])
    catalog = SimpleNamespace(
        task_code="T",
        is_enabled=True,
        ansible_playbook_path="ok.yml",
    )
    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        app_env="test",
        ansible_playbooks_dir=str(playbooks),
        ansible_inventories_dir=str(inventories),
    )
    with pytest.raises(RealAnsibleBlockedError) as exc:
        run_with_ansible_runner(
            job=job, mode="dry_run", catalog=catalog, settings=settings
        )
    assert exc.value.code == "phase8b_readiness_only"
    assert "ansible_runner" not in sys.modules


def test_blocked_audit_includes_actor_role_job_and_reason() -> None:
    db = MagicMock()
    service = AnsibleExecutionService(
        db,
        settings=_settings(
            mock_mode=False,
            real_ansible_enabled=False,
            app_env="lab",
        ),
    )
    job = SimpleNamespace(id=77, task_code="SSH_DISABLE_ROOT_LOGIN", environment="test")
    with pytest.raises(AnsibleExecutionError):
        service._execute_real(
            job=job, mode="dry_run", actor="role:operator", role="operator"
        )
    audit = db.add.call_args[0][0]
    assert audit.actor == "role:operator"
    assert audit.entity_id == "77"
    details = json.loads(audit.details)
    assert details["event"] == "blocked"
    assert details["auth_role"] == "operator"
    assert "REAL_ANSIBLE_ENABLED=false" in details["reason"]
    assert details["used_ai_generated_playbook"] is False
    assert details["used_remediation_text"] is False


def test_inventory_path_stays_under_inventories(tmp_path: Path) -> None:
    inventories = tmp_path / "inventories"
    inventories.mkdir()
    (inventories / "test.ini").write_text("[linux_test]\n")
    settings = _settings(ansible_inventories_dir=str(inventories))
    from app.services.ansible_safety import resolve_inventory_path

    path = resolve_inventory_path(settings, "test")
    assert path.is_file()
    assert path.resolve().is_relative_to(inventories.resolve())
    with pytest.raises(RealAnsibleBlockedError):
        resolve_inventory_path(settings, "production")


def test_disabled_catalog_cannot_provide_playbook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    playbooks = tmp_path / "playbooks"
    inventories = tmp_path / "inventories"
    playbooks.mkdir()
    inventories.mkdir()
    (playbooks / "ok.yml").write_text("---\n")
    (inventories / "test.ini").write_text("[linux_test]\n")
    monkeypatch.setattr(
        "app.services.ansible_safety.ansible_runner_available",
        lambda: (True, "ok"),
    )
    from app.services.real_ansible_runner import run_with_ansible_runner

    job = SimpleNamespace(id=1, environment="lab", targets=[])
    catalog = SimpleNamespace(
        task_code="T",
        is_enabled=False,
        ansible_playbook_path="ok.yml",
    )
    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        app_env="lab",
        ansible_playbooks_dir=str(playbooks),
        ansible_inventories_dir=str(inventories),
    )
    with pytest.raises(RealAnsibleBlockedError, match="disabled"):
        run_with_ansible_runner(
            job=job, mode="dry_run", catalog=catalog, settings=settings
        )

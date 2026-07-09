"""Phase 7 dashboard / list API unit tests (no Ansible)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.config import Settings
from app.services.dashboard import DashboardService


def test_dashboard_summary_includes_mock_mode_and_counters() -> None:
    db = MagicMock()
    # count scalars: imports, records, jobs, plans, suggestions
    db.scalar.side_effect = [3, 10, 5, 2, 4]
    # group_by execute results for 4 _count_by calls
    db.execute.side_effect = [
        MagicMock(all=lambda: [("parsed", 2), ("uploaded", 1)]),
        MagicMock(all=lambda: [("READY_FOR_PLAN", 7), ("NEEDS_REVIEW", 3)]),
        MagicMock(all=lambda: [("waiting_dry_run", 3), ("success", 2)]),
        MagicMock(all=lambda: [("draft", 4)]),
    ]
    # latest batches / jobs
    batch = SimpleNamespace(
        id=1,
        original_filename="a.xlsx",
        stored_path="/tmp/a.xlsx",
        status="parsed",
        total_records=2,
        valid_records=2,
        invalid_records=0,
        total_rows=2,
        processed_rows=2,
        uploaded_by="op",
        error_message=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    job = SimpleNamespace(
        id=9,
        plan_id=1,
        task_code="SSH_DISABLE_ROOT_LOGIN",
        environment="test",
        criticality="High",
        ansible_group="linux_test",
        status="waiting_dry_run",
        dry_run_status=None,
        approved_by=None,
        approved_at=None,
        started_at=None,
        finished_at=None,
    )

    class Scalars:
        def __init__(self, values):
            self._values = values

        def all(self):
            return self._values

    db.scalars.side_effect = [Scalars([batch]), Scalars([job])]

    settings = Settings(mock_mode=True, admin_token="t", database_url="sqlite://")
    from unittest.mock import patch

    with patch("app.services.dashboard.PlanQueryService") as pq_cls:
        pq_cls.return_value.count_job_targets.return_value = 2
        summary = DashboardService(db, settings=settings).summary(latest_limit=5)
    assert summary.mock_mode is True
    assert summary.import_batches_total == 3
    assert summary.records_total == 10
    assert summary.jobs_total == 5
    assert summary.plans_total == 2
    assert summary.suggestions_total == 4
    assert summary.import_batches_by_status["parsed"] == 2
    assert summary.records_by_validation_status["READY_FOR_PLAN"] == 7
    assert len(summary.latest_imports) == 1
    assert summary.latest_imports[0].id == 1

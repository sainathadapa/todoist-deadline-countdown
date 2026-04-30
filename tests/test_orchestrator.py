from datetime import date
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from countdown.__main__ import run


def _task(task_id: str, content: str, deadline_iso: str | None):
    """Build a fake Task object the orchestrator can consume."""
    deadline = MagicMock()
    if deadline_iso is None:
        deadline = None
    else:
        deadline.date = deadline_iso
    return MagicMock(id=task_id, content=content, deadline=deadline)


def test_run_appends_suffix_to_deadlined_tasks() -> None:
    today = date(2026, 4, 29)
    client = MagicMock()
    client.list_deadlined_tasks.return_value = [
        _task("1", "File 2026 taxes", "2026-05-14"),  # 15 days -> T-2w
    ]
    client.list_suffixed_tasks.return_value = []

    summary = run(client=client, today=today, tz=ZoneInfo("America/New_York"), dry_run=False)

    client.update_content.assert_called_once_with(task_id="1", content="File 2026 taxes [T-2w]")
    assert summary.scanned == 1
    assert summary.updated == 1
    assert summary.errors == 0


def test_run_is_idempotent_skips_unchanged_content() -> None:
    today = date(2026, 4, 29)
    client = MagicMock()
    client.list_deadlined_tasks.return_value = [
        _task("1", "File 2026 taxes [T-2w]", "2026-05-14"),
    ]
    client.list_suffixed_tasks.return_value = client.list_deadlined_tasks.return_value

    summary = run(client=client, today=today, tz=ZoneInfo("America/New_York"), dry_run=False)

    client.update_content.assert_not_called()
    assert summary.updated == 0


def test_run_strips_suffix_when_deadline_removed() -> None:
    today = date(2026, 4, 29)
    no_deadline_task = _task("9", "Old task [T-3d]", deadline_iso=None)
    client = MagicMock()
    client.list_deadlined_tasks.return_value = []
    client.list_suffixed_tasks.return_value = [no_deadline_task]

    summary = run(client=client, today=today, tz=ZoneInfo("America/New_York"), dry_run=False)

    client.update_content.assert_called_once_with(task_id="9", content="Old task")
    assert summary.stripped == 1


def test_run_dry_run_does_not_write() -> None:
    today = date(2026, 4, 29)
    client = MagicMock()
    client.list_deadlined_tasks.return_value = [
        _task("1", "File 2026 taxes", "2026-05-14"),
    ]
    client.list_suffixed_tasks.return_value = []

    summary = run(client=client, today=today, tz=ZoneInfo("America/New_York"), dry_run=True)

    client.update_content.assert_not_called()
    assert summary.updated == 1  # counted as "would update"


def test_run_continues_on_single_task_error_and_reports_count() -> None:
    today = date(2026, 4, 29)
    client = MagicMock()
    client.list_deadlined_tasks.return_value = [
        _task("1", "ok task", "2026-05-14"),
        _task("2", "bad task", "2026-05-14"),
    ]
    client.list_suffixed_tasks.return_value = []

    def update_side_effect(task_id: str, content: str) -> None:
        if task_id == "2":
            raise RuntimeError("simulated")

    client.update_content.side_effect = update_side_effect

    summary = run(client=client, today=today, tz=ZoneInfo("America/New_York"), dry_run=False)

    assert summary.updated == 1
    assert summary.errors == 1
    assert client.update_content.call_count == 2


def test_run_skips_task_with_empty_content() -> None:
    today = date(2026, 4, 29)
    client = MagicMock()
    client.list_deadlined_tasks.return_value = [_task("1", "", "2026-05-14")]
    client.list_suffixed_tasks.return_value = []

    summary = run(client=client, today=today, tz=ZoneInfo("America/New_York"), dry_run=False)

    client.update_content.assert_not_called()
    assert summary.updated == 0


from datetime import datetime as _dt


def test_run_handles_datetime_in_deadline_field() -> None:
    """The SDK's ApiDue Union allows datetime; ensure we narrow to date."""
    today = date(2026, 4, 29)
    task = MagicMock(
        id="dt",
        content="Renew passport",
        deadline=MagicMock(date=_dt(2026, 5, 14, 12, 0, 0)),
    )
    client = MagicMock()
    client.list_deadlined_tasks.return_value = [task]
    client.list_suffixed_tasks.return_value = []

    summary = run(client=client, today=today, tz=ZoneInfo("America/New_York"), dry_run=False)

    client.update_content.assert_called_once_with(
        task_id="dt", content="Renew passport [T-2w]"
    )
    assert summary.updated == 1
    assert summary.errors == 0


from unittest.mock import patch


def test_main_doctor_subcommand_prints_user_and_returns_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("TODOIST_API_TOKEN", "test-token")

    fake_client = MagicMock()
    fake_client.fetch_user_timezone.return_value = "America/New_York"

    with patch("countdown.__main__.TodoistClient", return_value=fake_client):
        from countdown.__main__ import main
        rc = main(["doctor"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "America/New_York" in out

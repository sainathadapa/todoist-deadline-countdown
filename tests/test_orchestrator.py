from datetime import date
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from countdown.__main__ import run


def _task(
    task_id: str,
    content: str,
    deadline_iso: str | None,
    *,
    parent_id: str | None = None,
    is_completed: bool = False,
    created_at=None,
):
    """Build a fake Task object the orchestrator can consume."""
    deadline = MagicMock()
    if deadline_iso is None:
        deadline = None
    else:
        deadline.date = deadline_iso
    return MagicMock(
        id=task_id,
        content=content,
        deadline=deadline,
        parent_id=parent_id,
        is_completed=is_completed,
        created_at=created_at,
    )


def test_run_prepends_marker_to_deadlined_tasks() -> None:
    today = date(2026, 4, 29)
    client = MagicMock()
    client.list_deadlined_tasks.return_value = [
        _task("1", "File 2026 taxes", "2026-05-14"),  # 15 days -> T-15d
    ]
    client.list_active_tasks.return_value = []
    client.list_marked_tasks.return_value = []

    summary = run(client=client, today=today, tz=ZoneInfo("America/New_York"), dry_run=False)

    client.update_content.assert_called_once_with(task_id="1", content="[T-15d] File 2026 taxes")
    assert summary.scanned == 1
    assert summary.updated == 1
    assert summary.errors == 0


def test_run_is_idempotent_skips_unchanged_content() -> None:
    today = date(2026, 4, 29)
    client = MagicMock()
    client.list_deadlined_tasks.return_value = [
        _task("1", "[T-15d] File 2026 taxes", "2026-05-14"),
    ]
    client.list_active_tasks.return_value = []
    client.list_marked_tasks.return_value = client.list_deadlined_tasks.return_value

    summary = run(client=client, today=today, tz=ZoneInfo("America/New_York"), dry_run=False)

    client.update_content.assert_not_called()
    assert summary.updated == 0


def test_run_strips_marker_when_deadline_removed() -> None:
    today = date(2026, 4, 29)
    no_deadline_task = _task("9", "[T-3d] Old task", deadline_iso=None)
    client = MagicMock()
    client.list_deadlined_tasks.return_value = []
    client.list_active_tasks.return_value = []
    client.list_marked_tasks.return_value = [no_deadline_task]

    summary = run(client=client, today=today, tz=ZoneInfo("America/New_York"), dry_run=False)

    client.update_content.assert_called_once_with(task_id="9", content="Old task")
    assert summary.stripped == 1


def test_run_with_no_deadlined_tasks_does_not_fetch_active_tasks() -> None:
    today = date(2026, 4, 29)
    client = MagicMock()
    client.list_deadlined_tasks.return_value = []
    client.list_marked_tasks.return_value = []

    summary = run(client=client, today=today, tz=ZoneInfo("America/New_York"), dry_run=False)

    client.list_active_tasks.assert_not_called()
    assert summary.scanned == 0


def test_run_dry_run_does_not_write() -> None:
    today = date(2026, 4, 29)
    client = MagicMock()
    client.list_deadlined_tasks.return_value = [
        _task("1", "File 2026 taxes", "2026-05-14"),
    ]
    client.list_active_tasks.return_value = []
    client.list_marked_tasks.return_value = []

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
    client.list_active_tasks.return_value = []
    client.list_marked_tasks.return_value = []

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
    client.list_active_tasks.return_value = []
    client.list_marked_tasks.return_value = []

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
    client.list_active_tasks.return_value = []
    client.list_marked_tasks.return_value = []

    summary = run(client=client, today=today, tz=ZoneInfo("America/New_York"), dry_run=False)

    client.update_content.assert_called_once_with(
        task_id="dt", content="[T-15d] Renew passport"
    )
    assert summary.updated == 1
    assert summary.errors == 0


def test_run_adds_progress_suffix_for_parent_task() -> None:
    today = date(2026, 4, 29)
    client = MagicMock()
    parent = _task("parent", "Project launch", "2026-05-14")
    sub_todo_1 = _task("s1", "Todo child 1", None, parent_id="parent", is_completed=False)
    sub_todo_2 = _task("s2", "Todo child 2", None, parent_id="parent", is_completed=False)
    client.list_deadlined_tasks.return_value = [parent]
    client.list_active_tasks.return_value = [parent, sub_todo_1, sub_todo_2]
    client.list_completed_subtasks_for_parent.return_value = [{"id": "done-1"}]
    client.list_marked_tasks.return_value = [parent]

    summary = run(client=client, today=today, tz=ZoneInfo("America/New_York"), dry_run=False)

    client.update_content.assert_called_once_with(
        task_id="parent", content="[T-15d] Project launch [1/3]"
    )
    assert summary.updated == 1


def test_run_with_no_subtasks_keeps_user_authored_trailing_ratio() -> None:
    today = date(2026, 4, 29)
    client = MagicMock()
    parent = _task("parent", "[T-15d] Project launch [7/13]", "2026-05-14")
    client.list_deadlined_tasks.return_value = [parent]
    client.list_active_tasks.return_value = [parent]
    client.list_marked_tasks.return_value = [parent]

    summary = run(client=client, today=today, tz=ZoneInfo("America/New_York"), dry_run=False)

    client.update_content.assert_not_called()
    assert summary.updated == 0


def test_run_is_idempotent_when_marker_and_progress_are_already_correct() -> None:
    today = date(2026, 4, 29)
    client = MagicMock()
    parent = _task("parent", "[T-15d] Project launch [1/2]", "2026-05-14")
    sub_todo = _task("s2", "Todo child", None, parent_id="parent", is_completed=False)
    client.list_deadlined_tasks.return_value = [parent]
    client.list_active_tasks.return_value = [parent, sub_todo]
    client.list_completed_subtasks_for_parent.return_value = [{"id": "done-1"}]
    client.list_marked_tasks.return_value = [parent]

    summary = run(client=client, today=today, tz=ZoneInfo("America/New_York"), dry_run=False)

    client.update_content.assert_not_called()
    assert summary.updated == 0


def test_run_continues_when_active_task_fetch_fails() -> None:
    today = date(2026, 4, 29)
    client = MagicMock()
    client.list_deadlined_tasks.return_value = [_task("1", "File 2026 taxes", "2026-05-14")]
    client.list_active_tasks.side_effect = RuntimeError("simulated active task failure")
    client.list_marked_tasks.return_value = []

    summary = run(client=client, today=today, tz=ZoneInfo("America/New_York"), dry_run=False)

    client.update_content.assert_called_once_with(task_id="1", content="[T-15d] File 2026 taxes")
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


def test_write_step_summary_renders_table_to_github_step_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from countdown.__main__ import Summary, _write_step_summary

    summary_file = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

    _write_step_summary(Summary(scanned=12, updated=3, stripped=1, errors=0), dry_run=False)

    text = summary_file.read_text(encoding="utf-8")
    assert "Countdown run" in text
    assert "| 12 | 3 | 1 | 0 |" in text


def test_write_step_summary_marks_dry_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from countdown.__main__ import Summary, _write_step_summary

    summary_file = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

    _write_step_summary(Summary(scanned=2, updated=2, stripped=0, errors=0), dry_run=True)

    assert "dry-run" in summary_file.read_text(encoding="utf-8")


def test_write_step_summary_noop_when_env_not_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from countdown.__main__ import Summary, _write_step_summary

    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    # Should not raise even though no path is set.
    _write_step_summary(Summary(), dry_run=False)


def test_main_strip_all_strips_marker_from_every_marked_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TODOIST_API_TOKEN", "test-token")

    marked = [
        MagicMock(id="A", content="[T-2w] task one"),
        MagicMock(id="B", content="[T+1d] task two"),
    ]
    fake_client = MagicMock()
    fake_client.list_marked_tasks.return_value = marked

    with patch("countdown.__main__.TodoistClient", return_value=fake_client):
        from countdown.__main__ import main
        rc = main(["--strip-all"])

    assert rc == 0
    fake_client.update_content.assert_any_call(task_id="A", content="task one")
    fake_client.update_content.assert_any_call(task_id="B", content="task two")
    assert fake_client.update_content.call_count == 2

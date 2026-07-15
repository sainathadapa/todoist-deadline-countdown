from datetime import date, datetime as _dt, timezone
from unittest.mock import MagicMock, call, patch
from zoneinfo import ZoneInfo

import pytest

from countdown.__main__ import run


def _task(
    task_id: str,
    content: str,
    deadline_iso: str | None,
    *,
    recurring: bool = False,
    parent_id: str | None = None,
    is_completed: bool = False,
    created_at=None,
):
    """Build a fake Task object the orchestrator can consume."""
    deadline = None if deadline_iso is None else MagicMock(date=deadline_iso)
    due = MagicMock(is_recurring=recurring) if recurring else None
    return MagicMock(
        id=task_id,
        content=content,
        deadline=deadline,
        due=due,
        parent_id=parent_id,
        is_completed=is_completed,
        created_at=created_at,
    )


def test_run_prepends_marker_to_deadlined_tasks() -> None:
    today = date(2026, 4, 29)
    client = MagicMock()
    client.list_active_tasks.return_value = [
        _task("1", "File 2026 taxes", "2026-05-14"),  # 15 days -> T-15d
    ]

    summary = run(client=client, today=today, tz=ZoneInfo("America/New_York"), dry_run=False)

    client.update_content.assert_called_once_with(task_id="1", content="[T-15d] File 2026 taxes")
    assert summary.scanned == 1
    assert summary.updated == 1
    assert summary.errors == 0


def test_run_is_idempotent_skips_unchanged_content() -> None:
    today = date(2026, 4, 29)
    client = MagicMock()
    client.list_active_tasks.return_value = [
        _task("1", "[T-15d] File 2026 taxes", "2026-05-14"),
    ]

    summary = run(client=client, today=today, tz=ZoneInfo("America/New_York"), dry_run=False)

    client.update_content.assert_not_called()
    assert summary.updated == 0


def test_run_strips_marker_when_deadline_removed() -> None:
    today = date(2026, 4, 29)
    no_deadline_task = _task("9", "[T-3d] Old task", deadline_iso=None)
    client = MagicMock()
    client.list_active_tasks.return_value = [no_deadline_task]

    summary = run(client=client, today=today, tz=ZoneInfo("America/New_York"), dry_run=False)

    client.update_content.assert_called_once_with(task_id="9", content="Old task")
    assert summary.stripped == 1


def test_run_with_empty_active_set_does_not_fetch_history_or_write() -> None:
    today = date(2026, 4, 29)
    client = MagicMock()
    client.list_active_tasks.return_value = []

    summary = run(client=client, today=today, tz=ZoneInfo("America/New_York"), dry_run=False)

    client.list_completed_tasks.assert_not_called()
    client.update_content.assert_not_called()
    assert summary.scanned == 0


def test_run_dry_run_does_not_write() -> None:
    today = date(2026, 4, 29)
    client = MagicMock()
    client.list_active_tasks.return_value = [
        _task("1", "File 2026 taxes", "2026-05-14"),
    ]

    summary = run(client=client, today=today, tz=ZoneInfo("America/New_York"), dry_run=True)

    client.update_content.assert_not_called()
    assert summary.updated == 1  # counted as "would update"


def test_run_continues_on_single_task_error_and_reports_count() -> None:
    today = date(2026, 4, 29)
    client = MagicMock()
    client.list_active_tasks.return_value = [
        _task("1", "ok task", "2026-05-14"),
        _task("2", "bad task", "2026-05-14"),
    ]

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
    client.list_active_tasks.return_value = [_task("1", "", "2026-05-14")]

    summary = run(client=client, today=today, tz=ZoneInfo("America/New_York"), dry_run=False)

    client.update_content.assert_not_called()
    assert summary.updated == 0


def test_run_handles_datetime_in_deadline_field() -> None:
    """The SDK's ApiDue Union allows datetime; ensure we narrow to date."""
    today = date(2026, 4, 29)
    task = MagicMock(
        id="dt",
        content="Renew passport",
        deadline=MagicMock(date=_dt(2026, 5, 14, 12, 0, 0)),
        due=None,
    )
    client = MagicMock()
    client.list_active_tasks.return_value = [task]

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
    client.list_active_tasks.return_value = [parent, sub_todo_1, sub_todo_2]
    client.list_completed_subtasks_for_parent.return_value = [{"id": "done-1"}]

    summary = run(client=client, today=today, tz=ZoneInfo("America/New_York"), dry_run=False)

    client.update_content.assert_called_once_with(
        task_id="parent", content="[T-15d] Project launch [1/3]"
    )
    assert summary.updated == 1


def test_run_with_no_subtasks_keeps_user_authored_trailing_ratio() -> None:
    today = date(2026, 4, 29)
    client = MagicMock()
    parent = _task("parent", "[T-15d] Project launch [7/13]", "2026-05-14")
    client.list_active_tasks.return_value = [parent]

    summary = run(client=client, today=today, tz=ZoneInfo("America/New_York"), dry_run=False)

    client.update_content.assert_not_called()
    assert summary.updated == 0


def test_run_is_idempotent_when_marker_and_progress_are_already_correct() -> None:
    today = date(2026, 4, 29)
    client = MagicMock()
    parent = _task("parent", "[T-15d] Project launch [1/2]", "2026-05-14")
    sub_todo = _task("s2", "Todo child", None, parent_id="parent", is_completed=False)
    client.list_active_tasks.return_value = [parent, sub_todo]
    client.list_completed_subtasks_for_parent.return_value = [{"id": "done-1"}]

    summary = run(client=client, today=today, tz=ZoneInfo("America/New_York"), dry_run=False)

    client.update_content.assert_not_called()
    assert summary.updated == 0


def test_run_updates_existing_progress_suffix_when_only_completed_subtasks_remain() -> None:
    today = date(2026, 4, 29)
    client = MagicMock()
    parent = _task("parent", "[T-15d] Project launch [7/8]", "2026-05-14")
    client.list_active_tasks.return_value = [parent]
    client.list_completed_subtasks_for_parent.return_value = [
        {"id": "done-1"},
        {"id": "done-2"},
        {"id": "done-3"},
        {"id": "done-4"},
        {"id": "done-5"},
        {"id": "done-6"},
        {"id": "done-7"},
        {"id": "done-8"},
    ]

    summary = run(client=client, today=today, tz=ZoneInfo("America/New_York"), dry_run=False)

    client.update_content.assert_called_once_with(
        task_id="parent", content="[T-15d] Project launch [8/8]"
    )
    assert summary.updated == 1


def test_run_propagates_authoritative_active_task_fetch_failure() -> None:
    client = MagicMock()
    client.list_active_tasks.side_effect = RuntimeError("simulated")

    with pytest.raises(RuntimeError, match="simulated"):
        run(
            client=client,
            today=date(2026, 4, 29),
            tz=ZoneInfo("America/New_York"),
            dry_run=False,
        )


def test_run_adds_zero_day_age_since_latest_recurring_completion() -> None:
    task = _task(
        "daily",
        "Daily review",
        None,
        recurring=True,
        created_at=_dt(2026, 1, 1, tzinfo=timezone.utc),
    )
    client = MagicMock()
    client.list_active_tasks.return_value = [task]
    client.list_completed_tasks.return_value = [
        {"id": "daily", "completed_at": "2026-07-15T12:00:00Z"}
    ]

    summary = run(
        client=client,
        today=date(2026, 7, 15),
        tz=ZoneInfo("America/New_York"),
        dry_run=False,
    )

    client.update_content.assert_called_once_with(
        task_id="daily", content="[R+0d] Daily review"
    )
    assert summary.scanned == 1
    assert summary.updated == 1


def test_run_adds_age_since_latest_recurring_completion() -> None:
    today = date(2026, 7, 15)
    task = _task(
        "friend-x",
        "Call friend X",
        None,
        recurring=True,
        created_at=_dt(2026, 1, 1, tzinfo=timezone.utc),
    )
    client = MagicMock()
    client.list_active_tasks.return_value = [task]
    client.list_completed_tasks.return_value = [
        {"id": "friend-x", "completed_at": "2026-06-03T12:00:00Z"}
    ]

    summary = run(
        client=client,
        today=today,
        tz=ZoneInfo("America/New_York"),
        dry_run=False,
    )

    client.update_content.assert_called_once_with(
        task_id="friend-x", content="[R+42d] Call friend X"
    )
    assert summary.scanned == 1
    assert summary.updated == 1


def test_run_is_idempotent_when_recurrence_marker_is_correct() -> None:
    task = _task(
        "friend-x",
        "[R+42d] Call friend X",
        None,
        recurring=True,
        created_at=_dt(2026, 1, 1, tzinfo=timezone.utc),
    )
    client = MagicMock()
    client.list_active_tasks.return_value = [task]
    client.list_completed_tasks.return_value = [
        {"id": "friend-x", "completed_at": "2026-06-03T12:00:00Z"}
    ]

    summary = run(
        client=client,
        today=date(2026, 7, 15),
        tz=ZoneInfo("America/New_York"),
        dry_run=False,
    )

    client.update_content.assert_not_called()
    assert summary.scanned == 1
    assert summary.updated == 0


def test_run_leaves_first_time_recurring_task_unmarked() -> None:
    task = _task(
        "new-habit",
        "Try a new habit",
        None,
        recurring=True,
        created_at=_dt(2026, 7, 14, tzinfo=timezone.utc),
    )
    client = MagicMock()
    client.list_active_tasks.return_value = [task]
    client.list_completed_tasks.return_value = []

    summary = run(
        client=client,
        today=date(2026, 7, 15),
        tz=ZoneInfo("America/New_York"),
        dry_run=False,
    )

    client.update_content.assert_not_called()
    assert summary.scanned == 1
    assert summary.updated == 0
    assert summary.stripped == 0


def test_run_rounds_recurrence_marker_to_weeks_at_100_days() -> None:
    task = _task(
        "seasonal",
        "Seasonal check-in",
        None,
        recurring=True,
        created_at=_dt(2026, 1, 1, tzinfo=timezone.utc),
    )
    client = MagicMock()
    client.list_active_tasks.return_value = [task]
    client.list_completed_tasks.return_value = [
        {"id": "seasonal", "completed_at": "2026-04-06T12:00:00Z"}
    ]

    run(
        client=client,
        today=date(2026, 7, 15),
        tz=ZoneInfo("America/New_York"),
        dry_run=False,
    )

    client.update_content.assert_called_once_with(
        task_id="seasonal", content="[R+14w] Seasonal check-in"
    )


def test_run_deadline_takes_precedence_over_recurrence_without_history_call() -> None:
    task = _task(
        "renew",
        "Renew subscription",
        "2026-07-20",
        recurring=True,
        created_at=_dt(2026, 1, 1, tzinfo=timezone.utc),
    )
    client = MagicMock()
    client.list_active_tasks.return_value = [task]

    summary = run(
        client=client,
        today=date(2026, 7, 15),
        tz=ZoneInfo("America/New_York"),
        dry_run=False,
    )

    client.list_completed_tasks.assert_not_called()
    client.update_content.assert_called_once_with(
        task_id="renew", content="[T-5d] Renew subscription"
    )
    assert summary.scanned == 1


def test_run_strips_recurrence_marker_from_non_recurring_task() -> None:
    task = _task("one-off", "[R+42d] One-off task", None)
    client = MagicMock()
    client.list_active_tasks.return_value = [task]

    summary = run(
        client=client,
        today=date(2026, 7, 15),
        tz=ZoneInfo("America/New_York"),
        dry_run=False,
    )

    client.list_completed_tasks.assert_not_called()
    client.update_content.assert_called_once_with(
        task_id="one-off", content="One-off task"
    )
    assert summary.scanned == 0
    assert summary.stripped == 1


def test_run_replaces_stale_deadline_marker_with_recurrence_marker() -> None:
    task = _task(
        "friend-x",
        "[T+1d] Call friend X",
        None,
        recurring=True,
        created_at=_dt(2026, 1, 1, tzinfo=timezone.utc),
    )
    client = MagicMock()
    client.list_active_tasks.return_value = [task]
    client.list_completed_tasks.return_value = [
        {"id": "friend-x", "completed_at": "2026-06-03T12:00:00Z"}
    ]

    summary = run(
        client=client,
        today=date(2026, 7, 15),
        tz=ZoneInfo("America/New_York"),
        dry_run=False,
    )

    client.update_content.assert_called_once_with(
        task_id="friend-x", content="[R+42d] Call friend X"
    )
    assert summary.updated == 1
    assert summary.stripped == 0


def test_run_scanned_counts_deadline_and_recurring_candidates_only() -> None:
    deadline = _task("deadline", "[T-5d] Deadline", "2026-07-20")
    recurring = _task(
        "habit",
        "New habit",
        None,
        recurring=True,
        created_at=_dt(2026, 7, 14, tzinfo=timezone.utc),
    )
    cleanup_only = _task("cleanup", "[T+2d] Ordinary task", None)
    client = MagicMock()
    client.list_active_tasks.return_value = [deadline, recurring, cleanup_only]
    client.list_completed_tasks.return_value = []

    summary = run(
        client=client,
        today=date(2026, 7, 15),
        tz=ZoneInfo("America/New_York"),
        dry_run=False,
    )

    assert summary.scanned == 2
    assert summary.updated == 0
    assert summary.stripped == 1
    client.update_content.assert_called_once_with(
        task_id="cleanup", content="Ordinary task"
    )


def test_run_recurring_subtask_never_gains_progress_suffix() -> None:
    recurring_subtask = _task(
        "habit",
        "Habit subtask",
        None,
        recurring=True,
        parent_id="project",
        created_at=_dt(2026, 1, 1, tzinfo=timezone.utc),
    )
    open_child = _task("child", "Open child", None, parent_id="habit")
    client = MagicMock()
    client.list_active_tasks.return_value = [recurring_subtask, open_child]
    client.list_completed_tasks.return_value = [
        {"id": "habit", "completed_at": "2026-06-03T12:00:00Z"}
    ]

    run(
        client=client,
        today=date(2026, 7, 15),
        tz=ZoneInfo("America/New_York"),
        dry_run=False,
    )

    client.update_content.assert_called_once_with(
        task_id="habit", content="[R+42d] Habit subtask"
    )
    client.list_completed_subtasks_for_parent.assert_not_called()


def test_run_dry_run_counts_recurrence_change_without_writing() -> None:
    task = _task(
        "friend-x",
        "Call friend X",
        None,
        recurring=True,
        created_at=_dt(2026, 1, 1, tzinfo=timezone.utc),
    )
    client = MagicMock()
    client.list_active_tasks.return_value = [task]
    client.list_completed_tasks.return_value = [
        {"id": "friend-x", "completed_at": "2026-06-03T12:00:00Z"}
    ]

    summary = run(
        client=client,
        today=date(2026, 7, 15),
        tz=ZoneInfo("America/New_York"),
        dry_run=True,
    )

    client.update_content.assert_not_called()
    assert summary.updated == 1
    assert summary.stripped == 0


def _history_failure_tasks():
    return [
        _task("deadline", "Ship release", "2026-07-20"),
        _task(
            "preserve",
            "[R+7d] Preserve trusted recurrence",
            None,
            recurring=True,
            created_at=_dt(2026, 1, 1, tzinfo=timezone.utc),
        ),
        _task(
            "stale-t",
            "[T+1d] Former deadline",
            None,
            recurring=True,
            created_at=_dt(2026, 1, 1, tzinfo=timezone.utc),
        ),
        _task(
            "unmarked",
            "Never completed",
            None,
            recurring=True,
            created_at=_dt(2026, 1, 1, tzinfo=timezone.utc),
        ),
        _task(
            "partial",
            "[T-8d] Do not publish partial age",
            None,
            recurring=True,
            created_at=_dt(2026, 1, 1, tzinfo=timezone.utc),
        ),
        _task("ordinary", "[R+8d] One-off cleanup", None),
    ]


def test_run_preserves_recurrence_markers_when_history_request_fails() -> None:
    client = MagicMock()
    client.list_active_tasks.return_value = _history_failure_tasks()
    client.list_completed_tasks.side_effect = [[], RuntimeError("simulated")]

    summary = run(
        client=client,
        today=date(2026, 7, 15),
        tz=ZoneInfo("America/New_York"),
        dry_run=False,
    )

    assert client.list_completed_tasks.call_count == 2
    assert client.update_content.call_args_list == [
        call(task_id="deadline", content="[T-5d] Ship release"),
        call(task_id="stale-t", content="Former deadline"),
        call(task_id="partial", content="Do not publish partial age"),
        call(task_id="ordinary", content="One-off cleanup"),
    ]
    assert summary.scanned == 5
    assert summary.updated == 1
    assert summary.stripped == 3
    assert summary.errors == 0


def test_run_preserves_recurrence_markers_when_history_record_is_malformed() -> None:
    client = MagicMock()
    client.list_active_tasks.return_value = _history_failure_tasks()
    client.list_completed_tasks.return_value = [
        {"id": "partial", "completed_at": "2026-06-03T12:00:00Z"},
        {"id": "unmarked", "completed_at": "not-a-timestamp"},
    ]

    summary = run(
        client=client,
        today=date(2026, 7, 15),
        tz=ZoneInfo("America/New_York"),
        dry_run=False,
    )

    client.list_completed_tasks.assert_called_once()
    assert client.update_content.call_args_list == [
        call(task_id="deadline", content="[T-5d] Ship release"),
        call(task_id="stale-t", content="Former deadline"),
        call(task_id="partial", content="Do not publish partial age"),
        call(task_id="ordinary", content="One-off cleanup"),
    ]
    assert summary.scanned == 5
    assert summary.updated == 1
    assert summary.stripped == 3
    assert summary.errors == 0


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

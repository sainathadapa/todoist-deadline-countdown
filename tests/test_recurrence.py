from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from countdown.__main__ import (
    _elapsed_days_since,
    _latest_recurring_completions,
    _parse_timestamp,
)


class FakeClient:
    def __init__(self, pages):
        self.pages = iter(pages)
        self.calls = []

    def list_completed_tasks(self, *, since, until):
        self.calls.append((since, until))
        return next(self.pages)


def test_parse_timestamp_accepts_zulu_time():
    assert _parse_timestamp("2026-07-01T12:30:00Z") == datetime(
        2026, 7, 1, 12, 30, tzinfo=timezone.utc
    )


@pytest.mark.parametrize("value", [None, "", "not-a-date", 123])
def test_parse_timestamp_rejects_malformed_values(value):
    with pytest.raises(ValueError):
        _parse_timestamp(value)


def test_elapsed_days_uses_resolved_todoist_timezone():
    tz = ZoneInfo("America/New_York")
    completed = datetime(2026, 7, 1, 23, 30, tzinfo=timezone.utc)
    assert (
        _elapsed_days_since(completed, today=date(2026, 7, 1), tz=tz)
        == 0
    )


def test_elapsed_days_clamps_future_completion_to_zero():
    tz = ZoneInfo("UTC")
    completed = datetime(2026, 7, 16, tzinfo=timezone.utc)
    assert (
        _elapsed_days_since(completed, today=date(2026, 7, 15), tz=tz)
        == 0
    )


def test_latest_recurring_completions_chooses_newest_match():
    now = datetime(2026, 7, 15, tzinfo=timezone.utc)
    task = SimpleNamespace(
        id="friend-x",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    client = FakeClient(
        [[
            {"id": "friend-x", "completed_at": "2026-07-01T12:00:00Z"},
            {"id": "friend-x", "completed_at": "2026-07-10T12:00:00Z"},
        ]]
    )

    result = _latest_recurring_completions(client, [task], now_utc=now)

    assert result == {
        "friend-x": datetime(2026, 7, 10, 12, tzinfo=timezone.utc)
    }
    assert client.calls == [(now - timedelta(days=89), now)]


def test_latest_recurring_completions_moves_backward_in_consecutive_windows():
    now = datetime(2026, 7, 15, tzinfo=timezone.utc)
    task = SimpleNamespace(
        id="friend-x",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    client = FakeClient(
        [
            [],
            [{"id": "friend-x", "completed_at": "2026-03-01T12:00:00Z"}],
        ]
    )

    result = _latest_recurring_completions(client, [task], now_utc=now)

    first_since = now - timedelta(days=89)
    assert result == {
        "friend-x": datetime(2026, 3, 1, 12, tzinfo=timezone.utc)
    }
    assert client.calls == [
        (first_since, now),
        (first_since - timedelta(days=89), first_since),
    ]


def test_latest_recurring_completions_stops_at_task_creation():
    now = datetime(2026, 7, 15, tzinfo=timezone.utc)
    created_at = datetime(2026, 5, 1, 8, 30, tzinfo=timezone.utc)
    task = SimpleNamespace(id="friend-x", created_at=created_at)
    client = FakeClient([[]])

    result = _latest_recurring_completions(client, [task], now_utc=now)

    assert result == {}
    assert client.calls == [(created_at, now)]


def test_latest_recurring_completions_ignores_unrelated_task_ids():
    now = datetime(2026, 7, 15, tzinfo=timezone.utc)
    created_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
    task = SimpleNamespace(id="friend-x", created_at=created_at)
    client = FakeClient(
        [[{"id": "someone-else", "completed_at": "2026-07-10T12:00:00Z"}]]
    )

    result = _latest_recurring_completions(client, [task], now_utc=now)

    assert result == {}
    assert client.calls == [(created_at, now)]


@pytest.mark.parametrize(
    "malformed_record",
    [
        {"id": None, "completed_at": "2026-07-11T12:00:00Z"},
        {"id": "someone-else", "completed_at": "not-a-date"},
    ],
)
def test_latest_recurring_completions_rejects_malformed_record_in_valid_response(
    malformed_record,
):
    now = datetime(2026, 7, 15, tzinfo=timezone.utc)
    task = SimpleNamespace(
        id="friend-x",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    client = FakeClient(
        [[
            {"id": "friend-x", "completed_at": "2026-07-10T12:00:00Z"},
            malformed_record,
        ]]
    )

    with pytest.raises(ValueError):
        _latest_recurring_completions(client, [task], now_utc=now)


def test_latest_recurring_completions_interprets_naive_creation_as_utc():
    now = datetime(2026, 7, 15, tzinfo=timezone.utc)
    created_at = datetime(2026, 5, 1, 8, 30)
    task = SimpleNamespace(id="friend-x", created_at=created_at)
    client = FakeClient([[]])

    result = _latest_recurring_completions(client, [task], now_utc=now)

    assert result == {}
    assert client.calls == [(created_at.replace(tzinfo=timezone.utc), now)]

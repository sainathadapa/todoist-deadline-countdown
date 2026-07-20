import pytest
import responses

from countdown.todoist_client import TodoistClient


USER_URL = "https://api.todoist.com/api/v1/user"
COMPLETED_URL = "https://api.todoist.com/api/v1/tasks/completed/by_completion_date"
ACTIVITIES_URL = "https://api.todoist.com/api/v1/activities"


@responses.activate
def test_fetch_user_timezone_returns_iana_name() -> None:
    responses.add(
        method=responses.GET,
        url=USER_URL,
        json={
            "id": "1",
            "tz_info": {
                "timezone": "America/New_York",
                "gmt_string": "-04:00",
                "hours": -4,
                "minutes": 0,
                "is_dst": 1,
            },
        },
        status=200,
    )

    client = TodoistClient(token="test-token")
    assert client.fetch_user_timezone() == "America/New_York"


@responses.activate
def test_fetch_user_timezone_returns_none_when_missing() -> None:
    responses.add(
        method=responses.GET,
        url=USER_URL,
        json={"id": "1"},
        status=200,
    )

    client = TodoistClient(token="test-token")
    assert client.fetch_user_timezone() is None


@responses.activate
def test_fetch_user_timezone_sends_bearer_token() -> None:
    responses.add(
        method=responses.GET,
        url=USER_URL,
        json={"tz_info": {"timezone": "UTC"}},
        status=200,
    )

    client = TodoistClient(token="abc123")
    client.fetch_user_timezone()

    assert responses.calls[0].request.headers["Authorization"] == "Bearer abc123"


@responses.activate
def test_list_completed_tasks_paginates_without_parent_filter() -> None:
    from datetime import datetime, timezone

    responses.add(
        method=responses.GET,
        url=COMPLETED_URL,
        json={
            "items": [{"id": "a"}],
            "next_cursor": "next-page",
        },
        status=200,
        match=[responses.matchers.query_param_matcher(
            {
                "since": "2026-05-01T00:00:00Z",
                "until": "2026-05-15T00:00:00Z",
                "limit": "200",
            }
        )],
    )
    responses.add(
        method=responses.GET,
        url=COMPLETED_URL,
        json={
            "items": [{"id": "b"}],
            "next_cursor": None,
        },
        status=200,
        match=[responses.matchers.query_param_matcher(
            {
                "since": "2026-05-01T00:00:00Z",
                "until": "2026-05-15T00:00:00Z",
                "limit": "200",
                "cursor": "next-page",
            }
        )],
    )

    client = TodoistClient(token="test-token")
    items = client.list_completed_tasks(
        since=datetime(2026, 5, 1, tzinfo=timezone.utc),
        until=datetime(2026, 5, 15, tzinfo=timezone.utc),
    )

    assert items == [{"id": "a"}, {"id": "b"}]
    assert len(responses.calls) == 2
    assert responses.calls[0].request.headers["Authorization"] == "Bearer test-token"
    assert "parent_id=" not in responses.calls[0].request.url
    assert "cursor=next-page" in responses.calls[1].request.url


@responses.activate
def test_list_completed_subtasks_for_parent_filters_and_paginates() -> None:
    from datetime import datetime, timezone

    responses.add(
        method=responses.GET,
        url=COMPLETED_URL,
        json={
            "items": [{"id": "c1"}, {"id": "c2"}],
            "next_cursor": "next-page",
        },
        status=200,
        match=[responses.matchers.query_param_matcher(
            {
                "since": "2026-05-01T00:00:00Z",
                "until": "2026-05-15T00:00:00Z",
                "parent_id": "parent-1",
                "limit": "200",
            }
        )],
    )
    responses.add(
        method=responses.GET,
        url=COMPLETED_URL,
        json={
            "items": [{"id": "c3"}],
            "next_cursor": None,
        },
        status=200,
        match=[responses.matchers.query_param_matcher(
            {
                "since": "2026-05-01T00:00:00Z",
                "until": "2026-05-15T00:00:00Z",
                "parent_id": "parent-1",
                "limit": "200",
                "cursor": "next-page",
            }
        )],
    )

    client = TodoistClient(token="test-token")
    items = client.list_completed_subtasks_for_parent(
        parent_id="parent-1",
        since=datetime(2026, 5, 1, tzinfo=timezone.utc),
        until=datetime(2026, 5, 15, tzinfo=timezone.utc),
    )

    assert [item["id"] for item in items] == ["c1", "c2", "c3"]
    assert len(responses.calls) == 2
    assert responses.calls[0].request.headers["Authorization"] == "Bearer test-token"


@responses.activate
def test_list_completed_item_activities_filters_and_paginates() -> None:
    from datetime import datetime, timezone

    responses.add(
        method=responses.GET,
        url=ACTIVITIES_URL,
        json={
            "results": [{"object_id": "habit", "event_date": "2026-05-10T12:00:00Z"}],
            "next_cursor": "next-page",
        },
        status=200,
        match=[responses.matchers.query_param_matcher(
            {
                "date_from": "2026-05-01T00:00:00Z",
                "date_to": "2026-05-15T00:00:00Z",
                "object_event_types": '["item:completed"]',
                "limit": "200",
            }
        )],
    )
    responses.add(
        method=responses.GET,
        url=ACTIVITIES_URL,
        json={
            "results": [{"object_id": "friend", "event_date": "2026-05-12T12:00:00Z"}],
            "next_cursor": None,
        },
        status=200,
        match=[responses.matchers.query_param_matcher(
            {
                "date_from": "2026-05-01T00:00:00Z",
                "date_to": "2026-05-15T00:00:00Z",
                "object_event_types": '["item:completed"]',
                "limit": "200",
                "cursor": "next-page",
            }
        )],
    )

    client = TodoistClient(token="test-token")
    events = client.list_completed_item_activities(
        since=datetime(2026, 5, 1, tzinfo=timezone.utc),
        until=datetime(2026, 5, 15, tzinfo=timezone.utc),
    )

    assert events == [
        {"object_id": "habit", "event_date": "2026-05-10T12:00:00Z"},
        {"object_id": "friend", "event_date": "2026-05-12T12:00:00Z"},
    ]
    assert len(responses.calls) == 2
    assert responses.calls[0].request.headers["Authorization"] == "Bearer test-token"
    assert "cursor=next-page" in responses.calls[1].request.url


@responses.activate
def test_list_completed_item_activities_rejects_non_object_response() -> None:
    from datetime import datetime, timezone

    responses.add(
        method=responses.GET,
        url=ACTIVITIES_URL,
        json=[{"object_id": "habit"}],
        status=200,
    )

    client = TodoistClient(token="test-token")
    with pytest.raises(
        ValueError, match="Todoist activity response must be an object"
    ):
        client.list_completed_item_activities(
            since=datetime(2026, 5, 1, tzinfo=timezone.utc),
            until=datetime(2026, 5, 15, tzinfo=timezone.utc),
        )


@responses.activate
def test_list_completed_item_activities_rejects_non_list_results() -> None:
    from datetime import datetime, timezone

    responses.add(
        method=responses.GET,
        url=ACTIVITIES_URL,
        json={"results": "not-a-list", "next_cursor": None},
        status=200,
    )

    client = TodoistClient(token="test-token")
    with pytest.raises(
        ValueError, match="Todoist activity response results must be a list"
    ):
        client.list_completed_item_activities(
            since=datetime(2026, 5, 1, tzinfo=timezone.utc),
            until=datetime(2026, 5, 15, tzinfo=timezone.utc),
        )


@responses.activate
def test_list_completed_item_activities_rejects_repeated_cursor() -> None:
    from datetime import datetime, timezone

    responses.add(
        method=responses.GET,
        url=ACTIVITIES_URL,
        json={"results": [{"object_id": "habit"}], "next_cursor": "repeated"},
        status=200,
    )
    responses.add(
        method=responses.GET,
        url=ACTIVITIES_URL,
        json={"results": [{"object_id": "friend"}], "next_cursor": "repeated"},
        status=200,
    )

    client = TodoistClient(token="test-token")
    with pytest.raises(ValueError, match="Todoist activity cursor repeated"):
        client.list_completed_item_activities(
            since=datetime(2026, 5, 1, tzinfo=timezone.utc),
            until=datetime(2026, 5, 15, tzinfo=timezone.utc),
        )


@responses.activate
def test_list_completed_tasks_rejects_non_object_response() -> None:
    from datetime import datetime, timezone

    responses.add(
        method=responses.GET,
        url=COMPLETED_URL,
        json=[{"id": "a"}],
        status=200,
    )

    client = TodoistClient(token="test-token")
    with pytest.raises(
        ValueError, match="Todoist completion response must be an object"
    ):
        client.list_completed_tasks(
            since=datetime(2026, 5, 1, tzinfo=timezone.utc),
            until=datetime(2026, 5, 15, tzinfo=timezone.utc),
        )


@responses.activate
def test_list_completed_tasks_rejects_non_list_items() -> None:
    from datetime import datetime, timezone

    responses.add(
        method=responses.GET,
        url=COMPLETED_URL,
        json={"items": "not-a-list", "next_cursor": None},
        status=200,
    )

    client = TodoistClient(token="test-token")
    with pytest.raises(
        ValueError, match="Todoist completion response items must be a list"
    ):
        client.list_completed_tasks(
            since=datetime(2026, 5, 1, tzinfo=timezone.utc),
            until=datetime(2026, 5, 15, tzinfo=timezone.utc),
        )


@responses.activate
def test_list_completed_tasks_rejects_non_string_cursor() -> None:
    from datetime import datetime, timezone

    responses.add(
        method=responses.GET,
        url=COMPLETED_URL,
        json={"items": [], "next_cursor": 42},
        status=200,
    )
    responses.add(
        method=responses.GET,
        url=COMPLETED_URL,
        json={"items": [], "next_cursor": None},
        status=200,
    )

    client = TodoistClient(token="test-token")
    with pytest.raises(
        ValueError, match="Todoist completion cursor must be a string or null"
    ):
        client.list_completed_tasks(
            since=datetime(2026, 5, 1, tzinfo=timezone.utc),
            until=datetime(2026, 5, 15, tzinfo=timezone.utc),
        )


@responses.activate
def test_list_completed_tasks_rejects_repeated_cursor() -> None:
    from datetime import datetime, timezone

    responses.add(
        method=responses.GET,
        url=COMPLETED_URL,
        json={"items": [{"id": "a"}], "next_cursor": "repeated"},
        status=200,
    )
    responses.add(
        method=responses.GET,
        url=COMPLETED_URL,
        json={"items": [{"id": "b"}], "next_cursor": "repeated"},
        status=200,
    )
    responses.add(
        method=responses.GET,
        url=COMPLETED_URL,
        json={"items": [{"id": "c"}], "next_cursor": None},
        status=200,
    )

    client = TodoistClient(token="test-token")
    with pytest.raises(ValueError, match="Todoist completion cursor repeated"):
        client.list_completed_tasks(
            since=datetime(2026, 5, 1, tzinfo=timezone.utc),
            until=datetime(2026, 5, 15, tzinfo=timezone.utc),
        )


from unittest.mock import MagicMock, call, patch


@patch("countdown.todoist_client.TodoistAPI")
def test_list_deadlined_tasks_uses_filter_query(mock_api_cls: MagicMock) -> None:
    api = mock_api_cls.return_value
    api.filter_tasks.return_value = iter([[MagicMock(id="1"), MagicMock(id="2")]])

    client = TodoistClient(token="t")
    tasks = client.list_deadlined_tasks()

    api.filter_tasks.assert_called_once_with(query="!no deadline")
    assert [t.id for t in tasks] == ["1", "2"]


@patch("countdown.todoist_client.TodoistAPI")
def test_list_active_tasks_uses_get_tasks(mock_api_cls: MagicMock) -> None:
    api = mock_api_cls.return_value
    api.get_tasks.return_value = iter([[MagicMock(id="1"), MagicMock(id="2")]])

    client = TodoistClient(token="t")
    tasks = client.list_active_tasks()

    api.get_tasks.assert_called_once_with()
    assert [t.id for t in tasks] == ["1", "2"]


@patch("countdown.todoist_client.TodoistAPI")
def test_list_marked_tasks_dedupes_across_three_searches(mock_api_cls: MagicMock) -> None:
    api = mock_api_cls.return_value
    task_a = MagicMock(id="A", content="[T-2w] Task mentioning R+ in body")
    task_b = MagicMock(id="B", content="[T+1d] Task with marker")
    task_c = MagicMock(id="C", content="[R+3d] Recurring task with marker")
    false_positive = MagicMock(id="D", content="False positive containing R+ in body")

    def filter_side_effect(query: str):
        if query == "search: T-":
            return iter([[task_a]])
        if query == "search: T+":
            return iter([[task_b]])
        if query == "search: R+":
            return iter([[task_a, task_c, false_positive]])
        raise AssertionError(f"unexpected query: {query}")

    api.filter_tasks.side_effect = filter_side_effect

    client = TodoistClient(token="t")
    tasks = client.list_marked_tasks()

    assert api.filter_tasks.call_args_list == [
        call(query="search: T-"),
        call(query="search: T+"),
        call(query="search: R+"),
    ]
    # task_a is deduplicated and the false positive does not match MARKER_RE.
    ids = sorted(t.id for t in tasks)
    assert ids == ["A", "B", "C"]


@patch("countdown.todoist_client.TodoistAPI")
def test_update_content_calls_sdk_update_task(mock_api_cls: MagicMock) -> None:
    api = mock_api_cls.return_value
    api.update_task.return_value = MagicMock()

    client = TodoistClient(token="t")
    client.update_content(task_id="42", content="[T-1d] Hello")

    api.update_task.assert_called_once_with(task_id="42", content="[T-1d] Hello")


@patch("countdown.todoist_client.TodoistAPI")
def test_list_marked_tasks_dedupes_when_task_appears_in_both_searches(
    mock_api_cls: MagicMock,
) -> None:
    api = mock_api_cls.return_value
    # The same task object is returned by BOTH searches — this can happen if a
    # title contains both a `T-` substring elsewhere AND a leading `[T+1d]` marker.
    same_task = MagicMock(id="DUPE", content="[T+1d] meeting")

    def filter_side_effect(query: str):
        if query == "search: T-":
            return iter([[same_task]])
        if query == "search: T+":
            return iter([[same_task]])
        if query == "search: R+":
            return iter([[]])
        raise AssertionError(f"unexpected query: {query}")

    api.filter_tasks.side_effect = filter_side_effect

    client = TodoistClient(token="t")
    tasks = client.list_marked_tasks()

    # Despite appearing in both searches, the task is returned exactly once.
    assert len(tasks) == 1
    assert tasks[0].id == "DUPE"


import requests
from countdown.todoist_client import retry_with_backoff


def test_retry_with_backoff_returns_on_first_success() -> None:
    calls = []

    def fn():
        calls.append(1)
        return "ok"

    assert retry_with_backoff(fn, sleep=lambda _: None) == "ok"
    assert len(calls) == 1


def test_retry_with_backoff_retries_on_5xx() -> None:
    attempts = []

    def fn():
        attempts.append(1)
        if len(attempts) < 3:
            r = requests.Response()
            r.status_code = 503
            raise requests.HTTPError(response=r)
        return "ok"

    assert retry_with_backoff(fn, sleep=lambda _: None) == "ok"
    assert len(attempts) == 3


def test_retry_with_backoff_retries_on_429_then_succeeds() -> None:
    attempts = []

    def fn():
        attempts.append(1)
        if len(attempts) < 2:
            r = requests.Response()
            r.status_code = 429
            r.headers["Retry-After"] = "1"
            raise requests.HTTPError(response=r)
        return "ok"

    assert retry_with_backoff(fn, sleep=lambda _: None) == "ok"
    assert len(attempts) == 2


def test_retry_with_backoff_does_not_retry_on_401() -> None:
    attempts = []

    def fn():
        attempts.append(1)
        r = requests.Response()
        r.status_code = 401
        raise requests.HTTPError(response=r)

    with pytest.raises(requests.HTTPError):
        retry_with_backoff(fn, sleep=lambda _: None)
    assert len(attempts) == 1


def test_retry_with_backoff_gives_up_after_max_attempts() -> None:
    attempts = []

    def fn():
        attempts.append(1)
        r = requests.Response()
        r.status_code = 503
        raise requests.HTTPError(response=r)

    with pytest.raises(requests.HTTPError):
        retry_with_backoff(fn, sleep=lambda _: None, max_attempts=3)
    assert len(attempts) == 3


def test_retry_with_backoff_retries_on_transport_error() -> None:
    attempts = []

    def fn():
        attempts.append(1)
        if len(attempts) < 3:
            raise requests.ConnectionError("simulated DNS failure")
        return "ok"

    assert retry_with_backoff(fn, sleep=lambda _: None) == "ok"
    assert len(attempts) == 3


def test_retry_with_backoff_gives_up_on_persistent_transport_error() -> None:
    attempts = []

    def fn():
        attempts.append(1)
        raise requests.Timeout("simulated timeout")

    with pytest.raises(requests.Timeout):
        retry_with_backoff(fn, sleep=lambda _: None, max_attempts=3)
    assert len(attempts) == 3

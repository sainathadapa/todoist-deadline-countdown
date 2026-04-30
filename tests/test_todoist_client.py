import pytest
import responses

from countdown.todoist_client import TodoistClient


SYNC_URL = "https://api.todoist.com/sync/v9/sync"


@responses.activate
def test_fetch_user_timezone_returns_iana_name() -> None:
    responses.add(
        method=responses.POST,
        url=SYNC_URL,
        json={
            "user": {
                "id": "1",
                "tz_info": {
                    "timezone": "America/New_York",
                    "gmt_string": "-04:00",
                    "hours": -4,
                    "minutes": 0,
                    "is_dst": 1,
                },
            }
        },
        status=200,
    )

    client = TodoistClient(token="test-token")
    assert client.fetch_user_timezone() == "America/New_York"


@responses.activate
def test_fetch_user_timezone_returns_none_when_missing() -> None:
    responses.add(
        method=responses.POST,
        url=SYNC_URL,
        json={"user": {"id": "1"}},
        status=200,
    )

    client = TodoistClient(token="test-token")
    assert client.fetch_user_timezone() is None


@responses.activate
def test_fetch_user_timezone_sends_bearer_token() -> None:
    responses.add(
        method=responses.POST,
        url=SYNC_URL,
        json={"user": {"tz_info": {"timezone": "UTC"}}},
        status=200,
    )

    client = TodoistClient(token="abc123")
    client.fetch_user_timezone()

    assert responses.calls[0].request.headers["Authorization"] == "Bearer abc123"


from unittest.mock import MagicMock, patch


@patch("countdown.todoist_client.TodoistAPI")
def test_list_deadlined_tasks_uses_filter_query(mock_api_cls: MagicMock) -> None:
    api = mock_api_cls.return_value
    api.filter_tasks.return_value = iter([[MagicMock(id="1"), MagicMock(id="2")]])

    client = TodoistClient(token="t")
    tasks = client.list_deadlined_tasks()

    api.filter_tasks.assert_called_once_with(query="deadline before: 5 years from now")
    assert [t.id for t in tasks] == ["1", "2"]


@patch("countdown.todoist_client.TodoistAPI")
def test_list_suffixed_tasks_dedupes_across_two_searches(mock_api_cls: MagicMock) -> None:
    api = mock_api_cls.return_value
    task_a = MagicMock(id="A", content="Task with [T-2w]")
    task_b = MagicMock(id="B", content="Task with [T+1d]")
    task_c = MagicMock(id="C", content="False positive containing T- in body")

    def filter_side_effect(query: str):
        if query == "search: T-":
            return iter([[task_a, task_c]])
        if query == "search: T+":
            return iter([[task_b]])
        raise AssertionError(f"unexpected query: {query}")

    api.filter_tasks.side_effect = filter_side_effect

    client = TodoistClient(token="t")
    tasks = client.list_suffixed_tasks()

    # task_c is filtered out because its content does not match SUFFIX_RE
    ids = sorted(t.id for t in tasks)
    assert ids == ["A", "B"]


@patch("countdown.todoist_client.TodoistAPI")
def test_update_content_calls_sdk_update_task(mock_api_cls: MagicMock) -> None:
    api = mock_api_cls.return_value
    api.update_task.return_value = MagicMock()

    client = TodoistClient(token="t")
    client.update_content(task_id="42", content="Hello [T-1d]")

    api.update_task.assert_called_once_with(task_id="42", content="Hello [T-1d]")

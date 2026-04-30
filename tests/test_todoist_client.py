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

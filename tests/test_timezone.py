from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from countdown.timezone import resolve_timezone


def test_env_override_takes_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COUNTDOWN_TZ", "Europe/Berlin")
    client = MagicMock()
    client.fetch_user_timezone.return_value = "America/New_York"

    tz = resolve_timezone(client)

    assert tz == ZoneInfo("Europe/Berlin")
    client.fetch_user_timezone.assert_not_called()


def test_uses_client_timezone_when_no_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COUNTDOWN_TZ", raising=False)
    client = MagicMock()
    client.fetch_user_timezone.return_value = "America/Los_Angeles"

    assert resolve_timezone(client) == ZoneInfo("America/Los_Angeles")


def test_falls_back_to_new_york_when_client_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("COUNTDOWN_TZ", raising=False)
    client = MagicMock()
    client.fetch_user_timezone.return_value = None

    assert resolve_timezone(client) == ZoneInfo("America/New_York")


def test_falls_back_to_new_york_when_client_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("COUNTDOWN_TZ", raising=False)
    client = MagicMock()
    client.fetch_user_timezone.side_effect = RuntimeError("boom")

    assert resolve_timezone(client) == ZoneInfo("America/New_York")


def test_invalid_env_override_falls_through_to_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COUNTDOWN_TZ", "Not/A/Real_Zone")
    client = MagicMock()
    client.fetch_user_timezone.return_value = "America/Chicago"

    assert resolve_timezone(client) == ZoneInfo("America/Chicago")

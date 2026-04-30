"""Thin wrapper over the Todoist SDK plus one direct REST call for user.tz_info."""

from __future__ import annotations

import time
from itertools import chain
from typing import Callable, TypeVar

import requests
from todoist_api_python.api import TodoistAPI

from countdown.format import SUFFIX_RE

USER_URL = "https://api.todoist.com/api/v1/user"

T = TypeVar("T")

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def retry_with_backoff(
    fn: Callable[[], T],
    *,
    max_attempts: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Run `fn`, retrying on 5xx, 429, and transport-level errors.

    Re-raises immediately on non-retryable HTTP statuses (4xx except 429).
    Backoff: 1s, 4s, 16s. For 429, prefer the `Retry-After` header.
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except requests.RequestException as exc:
            if isinstance(exc, requests.HTTPError):
                status = exc.response.status_code if exc.response is not None else None
                if status not in RETRYABLE_STATUS:
                    raise
            # Otherwise: transport error — always retry up to max_attempts.
            last_exc = exc
            if attempt == max_attempts:
                break
            wait = _retry_after_seconds(exc) if isinstance(exc, requests.HTTPError) else None
            if wait is None:
                wait = 4 ** (attempt - 1)
            sleep(wait)
    assert last_exc is not None
    raise last_exc


def _retry_after_seconds(exc: requests.HTTPError) -> float | None:
    if exc.response is None:
        return None
    raw = exc.response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _flatten(pages):
    """The SDK returns an iterator of pages (each page is a list). Flatten."""
    return list(chain.from_iterable(pages))


class TodoistClient:
    def __init__(self, token: str) -> None:
        self._token = token
        self._api = TodoistAPI(token)

    def fetch_user_timezone(self) -> str | None:
        """Fetch the authenticated user's IANA timezone via GET /api/v1/user.

        Returns None if the response lacks tz_info.
        """
        def _do():
            response = requests.get(
                USER_URL,
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=30,
            )
            response.raise_for_status()
            return response

        response = retry_with_backoff(_do)
        body = response.json()
        tz_info = body.get("tz_info") or {}
        return tz_info.get("timezone")

    def list_deadlined_tasks(self):
        return retry_with_backoff(
            lambda: _flatten(self._api.filter_tasks(query="deadline before: 5 years from now"))
        )

    def list_suffixed_tasks(self):
        seen: dict[str, object] = {}
        for query in ("search: T-", "search: T+"):
            tasks = retry_with_backoff(lambda q=query: _flatten(self._api.filter_tasks(query=q)))
            for task in tasks:
                if SUFFIX_RE.search(task.content):
                    seen[task.id] = task
        return list(seen.values())

    def update_content(self, task_id: str, content: str) -> None:
        retry_with_backoff(lambda: self._api.update_task(task_id=task_id, content=content))

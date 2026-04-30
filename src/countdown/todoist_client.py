"""Thin wrapper over the Todoist SDK plus one direct Sync API call for user.tz_info."""

from __future__ import annotations

from itertools import chain

import requests
from todoist_api_python.api import TodoistAPI

from countdown.format import SUFFIX_RE

SYNC_URL = "https://api.todoist.com/sync/v9/sync"


def _flatten(pages):
    """The SDK returns an iterator of pages (each page is a list). Flatten."""
    return list(chain.from_iterable(pages))


class TodoistClient:
    def __init__(self, token: str) -> None:
        self._token = token
        self._api = TodoistAPI(token)

    def fetch_user_timezone(self) -> str | None:
        """Fetch the authenticated user's IANA timezone via the Sync API.

        Returns None if the response lacks tz_info.
        """
        response = requests.post(
            SYNC_URL,
            headers={"Authorization": f"Bearer {self._token}"},
            data={"sync_token": "*", "resource_types": '["user"]'},
            timeout=30,
        )
        response.raise_for_status()
        user = response.json().get("user", {})
        tz_info = user.get("tz_info") or {}
        return tz_info.get("timezone")

    def list_deadlined_tasks(self):
        pages = self._api.filter_tasks(query="deadline before: 5 years from now")
        return _flatten(pages)

    def list_suffixed_tasks(self):
        seen: dict[str, object] = {}
        for query in ("search: T-", "search: T+"):
            for task in _flatten(self._api.filter_tasks(query=query)):
                if SUFFIX_RE.search(task.content):
                    seen[task.id] = task
        return list(seen.values())

    def update_content(self, task_id: str, content: str) -> None:
        self._api.update_task(task_id=task_id, content=content)

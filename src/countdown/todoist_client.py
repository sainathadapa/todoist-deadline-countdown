"""Thin wrapper over the Todoist SDK plus one direct Sync API call for user.tz_info."""

from __future__ import annotations

import requests
from todoist_api_python.api import TodoistAPI

SYNC_URL = "https://api.todoist.com/sync/v9/sync"


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

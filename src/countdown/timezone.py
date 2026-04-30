"""Timezone resolution: env override -> Todoist user.tz_info -> America/New_York."""

from __future__ import annotations

import logging
import os
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

FALLBACK = "America/New_York"
log = logging.getLogger(__name__)


def resolve_timezone(client) -> ZoneInfo:
    """Resolve the user's timezone, in this order:
       1. COUNTDOWN_TZ env var (if it parses as a valid IANA zone)
       2. client.fetch_user_timezone() (if it returns a valid IANA zone)
       3. America/New_York (logged as a warning)
    """
    override = os.environ.get("COUNTDOWN_TZ")
    if override:
        try:
            return ZoneInfo(override)
        except ZoneInfoNotFoundError:
            log.warning("COUNTDOWN_TZ=%r is not a valid IANA zone; ignoring.", override)

    try:
        name = client.fetch_user_timezone()
    except Exception as exc:  # noqa: BLE001 - we want to swallow and fall back
        log.warning("Failed to fetch Todoist user timezone (%s); falling back.", exc)
        name = None

    if name:
        try:
            return ZoneInfo(name)
        except ZoneInfoNotFoundError:
            log.warning("Todoist returned non-IANA timezone %r; falling back.", name)

    log.warning("Falling back to %s.", FALLBACK)
    return ZoneInfo(FALLBACK)

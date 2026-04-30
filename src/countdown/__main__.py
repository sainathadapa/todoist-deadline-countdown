"""Orchestrator: fetch tasks, compute new content, write updates."""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from countdown.format import apply_suffix, format_suffix, strip_suffix
from countdown.timezone import resolve_timezone
from countdown.todoist_client import TodoistClient

log = logging.getLogger("countdown")


@dataclass
class Summary:
    scanned: int = 0
    updated: int = 0
    stripped: int = 0
    errors: int = 0


def _parse_deadline(task) -> date | None:
    if task.deadline is None:
        return None
    raw = getattr(task.deadline, "date", None)
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def run(*, client, today: date, tz: ZoneInfo, dry_run: bool) -> Summary:
    summary = Summary()
    deadlined = client.list_deadlined_tasks()
    summary.scanned = len(deadlined)
    deadlined_ids = {t.id for t in deadlined}

    for task in deadlined:
        if not task.content:
            log.info("[skip ] %s empty content", task.id)
            continue
        deadline = _parse_deadline(task)
        if deadline is None:
            log.info("[skip ] %s malformed deadline", task.id)
            continue

        delta = (deadline - today).days
        suffix = format_suffix(delta)
        new_content = apply_suffix(task.content, suffix)

        if new_content == task.content:
            log.info(
                '[skip ] %s "%s" delta=%d suffix=%s (no change)',
                task.id, task.content, delta, suffix,
            )
            continue

        log.info(
            '[write] %s "%s" delta=%d suffix=%s (was: "%s")',
            task.id, new_content, delta, suffix, task.content,
        )
        if dry_run:
            summary.updated += 1
            continue
        try:
            client.update_content(task_id=task.id, content=new_content)
            summary.updated += 1
        except Exception as exc:  # noqa: BLE001
            log.error("[error] %s %s", task.id, exc)
            summary.errors += 1

    # Strip pass: tasks bearing our suffix that are no longer in the deadlined set.
    for task in client.list_suffixed_tasks():
        if task.id in deadlined_ids:
            continue
        new_content = strip_suffix(task.content)
        if new_content == task.content:
            continue
        log.info('[strip] %s "%s" deadline removed; stripping', task.id, task.content)
        if dry_run:
            summary.stripped += 1
            continue
        try:
            client.update_content(task_id=task.id, content=new_content)
            summary.stripped += 1
        except Exception as exc:  # noqa: BLE001
            log.error("[error] %s %s", task.id, exc)
            summary.errors += 1

    log.info(
        "summary: scanned=%d updated=%d stripped=%d errors=%d",
        summary.scanned, summary.updated, summary.stripped, summary.errors,
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    token = os.environ.get("TODOIST_API_TOKEN")
    if not token:
        log.error("TODOIST_API_TOKEN is not set")
        return 1

    client = TodoistClient(token=token)
    tz = resolve_timezone(client)
    today = datetime.now(tz).date()
    dry_run = os.environ.get("DRY_RUN") == "1"

    summary = run(client=client, today=today, tz=tz, dry_run=dry_run)
    return 0 if summary.errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

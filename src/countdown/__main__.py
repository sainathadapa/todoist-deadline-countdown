"""Orchestrator: fetch tasks, compute new content, write updates."""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from countdown.format import apply_marker, format_marker, strip_marker
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
        marker = format_marker(delta)
        new_content = apply_marker(task.content, marker)

        if new_content == task.content:
            log.info(
                '[skip ] %s "%s" delta=%d marker=%s (no change)',
                task.id, task.content, delta, marker,
            )
            continue

        log.info(
            '[write] %s "%s" delta=%d marker=%s (was: "%s")',
            task.id, new_content, delta, marker, task.content,
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

    # Strip pass: tasks bearing our marker that are no longer in the deadlined set.
    for task in client.list_marked_tasks():
        if task.id in deadlined_ids:
            continue
        new_content = strip_marker(task.content)
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


def _write_step_summary(summary: Summary, dry_run: bool) -> None:
    """Append a markdown summary card to $GITHUB_STEP_SUMMARY if running in CI."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    suffix = " (dry-run — nothing written)" if dry_run else ""
    md = (
        f"## Countdown run{suffix}\n\n"
        f"| Scanned | Updated | Stripped | Errors |\n"
        f"|---|---|---|---|\n"
        f"| {summary.scanned} | {summary.updated} | {summary.stripped} | {summary.errors} |\n"
    )
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(md)
    except OSError as exc:
        log.warning("Could not write step summary: %s", exc)


def main(argv: list[str] | None = None) -> int:
    argv = list(argv) if argv is not None else sys.argv[1:]
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    token = os.environ.get("TODOIST_API_TOKEN")
    if not token:
        log.error("TODOIST_API_TOKEN is not set")
        return 1

    client = TodoistClient(token=token)

    if argv and argv[0] == "doctor":
        tz = client.fetch_user_timezone() or "(none)"
        print(f"Token OK. User timezone (per Todoist): {tz}")
        return 0

    if argv and argv[0] == "--strip-all":
        errors = 0
        for task in client.list_marked_tasks():
            new_content = strip_marker(task.content)
            if new_content == task.content:
                continue
            try:
                client.update_content(task_id=task.id, content=new_content)
                log.info('[strip] %s "%s" -> "%s"', task.id, task.content, new_content)
            except Exception as exc:  # noqa: BLE001
                log.error("[error] %s %s", task.id, exc)
                errors += 1
        return 0 if errors == 0 else 1

    tz = resolve_timezone(client)
    today = datetime.now(tz).date()
    dry_run = os.environ.get("DRY_RUN") == "1"

    summary = run(client=client, today=today, tz=tz, dry_run=dry_run)
    _write_step_summary(summary, dry_run=dry_run)
    return 0 if summary.errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

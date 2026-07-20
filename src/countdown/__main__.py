"""Orchestrator: fetch tasks, compute new content, write updates."""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from countdown.format import (
    PROGRESS_SUFFIX_RE,
    RECURRENCE_PREFIX_RE,
    apply_marker,
    apply_progress_suffix,
    format_marker,
    format_recurrence_marker,
    strip_marker,
)
from countdown.timezone import resolve_timezone
from countdown.todoist_client import TodoistClient

log = logging.getLogger("countdown")
COMPLETED_LOOKBACK_WINDOW_DAYS = 89


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


def _build_open_subtask_counts(tasks) -> dict[str, int]:
    """Map parent task id -> number of open subtasks."""
    progress: dict[str, int] = {}
    for task in tasks:
        parent_id = getattr(task, "parent_id", None)
        if parent_id is None:
            continue
        key = str(parent_id)
        progress[key] = progress.get(key, 0) + 1
    return progress


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("completion timestamp must be a non-empty string")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"invalid completion timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError("completion timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _record_field(record: object, field: str) -> object:
    if isinstance(record, dict):
        return record.get(field)
    return getattr(record, field, None)


def _latest_recurring_completions(
    client, tasks, *, now_utc: datetime
) -> dict[str, datetime]:
    now_utc = _to_utc(now_utc)
    created_by_id: dict[str, datetime] = {}
    for task in tasks:
        created_at = getattr(task, "created_at", None)
        if not isinstance(created_at, datetime):
            raise ValueError(f"task {task.id} has invalid created_at")
        created_by_id[str(task.id)] = _to_utc(created_at)

    latest: dict[str, datetime] = {}
    unresolved = set(created_by_id)
    until = now_utc
    window = timedelta(days=COMPLETED_LOOKBACK_WINDOW_DAYS)

    while unresolved:
        earliest_creation = min(created_by_id[task_id] for task_id in unresolved)
        since = max(until - window, earliest_creation)
        if since >= until:
            break

        records = client.list_completed_item_activities(since=since, until=until)
        matches: dict[str, datetime] = {}
        for record in records:
            raw_event_type = _record_field(record, "event_type")
            if raw_event_type is not None and raw_event_type != "completed":
                raise ValueError("activity event has invalid event_type")
            raw_object_type = _record_field(record, "object_type")
            if raw_object_type is not None and raw_object_type != "item":
                raise ValueError("activity event has invalid object_type")
            raw_id = _record_field(record, "object_id")
            if not isinstance(raw_id, str) or not raw_id:
                raise ValueError("activity event has invalid object_id")
            completed_at = _parse_timestamp(_record_field(record, "event_date"))
            if raw_id in unresolved:
                matches[raw_id] = max(matches.get(raw_id, completed_at), completed_at)

        latest.update(matches)
        unresolved.difference_update(matches)
        unresolved = {
            task_id
            for task_id in unresolved
            if created_by_id[task_id] < since
        }
        until = since

    return latest


def _elapsed_days_since(
    completed_at: datetime, *, today: date, tz: ZoneInfo
) -> int:
    completed_day = _to_utc(completed_at).astimezone(tz).date()
    return max(0, (today - completed_day).days)


def _completed_subtask_counts_for_parents(client, parent_tasks) -> dict[str, int]:
    """Map parent task id -> completed subtask count from completion history."""
    counts: dict[str, int] = {}
    now_utc = datetime.now(timezone.utc)
    window = timedelta(days=COMPLETED_LOOKBACK_WINDOW_DAYS)

    for parent in parent_tasks:
        parent_id = str(parent.id)
        created_at = getattr(parent, "created_at", None)
        if isinstance(created_at, datetime):
            cursor = _to_utc(created_at)
        else:
            cursor = now_utc - window

        total = 0
        while cursor < now_utc:
            until = min(cursor + window, now_utc)
            items = client.list_completed_subtasks_for_parent(
                parent_id=parent_id, since=cursor, until=until
            )
            total += len(items)
            cursor = until
        if total > 0:
            counts[parent_id] = total

    return counts


def _is_recurring(task) -> bool:
    due = getattr(task, "due", None)
    return bool(due is not None and getattr(due, "is_recurring", False))


def _write_content_change(
    *,
    client,
    task,
    new_content: str,
    dry_run: bool,
    summary: Summary,
    stripped: bool,
) -> None:
    if new_content == task.content:
        return
    action = "strip" if stripped else "write"
    log.info('[%s] %s "%s" (was: "%s")', action, task.id, new_content, task.content)
    if dry_run:
        if stripped:
            summary.stripped += 1
        else:
            summary.updated += 1
        return
    try:
        client.update_content(task_id=task.id, content=new_content)
        if stripped:
            summary.stripped += 1
        else:
            summary.updated += 1
    except Exception as exc:  # noqa: BLE001
        log.error("[error] %s %s", task.id, exc)
        summary.errors += 1


def run(*, client, today: date, tz: ZoneInfo, dry_run: bool) -> Summary:
    summary = Summary()
    active_tasks = client.list_active_tasks()
    deadlined = [
        task for task in active_tasks if getattr(task, "deadline", None) is not None
    ]
    recurring = [
        task
        for task in active_tasks
        if getattr(task, "deadline", None) is None and _is_recurring(task)
    ]
    summary.scanned = len(deadlined) + len(recurring)

    progress_by_parent: dict[str, tuple[int, int]] = {}
    if deadlined:
        open_counts = _build_open_subtask_counts(active_tasks)
        parents = [
            task
            for task in deadlined
            if open_counts.get(str(task.id), 0) > 0
                or PROGRESS_SUFFIX_RE.search(task.content)
        ]
        completed_counts: dict[str, int] = {}
        if parents:
            try:
                completed_counts = _completed_subtask_counts_for_parents(
                    client, parents
                )
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "Could not fetch completed subtasks for progress suffixes; "
                    "falling back to open-subtask counts only: %s",
                    exc,
                )
        for parent in parents:
            parent_id = str(parent.id)
            open_subtasks = open_counts.get(parent_id, 0)
            completed_subtasks = completed_counts.get(parent_id, 0)
            if open_subtasks > 0 or completed_subtasks > 0:
                progress_by_parent[parent_id] = (
                    completed_subtasks,
                    completed_subtasks + open_subtasks,
                )

    now_utc = datetime.now(timezone.utc)
    recurrence_history: dict[str, datetime] | None = {}
    if recurring:
        try:
            recurrence_history = _latest_recurring_completions(
                client,
                recurring,
                now_utc=now_utc,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "Could not fetch reliable recurring completion history; "
                "preserving existing recurrence markers: %s",
                exc,
            )
            recurrence_history = None

    for task in active_tasks:
        if not task.content:
            log.info("[skip ] %s empty content", task.id)
            continue

        deadline_field = getattr(task, "deadline", None)
        if deadline_field is not None:
            deadline = _parse_deadline(task)
            if deadline is None:
                log.info("[skip ] %s malformed deadline", task.id)
                continue
            delta = (deadline - today).days
            new_content = apply_marker(task.content, format_marker(delta))
            progress = progress_by_parent.get(str(task.id))
            if progress is not None:
                completed, total = progress
                new_content = apply_progress_suffix(
                    new_content,
                    completed=completed,
                    total=total,
                )
            _write_content_change(
                client=client,
                task=task,
                new_content=new_content,
                dry_run=dry_run,
                summary=summary,
                stripped=False,
            )
            continue

        if _is_recurring(task):
            if recurrence_history is None:
                trusted_recurrence = RECURRENCE_PREFIX_RE.match(task.content)
                if trusted_recurrence:
                    trusted_marker = trusted_recurrence.group().strip()[1:-1]
                    new_content = apply_marker(task.content, trusted_marker)
                else:
                    new_content = strip_marker(task.content)
            else:
                completed_at = recurrence_history.get(str(task.id))
                if completed_at is None:
                    new_content = strip_marker(task.content)
                else:
                    elapsed = _elapsed_days_since(completed_at, today=today, tz=tz)
                    new_content = apply_marker(
                        task.content,
                        format_recurrence_marker(elapsed),
                    )
                    _write_content_change(
                        client=client,
                        task=task,
                        new_content=new_content,
                        dry_run=dry_run,
                        summary=summary,
                        stripped=False,
                    )
                    continue
        else:
            new_content = strip_marker(task.content)

        _write_content_change(
            client=client,
            task=task,
            new_content=new_content,
            dry_run=dry_run,
            summary=summary,
            stripped=True,
        )

    log.info(
        "summary: scanned=%d updated=%d stripped=%d errors=%d",
        summary.scanned,
        summary.updated,
        summary.stripped,
        summary.errors,
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

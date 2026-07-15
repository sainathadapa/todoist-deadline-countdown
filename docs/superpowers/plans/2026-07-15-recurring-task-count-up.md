# Recurring Task Count-Up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prefix eligible recurring Todoist tasks with an idempotent age marker such as `[R+42d]`, calculated from their latest completion, while preserving the existing deadline countdown behavior.

**Architecture:** Fetch the active task set once per run and classify each task. Tasks with deadlines keep the existing `[T±…]` path and take precedence. Recurring tasks without deadlines use completion history, fetched in backward 89-day windows, to find the latest completion. If completion history is unreliable, preserve existing recurring markers rather than publishing partial ages.

**Tech Stack:** Python 3.11+, Todoist REST API and `todoist-api-python`, `requests`, `zoneinfo`, `pytest`, `uv`, GitHub Actions.

**Design reference:** `docs/superpowers/specs/2026-07-15-recurring-task-count-up-design.md`

## Global constraints

- Use test-driven development: write each failing test, confirm the expected failure, implement the smallest change, and rerun the focused test.
- A task may have only one leading managed temporal marker. Deadline `[T±…]` always wins over recurrence `[R+…]`.
- Recurrence markers use exact days through 99 days and rounded weeks from 100 days onward.
- A recurring task gets no recurrence marker until its first completion appears in history.
- Resolve elapsed calendar days in the same Todoist timezone used by the deadline countdown.
- Do not make any completion-history request when there are no recurring, non-deadline candidates.
- Any malformed completion record or history request/pagination failure invalidates recurrence history for the whole run. Preserve an existing `[R+…]` on eligible recurring tasks in that case.
- The existing subtask progress suffix remains deadline-only.
- Keep `--strip-all`, dry-run, per-task update-error handling, and step-summary behavior intact.

---

## Task 1: Add recurrence marker formatting and managed-marker replacement

**Files:**

- Modify: `src/countdown/format.py`
- Modify: `tests/test_format.py`
- Modify: `tests/test_idempotency.py`

- [x] **Step 1: Add failing recurrence-format boundary tests**

In `tests/test_format.py`, import `format_recurrence_marker` and add:

```python
@pytest.mark.parametrize(
    ("elapsed_days", "expected"),
    [
        (0, "R+0d"),
        (1, "R+1d"),
        (42, "R+42d"),
        (99, "R+99d"),
        (100, "R+14w"),
        (365, "R+52w"),
    ],
)
def test_format_recurrence_marker(elapsed_days, expected):
    assert format_recurrence_marker(elapsed_days) == expected
```

- [x] **Step 2: Add failing strip/apply tests for recurrence and stacked stale markers**

In `tests/test_idempotency.py`, extend the imports with `apply_marker` and
`strip_marker`, then add cases that establish one managed-marker family and
preserve the progress suffix:

```python
def test_strip_marker_removes_recurrence_marker():
    assert strip_marker("[R+42d] Call Alex") == "Call Alex"


def test_strip_marker_removes_all_stacked_managed_markers():
    assert strip_marker("[T-3d] [R+42d] Call Alex") == "Call Alex"


def test_apply_deadline_marker_replaces_recurrence_marker():
    assert apply_marker("[R+42d] Call Alex", "T-6d") == "[T-6d] Call Alex"


def test_apply_recurrence_marker_replaces_deadline_marker_and_preserves_progress():
    assert (
        apply_marker("[T+2d] Call Alex [1/2]", "R+42d")
        == "[R+42d] Call Alex [1/2]"
    )
```

Also add an idempotency case in `tests/test_idempotency.py`:

```python
def test_recurrence_marker_application_is_idempotent():
    once = apply_marker("Call Alex", "R+42d")
    twice = apply_marker(once, "R+42d")
    assert twice == once
```

- [x] **Step 3: Run the focused tests and confirm they fail**

Run:

```bash
uv run pytest tests/test_format.py tests/test_idempotency.py -q
```

Expected: failures because `format_recurrence_marker` does not exist and current marker regexes only recognize `T` markers.

- [x] **Step 4: Implement recurrence formatting and unified managed-marker regexes**

In `src/countdown/format.py`, add:

```python
def format_recurrence_marker(elapsed_days: int) -> str:
    """Return the bracket-less count-up marker for elapsed calendar days."""
    magnitude = max(0, elapsed_days)
    if magnitude <= 99:
        return f"R+{magnitude}d"
    return f"R+{round(magnitude / 7)}w"
```

Replace the marker regex definitions with:

```python
DEADLINE_PREFIX_RE = re.compile(r"^\s*\[T[+-]\d+[dwm]\]\s*")
RECURRENCE_PREFIX_RE = re.compile(r"^\s*\[R\+\d+[dw]\]\s*")
PREFIX_RE = re.compile(
    r"^(?:\s*\[(?:T[+-]\d+[dwm]|R\+\d+[dw])\]\s*)+"
)
MARKER_RE = re.compile(r"\[(?:T[+-]\d+[dwm]|R\+\d+[dw])\]")
```

Keep `strip_marker()` and `apply_marker()` as the single replacement path so either marker replaces all stale leading managed markers.

- [x] **Step 5: Run focused tests and confirm green**

```bash
uv run pytest tests/test_format.py tests/test_idempotency.py -q
```

- [x] **Step 6: Commit Task 1**

```bash
git add src/countdown/format.py tests/test_format.py tests/test_idempotency.py
git commit -m "feat: add recurring task age markers"
```

---

## Task 2: Add validated, paginated completion-history access

**Files:**

- Modify: `src/countdown/todoist_client.py`
- Modify: `tests/test_todoist_client.py`

- [x] **Step 1: Add failing tests for account-level completion-history pagination**

In `tests/test_todoist_client.py`, add `responses`-based HTTP tests that verify:

1. `list_completed_tasks(since=since, until=until)` calls the completed-by-completion-date endpoint with bearer authorization, ISO-8601 UTC bounds, and `limit=200`.
2. A returned `next_cursor` is sent on the next request and all `items` are combined in order.
3. The account-level method omits `parent_id`.
4. The existing `list_completed_subtasks_for_parent()` still includes `parent_id` and shares pagination behavior.

Representative assertions after calling the method:

```python
items = client.list_completed_tasks(since=since, until=until)

assert items == [{"id": "a"}, {"id": "b"}]
assert len(responses.calls) == 2
assert responses.calls[0].request.headers["Authorization"] == "Bearer test-token"
assert "parent_id=" not in responses.calls[0].request.url
assert "cursor=next-page" in responses.calls[1].request.url
```

- [x] **Step 2: Add failing response-validation tests**

Add tests asserting that `ValueError` is raised for:

- a JSON body that is not a dictionary;
- `items` that is not a list;
- a non-string, non-null `next_cursor`;
- a repeated non-null cursor, which must fail instead of looping forever.

Do not validate individual completion record fields here; the history resolver owns semantic validation so one malformed record invalidates the recurrence run.

- [x] **Step 3: Add a failing marker-search test for `R+`**

Extend `test_list_marked_tasks_dedupes_across_two_searches` (and rename it to end in `three_searches`) to expect queries for `search: T-`, `search: T+`, and `search: R+`, deduplicate by task ID, and reject search false positives whose content lacks a managed marker. Update `test_list_marked_tasks_dedupes_when_task_appears_in_both_searches` as well so its side effect returns an empty page for `search: R+` rather than treating the new query as unexpected.

- [x] **Step 4: Run focused tests and confirm they fail**

```bash
uv run pytest tests/test_todoist_client.py -q
```

- [x] **Step 5: Extract one private completion-page loop and add the public account method**

Implement the following shape in `TodoistClient`:

```python
def _list_completed_tasks(
    self,
    *,
    since: datetime,
    until: datetime,
    parent_id: str | None = None,
) -> list[dict]:
    items: list[dict] = []
    cursor: str | None = None
    seen_cursors: set[str] = set()

    while True:
        params: dict[str, object] = {
            "since": since.isoformat().replace("+00:00", "Z"),
            "until": until.isoformat().replace("+00:00", "Z"),
            "limit": 200,
        }
        if parent_id is not None:
            params["parent_id"] = parent_id
        if cursor is not None:
            params["cursor"] = cursor

        def _do():
            response = requests.get(
                COMPLETED_BY_COMPLETION_DATE_URL,
                headers={"Authorization": f"Bearer {self._token}"},
                params=params,
                timeout=30,
            )
            response.raise_for_status()
            return response

        body = retry_with_backoff(_do).json()
        if not isinstance(body, dict):
            raise ValueError("Todoist completion response must be an object")
        page_items = body.get("items", [])
        if not isinstance(page_items, list):
            raise ValueError("Todoist completion response items must be a list")
        items.extend(page_items)

        next_cursor = body.get("next_cursor")
        if next_cursor is not None and not isinstance(next_cursor, str):
            raise ValueError("Todoist completion cursor must be a string or null")
        if not next_cursor:
            return items
        if next_cursor in seen_cursors:
            raise ValueError("Todoist completion cursor repeated")
        seen_cursors.add(next_cursor)
        cursor = next_cursor

def list_completed_tasks(
    self, *, since: datetime, until: datetime
) -> list[dict]:
    return self._list_completed_tasks(since=since, until=until)

def list_completed_subtasks_for_parent(
    self, *, parent_id: str, since: datetime, until: datetime
) -> list[dict]:
    return self._list_completed_tasks(
        since=since, until=until, parent_id=parent_id
    )
```

Extend `list_marked_tasks()` to include `search: R+`.

- [x] **Step 6: Run focused tests and confirm green**

```bash
uv run pytest tests/test_todoist_client.py -q
```

- [x] **Step 7: Commit Task 2**

```bash
git add src/countdown/todoist_client.py tests/test_todoist_client.py
git commit -m "feat: fetch recurring completion history"
```

---

## Task 3: Resolve the latest completion and elapsed Todoist-local day count

**Files:**

- Create: `tests/test_recurrence.py`
- Modify: `src/countdown/__main__.py`

- [x] **Step 1: Add failing timestamp and elapsed-day tests**

Create `tests/test_recurrence.py` and test private helpers directly:

```python
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from countdown.__main__ import _elapsed_days_since, _parse_timestamp


class FakeClient:
    def __init__(self, pages):
        self.pages = iter(pages)
        self.calls = []

    def list_completed_tasks(self, *, since, until):
        self.calls.append((since, until))
        return next(self.pages)


def test_parse_timestamp_accepts_zulu_time():
    assert _parse_timestamp("2026-07-01T12:30:00Z") == datetime(
        2026, 7, 1, 12, 30, tzinfo=timezone.utc
    )


@pytest.mark.parametrize("value", [None, "", "not-a-date", 123])
def test_parse_timestamp_rejects_malformed_values(value):
    with pytest.raises(ValueError):
        _parse_timestamp(value)


def test_elapsed_days_uses_resolved_todoist_timezone():
    tz = ZoneInfo("America/New_York")
    completed = datetime(2026, 7, 1, 23, 30, tzinfo=timezone.utc)
    assert _elapsed_days_since(completed, today=date(2026, 7, 1), tz=tz) == 0


def test_elapsed_days_clamps_future_completion_to_zero():
    tz = ZoneInfo("UTC")
    completed = datetime(2026, 7, 16, tzinfo=timezone.utc)
    assert _elapsed_days_since(completed, today=date(2026, 7, 15), tz=tz) == 0
```

- [x] **Step 2: Add failing backward-window history tests**

Build lightweight task objects with `id` and timezone-aware `created_at`, plus a fake client that records `(since, until)` calls.

Cover these cases:

- The newest matching completion in the newest 89-day window wins.
- If no candidate is found, the resolver moves backward in consecutive 89-day windows.
- Scanning stops at the earliest unresolved candidate's creation timestamp.
- Records for unrelated task IDs are ignored.
- A malformed record ID or `completed_at` raises `ValueError`, even if another valid match exists in the same response.
- A naive task `created_at` is interpreted as UTC through `_to_utc()`.

Representative core test:

```python
def test_latest_recurring_completions_chooses_newest_match():
    now = datetime(2026, 7, 15, tzinfo=timezone.utc)
    task = SimpleNamespace(
        id="friend-x",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    client = FakeClient(
        [[
            {"id": "friend-x", "completed_at": "2026-07-01T12:00:00Z"},
            {"id": "friend-x", "completed_at": "2026-07-10T12:00:00Z"},
        ]]
    )

    result = _latest_recurring_completions(client, [task], now_utc=now)

    assert result == {
        "friend-x": datetime(2026, 7, 10, 12, tzinfo=timezone.utc)
    }
    assert client.calls == [(now - timedelta(days=89), now)]
```

- [x] **Step 3: Run the new test module and confirm it fails**

```bash
uv run pytest tests/test_recurrence.py -q
```

- [x] **Step 4: Implement strict record parsing and reverse-window resolution**

Add to `src/countdown/__main__.py`:

```python
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

        records = client.list_completed_tasks(since=since, until=until)
        matches: dict[str, datetime] = {}
        for record in records:
            raw_id = _record_field(record, "id")
            if not isinstance(raw_id, str) or not raw_id:
                raise ValueError("completion record has invalid id")
            completed_at = _parse_timestamp(_record_field(record, "completed_at"))
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
```

Important: parse every record in every fetched page before accepting the window. This enforces the approved all-or-nothing history reliability rule.

- [x] **Step 5: Run recurrence tests and confirm green**

```bash
uv run pytest tests/test_recurrence.py -q
```

- [x] **Step 6: Run existing subtask-history tests for regression coverage**

```bash
uv run pytest tests/test_orchestrator.py tests/test_todoist_client.py -q
```

- [x] **Step 7: Commit Task 3**

```bash
git add src/countdown/__main__.py tests/test_recurrence.py
git commit -m "feat: resolve latest recurring completions"
```

---

## Task 4: Integrate recurrence ages into the orchestrator

**Files:**

- Modify: `src/countdown/__main__.py`
- Modify: `tests/test_orchestrator.py`

- [x] **Step 1: Make the orchestrator test task factory model `due.is_recurring` explicitly**

Update `_task()` in `tests/test_orchestrator.py` so `MagicMock` cannot accidentally make every task truthy-recurring:

```python
def _task(
    task_id: str,
    content: str,
    deadline_iso: str | None,
    *,
    recurring: bool = False,
    parent_id: str | None = None,
    is_completed: bool = False,
    created_at=None,
):
    deadline = None if deadline_iso is None else MagicMock(date=deadline_iso)
    due = MagicMock(is_recurring=recurring) if recurring else None
    return MagicMock(
        id=task_id,
        content=content,
        deadline=deadline,
        due=due,
        parent_id=parent_id,
        is_completed=is_completed,
        created_at=created_at,
    )
```

Also update the datetime-deadline test's hand-built task to set `due=None`.

- [x] **Step 2: Migrate existing tests to one authoritative active-task fetch**

For every existing `run()` test:

- populate `client.list_active_tasks.return_value` with the full active set;
- stop configuring or asserting `client.list_deadlined_tasks`;
- stop configuring `client.list_marked_tasks`, because the normal run can classify and clean all active tasks directly;
- retain `list_marked_tasks` only in the `--strip-all` CLI test.

Replace `test_run_with_no_deadlined_tasks_does_not_fetch_active_tasks` with a test that proves an empty active set causes no history call or write. Replace `test_run_continues_when_active_task_fetch_fails` with:

```python
def test_run_propagates_authoritative_active_task_fetch_failure():
    client = MagicMock()
    client.list_active_tasks.side_effect = RuntimeError("simulated")

    with pytest.raises(RuntimeError, match="simulated"):
        run(
            client=client,
            today=date(2026, 4, 29),
            tz=ZoneInfo("America/New_York"),
            dry_run=False,
        )
```

- [x] **Step 3: Add failing recurrence lifecycle tests**

Update the test module's datetime imports to include `timezone`, then add focused orchestrator cases using timezone-aware `created_at` values and completion records:

1. Recurring, no deadline, latest completion today becomes `[R+0d]`.
2. Recurring, no deadline, latest completion 42 local calendar days ago becomes `[R+42d]`.
3. An already-correct recurrence marker is idempotent.
4. A first-time recurring task with no matching completion has no marker.
5. A recurrence marker crosses to rounded weeks at 100 days.
6. A recurring task with a deadline receives only the deadline marker and triggers no history call if it is the only recurring task.
7. A non-recurring task with stale `[R+…]` is stripped.
8. A recurring task that no longer has a deadline replaces stale `[T±…]` with `[R+…]` when history succeeds.
9. `Summary.scanned` counts deadline tasks plus recurring non-deadline candidates, not ordinary cleanup-only tasks.
10. A recurring task may be a subtask, but recurrence annotations never gain or recalculate a progress suffix.
11. Dry-run counts a recurrence change without calling `update_content()`.

Representative test:

```python
def test_run_adds_age_since_latest_recurring_completion():
    today = date(2026, 7, 15)
    task = _task(
        "friend-x",
        "Call friend X",
        None,
        recurring=True,
        created_at=_dt(2026, 1, 1, tzinfo=timezone.utc),
    )
    client = MagicMock()
    client.list_active_tasks.return_value = [task]
    client.list_completed_tasks.return_value = [
        {"id": "friend-x", "completed_at": "2026-06-03T12:00:00Z"}
    ]

    summary = run(
        client=client,
        today=today,
        tz=ZoneInfo("America/New_York"),
        dry_run=False,
    )

    client.update_content.assert_called_once_with(
        task_id="friend-x", content="[R+42d] Call friend X"
    )
    assert summary.scanned == 1
    assert summary.updated == 1
```

- [x] **Step 4: Add failing all-or-nothing history-failure tests**

Cover request failure and malformed-record failure. In both cases:

- deadline tasks still update normally;
- an eligible task already starting with `[R+…]` is preserved exactly;
- an eligible task starting only with stale `[T±…]` has that marker stripped because it no longer has a deadline;
- an unmarked eligible task stays unmarked rather than receiving a guessed age;
- ordinary non-recurring stale markers are stripped;
- no partial recurrence age from an earlier successful window is published.

Use `client.list_completed_tasks.side_effect` to return one empty window and then raise, proving the result is discarded for the run.

- [x] **Step 5: Run orchestrator tests and confirm the new expectations fail**

```bash
uv run pytest tests/test_orchestrator.py -q
```

- [x] **Step 6: Add recurrence classification and imports**

Import `RECURRENCE_PREFIX_RE` and `format_recurrence_marker` from `countdown.format`, then add:

```python
def _is_recurring(task) -> bool:
    due = getattr(task, "due", None)
    return bool(due is not None and getattr(due, "is_recurring", False))
```

- [x] **Step 7: Refactor `run()` around the active task set**

Implement a shared content-change helper and refactor `run()` to the exact flow below. This preserves the existing dry-run counters, progress calculation, and isolated per-task update errors while making active tasks authoritative.

```python
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
                if RECURRENCE_PREFIX_RE.match(task.content):
                    continue
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
```

Capture `now_utc = datetime.now(timezone.utc)` once near the start of `run()` for the history lookup. Use the injected `today` value for elapsed local-calendar-day conversion so tests and production share the already-resolved Todoist-local date. Do not call `list_marked_tasks()` during a normal run.

When recurrence history is unavailable, only a leading `RECURRENCE_PREFIX_RE` is trusted and preserved. `strip_marker()` removes a stale deadline marker on an eligible recurring task that does not already carry a trusted recurrence marker.

- [x] **Step 8: Run orchestrator tests and confirm green**

```bash
uv run pytest tests/test_orchestrator.py -q
```

- [x] **Step 9: Run all implementation-focused tests**

```bash
uv run pytest \
  tests/test_format.py \
  tests/test_idempotency.py \
  tests/test_todoist_client.py \
  tests/test_recurrence.py \
  tests/test_orchestrator.py -q
```

- [x] **Step 10: Commit Task 4**

```bash
git add src/countdown/__main__.py tests/test_orchestrator.py
git commit -m "feat: annotate recurring tasks since completion"
```

---

## Task 5: Document the count-up workflow and complete CLI cleanup coverage

**Files:**

- Modify: `README.md`
- Modify: `tests/test_orchestrator.py`

- [x] **Step 1: Add a failing `--strip-all` recurrence-marker case**

Extend `test_main_strip_all_strips_marker_from_every_marked_task` with:

```python
MagicMock(id="C", content="[R+42d] call friend X")
```

Assert it is updated to `call friend X` and update the expected call count to three.

- [x] **Step 2: Run the focused CLI test as regression coverage**

```bash
uv run pytest tests/test_orchestrator.py::test_main_strip_all_strips_marker_from_every_marked_task -q
```

Expected: pass, because Task 1 made `strip_marker()` understand recurrence markers. This test locks that behavior into the CLI contract.

- [x] **Step 3: Update README examples and badge semantics**

Change the title and introduction to cover both deadline countdowns and recurring-task count-ups. Add a before/after example:

```text
Call friend X (recurring every! 6 weeks) -> [R+42d] Call friend X
```

Document:

- `[R+Nd]` for 0–99 days since the latest completion;
- `[R+Nw]` for 100+ days, rounded to weeks;
- recurrence markers appear only after the first completion;
- a Todoist deadline wins when a task has both deadline and recurrence metadata;
- subtask progress suffixes remain deadline-only.

Update the free-plan FAQ as well: recurring count-up works with recurring due dates, while deadline countdown badges still require a Todoist plan that exposes the `deadline` field.

- [x] **Step 4: Replace the outdated recurring-task FAQ**

Explain the intended workflow concretely:

1. Create `Call friend X` with `every! 6 weeks` so Todoist schedules from the actual completion date.
2. Complete it after making the call.
3. The next workflow run reads Todoist completion history and annotates the new recurring instance with the elapsed time since that completion.
4. The due date remains a cadence/reminder, not a deadline.

Mention that completion-history API failures preserve existing recurrence badges until a later successful run.

- [x] **Step 5: Update idempotency and uninstall documentation**

Describe the managed leading-marker grammar as both deadline and recurrence markers:

```regex
^\s*\[(?:T[+-]\d+[dwm]|R\+\d+[dw])\]\s*
```

State that `--strip-all` removes both marker families.

- [x] **Step 6: Run CLI and full tests**

```bash
uv run pytest tests/test_orchestrator.py -q
uv run pytest -q
```

- [x] **Step 7: Commit Task 5**

```bash
git add README.md tests/test_orchestrator.py
git commit -m "docs: explain recurring task count-up"
```

---

## Task 6: Final verification and implementation bookkeeping

**Files:**

- Modify: `docs/superpowers/plans/2026-07-15-recurring-task-count-up.md`

- [x] **Step 1: Run the complete test suite from a clean process**

```bash
uv run pytest
```

Expected: all tests pass with no warnings introduced by this feature.

- [x] **Step 2: Run static repository checks**

```bash
git diff --check
git status --short
git log --oneline -8
```

Expected: no whitespace errors; only intentional plan bookkeeping may remain uncommitted.

- [x] **Step 3: Review behavior against the approved design**

Manually verify each invariant:

- deadline precedence produces one `[T±…]` marker;
- recurring non-deadline tasks produce one `[R+…]` only after a completion;
- no recurring candidates means zero completion-history calls;
- history failure never publishes partial or guessed recurrence ages;
- stale managed markers are removed when their classification no longer applies;
- all date arithmetic uses the resolved Todoist timezone;
- dry-run and `--strip-all` are covered.

- [x] **Step 4: Mark completed plan checkboxes and commit the bookkeeping update**

```bash
git add docs/superpowers/plans/2026-07-15-recurring-task-count-up.md
git commit -m "docs: complete recurring count-up plan"
```

- [x] **Step 5: Confirm the final working tree is clean**

```bash
git status --short
```

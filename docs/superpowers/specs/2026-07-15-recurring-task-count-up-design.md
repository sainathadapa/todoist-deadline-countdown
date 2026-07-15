# Recurring Task Count-Up Design

## Goal

Show how long it has been since each recurring Todoist task was last completed. A task such as `Call X` becomes `[R+42d] Call X` 42 days after its most recent completion.

## User Workflow

The user creates and completes recurring Todoist tasks normally. For a cadence based on the actual completion date, Todoist's `every!` syntax remains the recommended setup; for example, `Call X every! 6 weeks` schedules the next occurrence six weeks after the task is completed.

The existing GitHub Actions job continues to run every three hours. After a recurring task is completed, the next successful run updates its title to `[R+0d]` and increments the marker over time.

## Eligibility and Precedence

Every active task is classified from its Todoist fields:

1. A task with a deadline uses the existing `[T-Nd]`, `[T+Nd]`, `[T-Nw]`, or `[T+Nw]` marker. A deadline always suppresses the recurrence marker, even when the task also has a recurring date.
2. A task without a deadline whose `due.is_recurring` value is true is eligible for a recurrence marker.
3. A task with neither a deadline nor a recurring date has any stale managed temporal marker removed.

A recurring task has no recurrence marker until Todoist reports its first completion. The feature is account-wide and does not require a project, label, environment variable, or other opt-in mechanism.

## Marker Format

The recurrence marker is a leading `[R+…]` prefix:

| Elapsed time since latest completion | Marker |
|---|---|
| Today | `[R+0d]` |
| 1–99 days | `[R+Nd]` |
| 100+ days | `[R+Nw]` |

Weeks use the same rounded `days / 7` behavior as deadline markers. Only one managed temporal marker appears at the beginning of a title. Examples:

```text
Call X
[R+0d] Call X
[R+42d] Call X
[R+14w] Call X
[T-10d] Call X
[R+42d] Call family [2/3]
```

Both deadline and recurrence markers are recognized only at the beginning of the title. Other user-authored bracketed text remains untouched. Existing subtask progress suffix behavior remains unchanged and deadline-only.

## Architecture

### Formatting

`src/countdown/format.py` owns recognition, formatting, replacement, and removal of `[T±…]` and `[R+…]` markers. Formatting exposes separate deadline and recurrence marker functions while sharing safe leading-prefix stripping. Applying either marker removes any other managed temporal prefix first, which guarantees deadline precedence and idempotency.

### Todoist client

`src/countdown/todoist_client.py` owns paginated access to `GET /api/v1/tasks/completed/by_completion_date`. Todoist limits each request to a completion-date range of at most three months, so the client accepts explicit `since` and `until` datetimes and returns all pages for that window.

The implementation uses 89-day windows and matches completion records to active recurring tasks by Todoist task ID. It does not infer completion dates from recurrence strings or future due dates.

### Orchestrator

`src/countdown/__main__.py` fetches all active tasks once and derives deadline and recurring candidates locally. The active task collection also continues to support current subtask progress calculation.

For recurring tasks without deadlines, the orchestrator searches completion history backward from the current UTC time. It keeps an unresolved set of task IDs, records the first matching completion encountered for each task as the latest completion, and stops searching for a task when either:

- a completion is found; or
- the search window reaches that task's creation time, proving no earlier completion is possible.

The search stops when every candidate is resolved. Completion records from unrelated tasks are ignored after retrieval.

When there are no eligible recurring tasks, the run makes no completion-history requests.

For each resolved completion, `completed_at` is converted from UTC into the resolved Todoist timezone before its calendar date is compared with `today`. The elapsed value is clamped to zero if clock skew produces a future local completion date.

## Title Lifecycle

- First completion: the next successful run adds `[R+0d]`.
- Later runs: the marker advances according to elapsed calendar days.
- Recurrence removed: the stale `[R+…]` marker is stripped.
- Deadline added: `[R+…]` is replaced by the appropriate `[T±…]` marker.
- Deadline removed while recurrence remains: `[R+…]` is restored from completion history.
- Successful history scan with no matching completion: no recurrence marker is applied, and any stale recurrence marker is stripped.
- Non-recurring task with a stale deadline or recurrence marker: the managed prefix is stripped.

`Summary.scanned` becomes the total number of deadline candidates plus recurring-without-deadline candidates processed. `updated`, `stripped`, and `errors` retain their existing meanings.

## Failure Handling

Completion history is accumulated in memory before any recurrence-title updates are attempted. If any history window or pagination request fails, the recurrence history is considered unavailable for that run and no partially calculated recurrence markers are written.

On a history failure:

- deadline tasks continue to receive normal deadline updates;
- an eligible recurring task that already begins with `[R+…]` is left unchanged;
- an eligible recurring task that begins with a stale `[T±…]` prefix has that deadline prefix removed because deadline absence is known from the active task itself;
- an unmarked eligible recurring task is left unchanged; and
- clearly non-recurring tasks still have stale managed prefixes stripped.

A completion record without a valid task ID or `completed_at` timestamp makes recurrence history unavailable for that run. The record is logged, the scan is aborted, and no partial recurrence ages are written. Per-task Todoist title update failures continue to increment `Summary.errors` without stopping updates for other tasks. Dry-run mode performs all calculations and reports would-be changes without writing.

## Testing

Formatter tests cover:

- `[R+0d]`, the 99/100-day boundary, and rounded weeks;
- replacing either managed marker with the other;
- idempotent recurrence application and stripping; and
- preservation of user-authored bracketed text and progress suffixes.

Client tests cover:

- completion-date request parameters;
- pagination within an 89-day window;
- authentication and retry behavior; and
- malformed-response rejection and empty response pages.

Orchestrator tests cover:

- no marker before first completion;
- reset to zero after completion;
- elapsed days and timezone-boundary conversion;
- matching the latest completion by task ID;
- backward window traversal and stopping at task creation;
- deadline precedence and deadline removal;
- recurrence removal and stale marker cleanup;
- all-or-nothing recurrence behavior on history failure;
- idempotency, dry-run behavior, summary counts, and isolated update errors; and
- the complete pre-existing deadline and subtask-progress regression suite.

## Non-Goals

- No configurable marker text or thresholds.
- No project- or label-based opt-in.
- No webhook service or persistent database.
- No parsing of recurrence strings to infer completion dates.
- No simultaneous deadline and recurrence markers on one task.

# Deadline Existence Query Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Todoist client fetch every active task with a deadline by using the `!no deadline` filter query.

**Architecture:** Preserve the existing `TodoistClient.list_deadlined_tasks()` interface, retry wrapper, SDK pagination, and page flattening. Change only the Todoist query string and its regression-test expectation.

**Tech Stack:** Python 3.12+, `todoist-api-python`, pytest, `unittest.mock`, uv

## Global Constraints

- Use the exact Todoist filter query `!no deadline`.
- Do not add project exclusions, environment variables, configuration, or client-side deadline filtering.
- Preserve existing pagination flattening and retry behavior.

---

### Task 1: Replace the bounded deadline query

**Files:**
- Modify: `tests/test_todoist_client.py:116-125`
- Modify: `src/countdown/todoist_client.py:98-101`

**Interfaces:**
- Consumes: `TodoistAPI.filter_tasks(query: str)` and existing `_flatten(pages)` behavior.
- Produces: unchanged `TodoistClient.list_deadlined_tasks()` behavior returning a flattened list of task objects, now selected with `!no deadline`.

- [x] **Step 1: Change the regression test expectation**

```python
@patch("countdown.todoist_client.TodoistAPI")
def test_list_deadlined_tasks_uses_filter_query(mock_api_cls: MagicMock) -> None:
    api = mock_api_cls.return_value
    api.filter_tasks.return_value = iter([[MagicMock(id="1"), MagicMock(id="2")]])

    client = TodoistClient(token="t")
    tasks = client.list_deadlined_tasks()

    api.filter_tasks.assert_called_once_with(query="!no deadline")
    assert [t.id for t in tasks] == ["1", "2"]
```

- [x] **Step 2: Run the targeted test and verify RED**

Run:

```bash
uv run pytest tests/test_todoist_client.py::test_list_deadlined_tasks_uses_filter_query -v
```

Expected: FAIL because the actual call still uses `query="deadline before: 5 years from now"`.

- [x] **Step 3: Make the minimal production change**

```python
def list_deadlined_tasks(self):
    return retry_with_backoff(
        lambda: _flatten(self._api.filter_tasks(query="!no deadline"))
    )
```

- [x] **Step 4: Run the targeted test and verify GREEN**

Run:

```bash
uv run pytest tests/test_todoist_client.py::test_list_deadlined_tasks_uses_filter_query -v
```

Expected: PASS.

- [x] **Step 5: Run the complete test suite**

Run:

```bash
uv run pytest
```

Expected: all tests pass with no errors or warnings.

- [x] **Step 6: Review and commit the implementation**

Run:

```bash
git diff --check
git diff -- src/countdown/todoist_client.py tests/test_todoist_client.py docs/superpowers/plans/2026-07-14-deadline-existence-query.md
git add src/countdown/todoist_client.py tests/test_todoist_client.py docs/superpowers/plans/2026-07-14-deadline-existence-query.md
git commit -m "fix: fetch all tasks with deadlines"
```

Expected: one focused commit containing the query change, regression-test update, and implementation plan.

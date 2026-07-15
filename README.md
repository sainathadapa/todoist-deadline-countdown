# Todoist Deadline Countdown & Recurring Count-Up

Live countdown badges on Todoist tasks with deadlines, plus count-up
badges showing how long it has been since you completed a recurring
task — no server, no signup, no third party sees your tasks. Runs in
*your own* GitHub account on the free Actions tier.

| Before | After |
|---|---|
| File 2026 taxes | `[T-15d] File 2026 taxes` |
| Renew passport | `[T-2w] Renew passport` |
| Pay rent | `[T-0d] Pay rent` |
| Submit assignment | `[T+3d] Submit assignment` |
| Plan launch *(with subtasks)* | `[T-15d] Plan launch [7/13]` |
| Call friend X *(recurring every! 6 weeks)* | `[R+42d] Call friend X` |

## Setup (5 minutes)

### 1. Create your own copy

Click the green **Use this template** button at the top of this repo →
**Create a new repository**. Name it whatever you like; private is fine.

### 2. Add your Todoist API token

1. Open <https://todoist.com/app/settings/integrations/developer> and
   copy your API token.
2. In your new repo go to **Settings → Secrets and variables → Actions
   → New repository secret**.
3. Name it exactly `TODOIST_API_TOKEN`, paste the token, **Add secret**.

### 3. Run it for the first time

1. Open the **Actions** tab. If it asks, click *"I understand my
   workflows, go ahead and enable them."*
2. Pick the **countdown** workflow on the left, then **Run workflow** on
   the right.
3. *(Recommended for the first run.)* Tick **Preview changes without
   writing to Todoist**, then **Run workflow**.
4. After ~30 seconds the run finishes — click into it to see a summary
   like `Scanned: 12 · Updated: 3 · Stripped: 0`.
5. Once you're happy, run it again with the box unticked — your tasks
   now have badges.

From here on it runs automatically every 3 hours.

## How do I know it's working?

- Open Todoist — every task with a deadline now starts with `[T-Nd]`,
  `[T-Nw]`, `[T+Nd]`, or `[T+Nw]`. Recurring tasks start with an
  `[R+Nd]` or `[R+Nw]` badge after their first completion.
- Deadlined parent tasks that currently have subtasks also end with
  progress like `[7/13]` (7 completed out of 13 total subtasks).
- The **Actions** tab shows a green check after each scheduled run, plus
  a step summary with how many tasks were scanned and updated.

## What the badges mean

### Deadline countdowns

| Time to deadline | Badge |
|---|---|
| Today | `[T-0d]` |
| 1–99 days away | `[T-Nd]` (e.g. `[T-7d]`, `[T-99d]`) |
| 100+ days away | `[T-Nw]` (e.g. `[T-14w]`, `[T-52w]`) |
| 1–99 days overdue | `[T+Nd]` (e.g. `[T+1d]`, `[T+10d]`) |
| 100+ days overdue | `[T+Nw]` (e.g. `[T+14w]`) |

For deadlined parent tasks with subtasks, a trailing progress suffix is
also added: `[done/total]` (for example `[7/13]`). Subtask progress
suffixes are deadline-only and are not added to recurring count-ups.

### Recurring-task count-ups

| Time since latest completion | Badge |
|---|---|
| 0–99 days | `[R+Nd]` (e.g. `[R+0d]`, `[R+42d]`, `[R+99d]`) |
| 100+ days | `[R+Nw]`, rounded to weeks (e.g. `[R+14w]`, `[R+52w]`) |

A recurrence badge appears only after the task has been completed at
least once. If Todoist returns both deadline and recurrence metadata
for a task, the deadline countdown wins.

## FAQ

### Does it work on the free Todoist plan?
**Yes, for recurring count-ups.** They work with recurring due dates.
Deadline countdown badges still require a Todoist plan that exposes the
`deadline` field, which is different from the regular due date.

### What about recurring tasks?
Use the recurring count-up to see how long it has been since you last
did something:

1. Create `Call friend X` with `every! 6 weeks`. The exclamation mark
   makes Todoist schedule the next occurrence from the actual
   completion date.
2. Complete the task after making the call.
3. On its next run, the workflow reads Todoist completion history and
   annotates the new recurring instance with the elapsed time since
   that completion, such as `[R+42d] Call friend X`.
4. Treat the due date as a cadence or reminder, not a deadline.

If the completion-history API fails, the workflow preserves existing
recurrence badges until a later successful run.

### How do I share this with my partner / friend?
They make their own copy of the template with their own token. Each
copy is fully independent — own repo, own schedule, own time zone.

### Will my copy get updates from this repo automatically?
No. Repositories created from this template are independent copies, not
live mirrors. If this repo gets bug fixes or new features later, you'll
need to apply those changes to your own repo manually.

### How do I change how often it runs?
Edit `.github/workflows/countdown.yml`. The default is `'5 */3 * * *'`
(every 3 hours at :05 past the hour). The minimum allowed by GitHub is
every 5 minutes.

### How do I set the time zone?
By default it's auto-detected from your Todoist user profile. To
override: in your repo, **Settings → Secrets and variables → Actions →
Variables → New repository variable** named `COUNTDOWN_TZ`, value an
IANA name like `Europe/Berlin` or `America/Los_Angeles`.

### My token is valid — is the script seeing it?
Run the doctor subcommand locally:
```bash
TODOIST_API_TOKEN=your-token uv run python -m countdown doctor
```
Prints your detected time zone if the token is valid.

### How do I uninstall?
Strip every deadline and recurrence badge from every task:
```bash
TODOIST_API_TOKEN=your-token uv run python -m countdown --strip-all
```
Then either disable the workflow (Actions tab → countdown → "⋯" →
Disable workflow) or delete the repo. Note: badges that exist on tasks
when the workflow stops running will remain until you run `--strip-all`
or edit the tasks manually.

## Upgrading your copy

Template-created repositories do not receive updates from this repo
automatically.

If you want an update from this repo later, you have two options:

- Simple: open the changed files here and copy the updates into your own
  repo.
- Advanced: add this repo as an `upstream` remote, fetch changes, and
  cherry-pick specific commits you want.

Note: repositories created from a GitHub template have unrelated
history to the template repo, so a normal upstream merge or pull is
usually not the cleanest upgrade path.

## Idempotency

The script identifies its own annotations using the regex
`^\s*\[(?:T[+-]\d+[dwm]|R\+\d+[dw])\]\s*` anchored at
start-of-string. This covers both deadline and recurrence markers, and
`--strip-all` removes both marker families. Anything not matching that
pattern — including user-typed text like `[draft]` mid-title or a
literal `T-15d` in the body — is left untouched. Running the workflow
more often than needed is safe; mid-day runs that find nothing to
change are no-ops.

## Local development

```bash
uv sync --all-extras
uv run pytest
```

Dry-run against your real account without writing:
```bash
TODOIST_API_TOKEN=your-token DRY_RUN=1 uv run python -m countdown
```

## License

MIT

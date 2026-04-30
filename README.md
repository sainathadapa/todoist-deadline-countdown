# Todoist Deadline Countdown

Live countdown badges on every Todoist task that has a deadline — no
server, no signup, no third party sees your tasks. Runs in *your own*
GitHub account on the free Actions tier.

| Before | After |
|---|---|
| File 2026 taxes | `[T-15d] File 2026 taxes` |
| Renew passport | `[T-2w] Renew passport` |
| Pay rent | `[T-0d] Pay rent` |
| Submit assignment | `[T+3d] Submit assignment` |

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
  `[T-Nw]`, `[T+Nd]`, or `[T+Nw]`.
- The **Actions** tab shows a green check after each scheduled run, plus
  a step summary with how many tasks were scanned and updated.

## What the badges mean

| Time to deadline | Badge |
|---|---|
| Today | `[T-0d]` |
| 1–99 days away | `[T-Nd]` (e.g. `[T-7d]`, `[T-99d]`) |
| 100+ days away | `[T-Nw]` (e.g. `[T-14w]`, `[T-52w]`) |
| 1–99 days overdue | `[T+Nd]` (e.g. `[T+1d]`, `[T+10d]`) |
| 100+ days overdue | `[T+Nw]` (e.g. `[T+14w]`) |

## FAQ

### Does it work on the free Todoist plan?
**No.** The `deadline` field is Todoist Pro/Business only. (This is
*different* from the regular due date.)

### What about recurring tasks?
Todoist doesn't allow deadlines on recurring tasks, so they're never
touched.

### How do I share this with my partner / friend?
They make their own copy of the template with their own token. Each
copy is fully independent — own repo, own schedule, own time zone.

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
Strip every badge from every task:
```bash
TODOIST_API_TOKEN=your-token uv run python -m countdown --strip-all
```
Then either disable the workflow (Actions tab → countdown → "⋯" →
Disable workflow) or delete the repo. Note: badges that exist on tasks
when the workflow stops running will remain until you run `--strip-all`
or edit the tasks manually.

## Idempotency

The script identifies its own annotations using the regex
`^\s*\[T[+-]\d+[dwm]\]\s*` anchored at start-of-string. Anything not
matching that pattern — including user-typed text like `[draft]`
mid-title or a literal `T-15d` in the body — is left untouched. Running
the workflow more often than needed is safe; mid-day runs that find
nothing to change are no-ops.

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

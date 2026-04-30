# todoist-deadline-countdown

Daily GitHub Actions cron job that suffixes every uncompleted Todoist task with
a countdown badge based on its deadline.

## What it does

| Time to deadline | Suffix |
|---|---|
| 10 days overdue | `[T+10d]` |
| 1 day overdue | `[T+1d]` |
| Today | `[T-0d]` |
| 1–14 days | `[T-Nd]` (e.g. `[T-7d]`) |
| 15–89 days | `[T-Nw]` (e.g. `[T-2w]`, `[T-13w]`) |
| 90+ days | `[T-Nm]` (e.g. `[T-3m]`, `[T-12m]`) |

Runs once daily and is idempotent — re-running mid-day is a no-op.

## Setup

1. Fork or clone this repo on github.com.
2. Get your Todoist API token: <https://www.todoist.com/help/articles/find-your-api-token-Jpzx9IIlB>
3. In repo Settings → Secrets and variables → Actions, add a secret named `TODOIST_API_TOKEN`.
4. (Optional) Add a repository variable `COUNTDOWN_TZ` with an IANA timezone name to override
   timezone detection (default: auto-detected from your Todoist user profile).
5. Push to `main`. The workflow will fire on the next scheduled run, or you can trigger it
   manually via the Actions tab → "countdown" → "Run workflow".

## Local development

```bash
uv sync --all-extras
uv run pytest
```

To dry-run against your real account without writing:
```bash
TODOIST_API_TOKEN=your-token DRY_RUN=1 uv run python -m countdown
```

To validate the token:
```bash
TODOIST_API_TOKEN=your-token uv run python -m countdown doctor
```

## Rollback

To remove every countdown suffix from every task:
```bash
TODOIST_API_TOKEN=your-token uv run python -m countdown --strip-all
```

## Idempotency

The script identifies its own annotations using the regex `\s*\[T[+-]\d+[dwm]\]\s*$`
anchored at end-of-string. Anything not matching that pattern — including user-typed
text like `[draft]` or a literal `T-15d` mid-title — is left untouched.

## Caveats

- **Pro/Business only.** Todoist's `deadline` field is paid-tier only.
- **One-time deadlines only.** Recurring tasks can't have deadlines (Todoist limitation).
- **Title is the state.** No database; if you delete this repo, badges remain on
  existing tasks. Run `--strip-all` first if you want a clean uninstall.

## License

MIT

# todoist-deadline-countdown

Daily GitHub Actions cron job that suffixes every uncompleted Todoist task with a
countdown badge based on its deadline:

- `[T-3d]` → 3 days until deadline
- `[T-2w]` → ~2 weeks
- `[T-6m]` → ~6 months
- `[T+1d]` → 1 day overdue
- `[T-0d]` → due today

See README at the end of implementation for setup details.

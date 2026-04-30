"""Countdown suffix formatting and idempotent strip/apply helpers."""


def format_suffix(delta_days: int) -> str:
    """Return the bracket-less countdown suffix for a given delta in days.

    Rules:
      delta_days <  0      -> "T+{abs(delta)}d"  (overdue, count up in days)
      0 <= delta_days <=14 -> "T-{delta}d"
      15 <= delta_days <=89 -> "T-{round(delta/7)}w"
      delta_days >= 90      -> "T-{round(delta/30)}m"
    """
    if delta_days < 0:
        return f"T+{-delta_days}d"
    if delta_days <= 14:
        return f"T-{delta_days}d"
    if delta_days <= 89:
        return f"T-{round(delta_days / 7)}w"
    return f"T-{round(delta_days / 30)}m"

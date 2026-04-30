"""Countdown suffix formatting and idempotent strip/apply helpers."""

import re


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


SUFFIX_RE = re.compile(r"\s*\[T[+-]\d+[dwm]\]\s*$")


def strip_suffix(content: str) -> str:
    """Remove a trailing countdown suffix if present. Idempotent."""
    return SUFFIX_RE.sub("", content).rstrip()


def apply_suffix(content: str, suffix: str) -> str:
    """Replace any existing countdown suffix with `[suffix]` at the end."""
    base = strip_suffix(content)
    if not base:
        return f"[{suffix}]"
    return f"{base} [{suffix}]"

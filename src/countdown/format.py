"""Countdown prefix formatting and idempotent strip/apply helpers."""

import re


def format_marker(delta_days: int) -> str:
    """Return the bracket-less countdown marker for a given delta in days.

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


PREFIX_RE = re.compile(r"^\s*\[T[+-]\d+[dwm]\]\s*")
# Matches a marker anywhere a task might carry it (used for filtering search results).
MARKER_RE = re.compile(r"\[T[+-]\d+[dwm]\]")


def strip_marker(content: str) -> str:
    """Remove a leading countdown marker if present. Idempotent."""
    return PREFIX_RE.sub("", content).strip()


def apply_marker(content: str, marker: str) -> str:
    """Replace any existing countdown marker with `[marker]` at the start."""
    base = strip_marker(content)
    if not base:
        return f"[{marker}]"
    return f"[{marker}] {base}"

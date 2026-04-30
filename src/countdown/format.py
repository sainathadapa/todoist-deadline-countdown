"""Countdown prefix formatting and idempotent strip/apply helpers."""

import re


def format_marker(delta_days: int) -> str:
    """Return the bracket-less countdown marker for a given delta in days.

    Rules (applied symmetrically to past and future):
      |delta_days| <= 99  -> days  ("T-Nd" or "T+Nd")
      |delta_days| >= 100 -> weeks ("T-Nw" or "T+Nw")
    """
    sign = "-" if delta_days >= 0 else "+"
    magnitude = abs(delta_days)
    if magnitude <= 99:
        return f"T{sign}{magnitude}d"
    return f"T{sign}{round(magnitude / 7)}w"


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

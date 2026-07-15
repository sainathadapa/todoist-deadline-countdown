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


def format_recurrence_marker(elapsed_days: int) -> str:
    """Return the bracket-less count-up marker for elapsed calendar days."""
    magnitude = max(0, elapsed_days)
    if magnitude <= 99:
        return f"R+{magnitude}d"
    return f"R+{round(magnitude / 7)}w"


DEADLINE_PREFIX_RE = re.compile(r"^\s*\[T[+-]\d+[dwm]\]\s*")
RECURRENCE_PREFIX_RE = re.compile(r"^\s*\[R\+\d+[dw]\]\s*")
PREFIX_RE = re.compile(
    r"^(?:\s*\[(?:T[+-]\d+[dwm]|R\+\d+[dw])\]\s*)+"
)
# Matches a marker anywhere a task might carry it (used for filtering search results).
MARKER_RE = re.compile(r"\[(?:T[+-]\d+[dwm]|R\+\d+[dw])\]")
PROGRESS_SUFFIX_RE = re.compile(r"\s*\[\d+/\d+\]\s*$")


def strip_marker(content: str) -> str:
    """Remove a leading countdown marker if present. Idempotent."""
    return PREFIX_RE.sub("", content).strip()


def apply_marker(content: str, marker: str) -> str:
    """Replace any existing countdown marker with `[marker]` at the start."""
    base = strip_marker(content)
    if not base:
        return f"[{marker}]"
    return f"[{marker}] {base}"


def strip_progress_suffix(content: str) -> str:
    """Remove a trailing `[done/total]` progress suffix if present. Idempotent."""
    return PROGRESS_SUFFIX_RE.sub("", content).strip()


def apply_progress_suffix(content: str, *, completed: int, total: int) -> str:
    """Apply a trailing subtask progress suffix for parent tasks."""
    base = strip_progress_suffix(content)
    if total <= 0:
        return base
    if not base:
        return f"[{completed}/{total}]"
    return f"{base} [{completed}/{total}]"

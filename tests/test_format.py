import pytest

from countdown.format import format_marker


@pytest.mark.parametrize(
    ("delta_days", "expected"),
    [
        (-10, "T+10d"),
        (-1, "T+1d"),
        (0, "T-0d"),
        (1, "T-1d"),
        (14, "T-14d"),
        (15, "T-2w"),
        (21, "T-3w"),
        (60, "T-9w"),
        (89, "T-13w"),
        (90, "T-3m"),
        (180, "T-6m"),
        (365, "T-12m"),
    ],
)
def test_format_marker_boundary_table(delta_days: int, expected: str) -> None:
    assert format_marker(delta_days) == expected

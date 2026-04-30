import pytest

from countdown.format import format_marker


@pytest.mark.parametrize(
    ("delta_days", "expected"),
    [
        (-100, "T+14w"),
        (-99, "T+99d"),
        (-10, "T+10d"),
        (-1, "T+1d"),
        (0, "T-0d"),
        (1, "T-1d"),
        (14, "T-14d"),
        (15, "T-15d"),
        (89, "T-89d"),
        (99, "T-99d"),
        (100, "T-14w"),
        (180, "T-26w"),
        (365, "T-52w"),
    ],
)
def test_format_marker_boundary_table(delta_days: int, expected: str) -> None:
    assert format_marker(delta_days) == expected

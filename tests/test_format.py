import pytest

from countdown.format import apply_progress_suffix, format_marker, strip_progress_suffix


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


def test_apply_progress_suffix_adds_and_replaces_managed_suffix() -> None:
    assert (
        apply_progress_suffix("[T-15d] Parent [1/3]", completed=2, total=3)
        == "[T-15d] Parent [2/3]"
    )


def test_apply_progress_suffix_removes_suffix_when_no_subtasks() -> None:
    assert apply_progress_suffix("[T-15d] Parent [1/3]", completed=0, total=0) == "[T-15d] Parent"
    assert strip_progress_suffix("[T-15d] Parent [1/3]") == "[T-15d] Parent"

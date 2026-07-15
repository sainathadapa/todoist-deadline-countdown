import pytest

from countdown.format import PREFIX_RE, apply_marker, format_marker, strip_marker


@pytest.mark.parametrize(
    ("content", "stripped"),
    [
        ("[T-15d] File 2026 taxes", "File 2026 taxes"),
        ("[T-2w] File 2026 taxes", "File 2026 taxes"),
        ("[T-6m] File 2026 taxes", "File 2026 taxes"),
        ("[T+3d] File 2026 taxes", "File 2026 taxes"),
        ("[T-0d] File 2026 taxes", "File 2026 taxes"),
        ("  [T-2w]  File 2026 taxes", "File 2026 taxes"),
        ("Renew passport", "Renew passport"),
        ("[draft] Meeting", "[draft] Meeting"),
        ("Note about T-15d in body", "Note about T-15d in body"),
        ("", ""),
    ],
)
def test_strip_marker(content: str, stripped: str) -> None:
    assert strip_marker(content) == stripped


def test_apply_marker_prepends_marker() -> None:
    assert apply_marker("File 2026 taxes", "T-15d") == "[T-15d] File 2026 taxes"


def test_apply_marker_replaces_existing_marker() -> None:
    assert apply_marker("[T-15d] File 2026 taxes", "T-2w") == "[T-2w] File 2026 taxes"


def test_apply_marker_is_idempotent() -> None:
    once = apply_marker("File 2026 taxes", "T-15d")
    twice = apply_marker(once, "T-15d")
    assert once == twice


def test_apply_marker_preserves_user_brackets() -> None:
    assert apply_marker("[draft] Meeting", "T-1d") == "[T-1d] [draft] Meeting"


def test_apply_marker_preserves_bare_t_minus_text() -> None:
    # "T-15d" without brackets is user content — never touched.
    result = apply_marker("Note about T-15d in body", "T-3d")
    assert result == "[T-3d] Note about T-15d in body"


def test_round_trip_via_format_marker() -> None:
    base = "File 2026 taxes"
    marker = format_marker(15)
    once = apply_marker(base, marker)
    twice = apply_marker(once, marker)
    assert once == twice
    assert strip_marker(once) == base


def test_prefix_re_anchored_to_start() -> None:
    # The regex must only match at start-of-string.
    assert PREFIX_RE.search("middle of title [T-15d] here") is None
    assert PREFIX_RE.search("[T-15d] start-of-title") is not None

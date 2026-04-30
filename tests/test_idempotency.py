import pytest

from countdown.format import SUFFIX_RE, apply_suffix, format_suffix, strip_suffix


@pytest.mark.parametrize(
    ("content", "stripped"),
    [
        ("File 2026 taxes [T-15d]", "File 2026 taxes"),
        ("File 2026 taxes [T-2w]", "File 2026 taxes"),
        ("File 2026 taxes [T-6m]", "File 2026 taxes"),
        ("File 2026 taxes [T+3d]", "File 2026 taxes"),
        ("File 2026 taxes [T-0d]", "File 2026 taxes"),
        ("File 2026 taxes  [T-2w]  ", "File 2026 taxes"),
        ("Renew passport", "Renew passport"),
        ("Meeting [draft]", "Meeting [draft]"),
        ("Note about T-15d in body", "Note about T-15d in body"),
        ("", ""),
    ],
)
def test_strip_suffix(content: str, stripped: str) -> None:
    assert strip_suffix(content) == stripped


def test_apply_suffix_appends_marker() -> None:
    assert apply_suffix("File 2026 taxes", "T-15d") == "File 2026 taxes [T-15d]"


def test_apply_suffix_replaces_existing_marker() -> None:
    assert apply_suffix("File 2026 taxes [T-15d]", "T-2w") == "File 2026 taxes [T-2w]"


def test_apply_suffix_is_idempotent() -> None:
    once = apply_suffix("File 2026 taxes", "T-15d")
    twice = apply_suffix(once, "T-15d")
    assert once == twice


def test_apply_suffix_preserves_user_brackets() -> None:
    assert apply_suffix("Meeting [draft]", "T-1d") == "Meeting [draft] [T-1d]"


def test_apply_suffix_preserves_bare_t_minus_text() -> None:
    # "T-15d" without brackets is user content — never touched.
    result = apply_suffix("Note about T-15d in body", "T-3d")
    assert result == "Note about T-15d in body [T-3d]"


def test_round_trip_via_format_suffix() -> None:
    base = "File 2026 taxes"
    suffix = format_suffix(15)
    once = apply_suffix(base, suffix)
    twice = apply_suffix(once, suffix)
    assert once == twice
    assert strip_suffix(once) == base


def test_suffix_re_anchored_to_end() -> None:
    # The regex must only match at end-of-string.
    assert SUFFIX_RE.search("[T-15d] in middle of title") is None
    assert SUFFIX_RE.search("end-of-title [T-15d]") is not None

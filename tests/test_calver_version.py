from __future__ import annotations

import pytest

from calver_scm.calver_version import CalverVersion

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026.4", "2026.04.0"),
        ("2026.4.2", "2026.04.2"),
        ("2026.4.2beta3", "2026.04.2b3"),
        ("2026.4.2.post-2", "2026.04.2.post2"),
        ("2026.4.2.dev-4", "2026.04.2.dev4"),
        ("2026.4.2rc1.post2.dev3+linux.x86_64", "2026.04.2rc1.post2.dev3+linux.x86.64"),
    ],
)
def test_format_month_mode_keeps_padding_and_canonical_suffixes(
    raw: str,
    expected: str,
) -> None:
    """Render month-mode versions with stable zero-padding and PEP 440 suffixes."""
    assert CalverVersion(raw).format(mode="month") == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026.4.5", "2026.04.05.0"),
        ("2026.4.5.2", "2026.04.05.2"),
        ("2026.4.5.2rc1", "2026.04.05.2rc1"),
    ],
)
def test_format_day_mode_handles_optional_patch(raw: str, expected: str) -> None:
    """Render day-mode versions for both three-part and four-part releases."""
    assert CalverVersion(raw).format(mode="day") == expected


@pytest.mark.parametrize("raw", ["2026", "2026.4.5.1.9"])
def test_format_returns_plain_string_when_release_shape_is_unexpected(raw: str) -> None:
    """Fall back to canonical string output for unsupported release lengths."""
    version = CalverVersion(raw)
    assert version.format(mode="month") == str(version)
    assert version.format(mode="day") == str(version)


def test_format_from_base_preserves_suffix_order() -> None:
    """Attach suffixes in pre, post, dev, local order when rendering from a base."""
    version = CalverVersion("2026.4.2rc1.post2.dev3+abc")
    assert (
        version.format_from_base(base="2026.04", patch=7)
        == "2026.04.7rc1.post2.dev3+abc"
    )

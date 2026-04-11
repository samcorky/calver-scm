"""Tests for ``calver_scm.calver_version``."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, cast

if TYPE_CHECKING:
    from collections.abc import Callable

import pytest

from calver_scm.calver_version import CalverVersion

Mode = Literal["month", "day"]


@pytest.fixture
def make_version() -> Callable[[str], CalverVersion]:
    """Create a `CalverVersion` from a version string."""

    def _make(version: str) -> CalverVersion:
        return CalverVersion(version)

    return _make


@pytest.fixture(params=["month", "day"])
def mode(request: pytest.FixtureRequest) -> Mode:
    return cast("Mode", request.param)


@pytest.mark.parametrize(
    ("version", "mode", "expected"),
    [
        ("2026.04", "month", "2026.04.0"),
        ("2026.04.1", "month", "2026.04.1"),
        ("2026.4", "month", "2026.04.0"),
        ("2026.4.1", "month", "2026.04.1"),
        ("2026.04.15", "day", "2026.04.15.0"),
        ("2026.04.15.2", "day", "2026.04.15.2"),
        ("2026.4.5", "day", "2026.04.05.0"),
        ("2026.4.5.2", "day", "2026.04.05.2"),
    ],
)
def test_format_release_only(
    make_version: Callable[[str], CalverVersion],
    version: str,
    mode: Mode,
    expected: str,
) -> None:
    assert make_version(version).format(mode=mode) == expected


@pytest.mark.parametrize(
    ("version", "mode", "expected"),
    [
        ("2026.04rc1", "month", "2026.04.0rc1"),
        ("2026.04.1rc2", "month", "2026.04.1rc2"),
        ("2026.04a1", "month", "2026.04.0a1"),
        ("2026.04b2", "month", "2026.04.0b2"),
        ("2026.04.15rc1", "day", "2026.04.15.0rc1"),
        ("2026.04.15.2rc3", "day", "2026.04.15.2rc3"),
        ("2026.04.15a1", "day", "2026.04.15.0a1"),
        ("2026.04.15b2", "day", "2026.04.15.0b2"),
    ],
)
def test_format_preserves_prerelease_segments(
    make_version: Callable[[str], CalverVersion],
    version: str,
    mode: Mode,
    expected: str,
) -> None:
    assert make_version(version).format(mode=mode) == expected


@pytest.mark.parametrize(
    ("version", "mode", "expected"),
    [
        ("2026.04.post1", "month", "2026.04.0.post1"),
        ("2026.04.1.post2", "month", "2026.04.1.post2"),
        ("2026.04.dev1", "month", "2026.04.0.dev1"),
        ("2026.04.1.dev2", "month", "2026.04.1.dev2"),
        ("2026.04.15.post1", "day", "2026.04.15.0.post1"),
        ("2026.04.15.2.post2", "day", "2026.04.15.2.post2"),
        ("2026.04.15.dev1", "day", "2026.04.15.0.dev1"),
        ("2026.04.15.2.dev2", "day", "2026.04.15.2.dev2"),
    ],
)
def test_format_preserves_post_and_dev_segments(
    make_version: Callable[[str], CalverVersion],
    version: str,
    mode: Mode,
    expected: str,
) -> None:
    assert make_version(version).format(mode=mode) == expected


@pytest.mark.parametrize(
    ("version", "mode", "expected"),
    [
        ("2026.04+abc", "month", "2026.04.0+abc"),
        ("2026.04.1+abc.def", "month", "2026.04.1+abc.def"),
        ("2026.04.15+linux.x86_64", "day", "2026.04.15.0+linux.x86.64"),
        ("2026.04.15.2+abc.1", "day", "2026.04.15.2+abc.1"),
    ],
)
def test_format_preserves_local_segment(
    make_version: Callable[[str], CalverVersion],
    version: str,
    mode: Mode,
    expected: str,
) -> None:
    assert make_version(version).format(mode=mode) == expected


@pytest.mark.parametrize(
    ("version", "mode", "expected"),
    [
        ("2026.04rc1.post2.dev3+local", "month", "2026.04.0rc1.post2.dev3+local"),
        (
            "2026.04.1rc2.post3.dev4+linux.1",
            "month",
            "2026.04.1rc2.post3.dev4+linux.1",
        ),
        (
            "2026.04.15rc1.post2.dev3+local",
            "day",
            "2026.04.15.0rc1.post2.dev3+local",
        ),
        (
            "2026.04.15.2rc2.post3.dev4+linux.1",
            "day",
            "2026.04.15.2rc2.post3.dev4+linux.1",
        ),
    ],
)
def test_format_preserves_combined_pep440_segments(
    make_version: Callable[[str], CalverVersion],
    version: str,
    mode: Mode,
    expected: str,
) -> None:
    assert make_version(version).format(mode=mode) == expected


@pytest.mark.parametrize(
    ("version", "mode"),
    [
        ("2026", "month"),
        ("2026.04.15.2", "month"),
        ("2026.04.15.2.9", "month"),
        ("2026", "day"),
        ("2026.04", "day"),
        ("2026.04.15.2.9", "day"),
    ],
)
def test_format_falls_back_to_canonical_string_for_unsupported_release_lengths(
    make_version: Callable[[str], CalverVersion],
    version: str,
    mode: Mode,
) -> None:
    parsed = make_version(version)
    assert parsed.format(mode=mode) == str(parsed)


@pytest.mark.parametrize(
    (
        "version",
        "expected_release",
        "expected_pre",
        "expected_post",
        "expected_dev",
        "expected_local",
    ),
    [
        ("2026.04", (2026, 4), None, None, None, None),
        ("2026.04.1rc2", (2026, 4, 1), ("rc", 2), None, None, None),
        ("2026.04.post3", (2026, 4), None, 3, None, None),
        ("2026.04.dev4", (2026, 4), None, None, 4, None),
        ("2026.04.1+abc.def", (2026, 4, 1), None, None, None, "abc.def"),
        (
            "2026.04.15.2rc1.post3.dev4+linux.1",
            (2026, 4, 15, 2),
            ("rc", 1),
            3,
            4,
            "linux.1",
        ),
    ],
)
def test_version_attributes_preserve_pep440_semantics(
    make_version: Callable[[str], CalverVersion],
    version: str,
    expected_release: tuple[int, ...],
    expected_pre: tuple[str, int] | None,
    expected_post: int | None,
    expected_dev: int | None,
    expected_local: str | None,
) -> None:
    parsed = make_version(version)

    assert parsed.release == expected_release
    assert parsed.pre == expected_pre
    assert parsed.post == expected_post
    assert parsed.dev == expected_dev
    assert parsed.local == expected_local


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("2026.04", "2026.4"),
        ("2026.04.1", "2026.4.1"),
        ("2026.04rc1", "2026.4rc1"),
        ("2026.04.post1", "2026.4.post1"),
        ("2026.04.dev1", "2026.4.dev1"),
    ],
)
def test_str_remains_packaging_canonical_form(
    make_version: Callable[[str], CalverVersion],
    version: str,
    expected: str,
) -> None:
    assert str(make_version(version)) == expected


@pytest.mark.parametrize(
    ("version", "month_expected", "day_expected"),
    [
        (
            "2026.04.1rc2.post3.dev4+abc",
            "2026.04.1rc2.post3.dev4+abc",
            "2026.04.01.0rc2.post3.dev4+abc",
        ),
        (
            "2026.04.15rc1+abc",
            "2026.04.15rc1+abc",
            "2026.04.15.0rc1+abc",
        ),
    ],
)
def test_format_is_distinct_from_canonical_str_when_padding_or_mode_matters(
    make_version: Callable[[str], CalverVersion],
    version: str,
    month_expected: str,
    day_expected: str,
) -> None:
    parsed = make_version(version)

    assert parsed.format(mode="month") == month_expected
    assert parsed.format(mode="day") == day_expected
    assert str(parsed) != month_expected or str(parsed) != day_expected


def test_fixture_exercises_both_modes(
    make_version: Callable[[str], CalverVersion],
    mode: Mode,
) -> None:
    parsed = make_version("2026.04.1")

    result = parsed.format(mode=mode)

    if mode == "month":
        assert result == "2026.04.1"
    else:
        assert result == "2026.04.01.0"


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("2026.04.15", "2026.04.15"),
        ("2026.04.15rc1", "2026.04.15rc1"),
    ],
)
def test_month_mode_interprets_three_part_release_as_patch(
    make_version: Callable[[str], CalverVersion],
    version: str,
    expected: str,
) -> None:
    assert make_version(version).format(mode="month") == expected


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("2026.04.1", "2026.04.01.0"),
        ("2026.04.1rc2", "2026.04.01.0rc2"),
    ],
)
def test_day_mode_interprets_three_part_release_as_day_with_implicit_patch_zero(
    make_version: Callable[[str], CalverVersion],
    version: str,
    expected: str,
) -> None:
    assert make_version(version).format(mode="day") == expected


@pytest.mark.parametrize(
    ("raw", "month_expected"),
    [
        ("2026.04.1alpha2", "2026.04.1a2"),
        ("2026.04.1beta3", "2026.04.1b3"),
        ("2026.04.1preview4", "2026.04.1rc4"),
        ("2026.04.1pre4", "2026.04.1rc4"),
        ("2026.04.1c4", "2026.04.1rc4"),
        ("2026.04.1-r5", "2026.04.1.post5"),
        ("2026.04.1rev6", "2026.04.1.post6"),
        ("2026.04.1.post-7", "2026.04.1.post7"),
        ("2026.04.1dev", "2026.04.1.dev0"),
        ("2026.04.1.dev-8", "2026.04.1.dev8"),
    ],
)
def test_format_handles_pep440_naming_variants(
    make_version: Callable[[str], CalverVersion],
    raw: str,
    month_expected: str,
) -> None:
    assert make_version(raw).format(mode="month") == month_expected

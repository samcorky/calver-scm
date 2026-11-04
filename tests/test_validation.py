from __future__ import annotations

import pytest

from calver_scm.config import CalverConfig, CalverMode
from calver_scm.release import TagKind
from calver_scm.validation import (
    IssueCode,
    ValidationResult,
    VersionParts,
    validate_version,
)

pytestmark = pytest.mark.unit

MONTH = CalverConfig()
DAY = CalverConfig(mode=CalverMode.DAY)
WEEK = CalverConfig(mode=CalverMode.WEEK)
YEAR = CalverConfig(mode=CalverMode.YEAR)
UNSTABLE = CalverConfig(stable=False)


def codes(result: ValidationResult) -> list[IssueCode]:
    return [issue.code for issue in result.issues]


@pytest.mark.parametrize(
    ("text", "config"),
    [
        ("2026.4.2", MONTH),
        ("2026.4", MONTH),
        ("2026.04.2", MONTH),
        ("2026.4.0rc1", MONTH),
        ("2026.4.2.post1", MONTH),
        ("2026.4.2.dev3", MONTH),
        ("2026.4.2.dev3+g1a2b3c4.d20260415", MONTH),
        ("2026.4.2rc1.post2.dev3+abc", MONTH),
        ("2026.12.0", MONTH),
        ("2026.2.28", DAY),
        ("2024.2.29.1", DAY),
        ("2026.16.1", WEEK),
        ("2026.53.0", WEEK),
        ("2027.53.0", WEEK),
        ("2026.0", YEAR),
        ("2026", YEAR),
        ("0.2026.4.2", UNSTABLE),
        ("26.4.1", CalverConfig(scheme="YY.MM")),
        ("0.4.1", CalverConfig(scheme="YY.MM")),
        ("2026.31", CalverConfig(scheme="YYYY.DD")),
    ],
)
def test_valid_versions(text: str, config: CalverConfig) -> None:
    """Accept well-formed versions, including PEP 440 suffixes."""
    result = validate_version(text, config)
    assert result.valid
    assert result.issues == ()
    assert result.input == text


@pytest.mark.parametrize(
    ("text", "config", "expected"),
    [
        ("foo", MONTH, [IssueCode.INVALID_PEP440]),
        ("", MONTH, [IssueCode.INVALID_PEP440]),
        ("2026.4.2.xyz", MONTH, [IssueCode.INVALID_PEP440]),
        ("2026", MONTH, [IssueCode.INVALID_RELEASE_SHAPE]),
        ("2026.4.2.1", MONTH, [IssueCode.INVALID_RELEASE_SHAPE]),
        ("2026.4", DAY, [IssueCode.INVALID_RELEASE_SHAPE]),
        ("2026.13.1", MONTH, [IssueCode.INVALID_MONTH]),
        ("2026.0.1", MONTH, [IssueCode.INVALID_MONTH]),
        ("2026.2.30", DAY, [IssueCode.INVALID_DAY]),
        ("2026.2.29", DAY, [IssueCode.INVALID_DAY]),
        ("2026.4.31", DAY, [IssueCode.INVALID_DAY]),
        ("2026.4.0.1", DAY, [IssueCode.INVALID_DAY]),
        ("2026.13.32", DAY, [IssueCode.INVALID_MONTH, IssueCode.INVALID_DAY]),
        ("2026.0.1", WEEK, [IssueCode.INVALID_WEEK]),
        ("2026.54.0", WEEK, [IssueCode.INVALID_WEEK]),
        ("10000.1.0", MONTH, [IssueCode.INVALID_YEAR]),
        ("100.4.0", CalverConfig(scheme="YY.MM"), [IssueCode.INVALID_YEAR]),
        ("2026.32", CalverConfig(scheme="YYYY.DD"), [IssueCode.INVALID_DAY]),
        ("2026.4.2", UNSTABLE, [IssueCode.MISSING_STABILITY_PREFIX]),
        ("0.2026.13.2", UNSTABLE, [IssueCode.INVALID_MONTH]),
        ("0.2026.4.2", MONTH, [IssueCode.UNEXPECTED_STABILITY_PREFIX]),
    ],
)
def test_invalid_versions(
    text: str, config: CalverConfig, expected: list[IssueCode]
) -> None:
    """Report each way a version fails syntax or the CalVer policy."""
    result = validate_version(text, config)
    assert not result.valid
    assert codes(result) == expected
    assert all(issue.message for issue in result.issues)


def test_tag_mode_requires_and_strips_the_configured_prefix() -> None:
    """Interpret the input as a Git tag including its prefix."""
    assert validate_version("v2026.4.2", MONTH, is_tag=True).valid
    missing = validate_version("2026.4.2", MONTH, is_tag=True)
    assert codes(missing) == [IssueCode.MISSING_TAG_PREFIX]
    custom = CalverConfig(tag_prefix="release-")
    assert validate_version("release-2026.4.2", custom, is_tag=True).valid
    assert codes(validate_version("v2026.4.2", custom, is_tag=True)) == [
        IssueCode.MISSING_TAG_PREFIX
    ]


def test_tag_mode_without_a_prefix_accepts_bare_versions() -> None:
    """Skip the prefix check when no prefix is configured."""
    config = CalverConfig(tag_prefix="")
    assert validate_version("2026.4.2", config, is_tag=True).valid


def test_plain_version_with_leading_v_is_accepted_per_pep_440() -> None:
    """PEP 440 allows a leading 'v', so plain mode does not insist on --tag."""
    assert validate_version("v2026.4.2", MONTH).valid


@pytest.mark.parametrize(
    ("text", "kind", "prerelease"),
    [
        ("2026.4.2", TagKind.FINAL, False),
        ("2026.4.2rc1", TagKind.PRERELEASE, True),
        ("2026.4.2a1", TagKind.PRERELEASE, True),
        ("2026.4.2.post1", TagKind.POSTRELEASE, False),
        ("2026.4.2.dev3", TagKind.DEV, True),
    ],
)
def test_a_valid_version_reports_its_kind(
    text: str, kind: TagKind, prerelease: bool
) -> None:
    result = validate_version(text, MONTH)
    assert result.kind is kind
    assert result.is_prerelease is prerelease


@pytest.mark.parametrize("text", ["2026.13.1", "not-a-version", "2026.4.2.3.4"])
def test_an_invalid_version_reports_no_kind(text: str) -> None:
    result = validate_version(text, MONTH)
    assert result.kind is None
    assert result.is_prerelease is None


TAGGED = CalverConfig(stable=False, tag_prefix="v")


@pytest.mark.parametrize(
    ("text", "config", "is_tag", "expected"),
    [
        (
            "2026.4.2",
            MONTH,
            False,
            VersionParts(
                "2026.4",
                (("YYYY", 2026), ("MM", 4)),
                2,
                None,
                None,
                None,
                "2026.4.2",
                True,
                "",
            ),
        ),
        (
            "2026.04",
            MONTH,
            False,
            VersionParts(
                "2026.4",
                (("YYYY", 2026), ("MM", 4)),
                0,
                None,
                None,
                None,
                "2026.4",
                True,
                "",
            ),
        ),
        (
            "v0.2026.11.0.post1",
            TAGGED,
            True,
            VersionParts(
                "2026.11",
                (("YYYY", 2026), ("MM", 11)),
                0,
                None,
                1,
                None,
                "0.2026.11.0.post1",
                False,
                "v",
            ),
        ),
        (
            "0.2026.11.0rc2",
            UNSTABLE,
            False,
            VersionParts(
                "2026.11",
                (("YYYY", 2026), ("MM", 11)),
                0,
                "rc2",
                None,
                None,
                "0.2026.11.0rc2",
                False,
                "",
            ),
        ),
        (
            "2026.4.1.dev3",
            MONTH,
            False,
            VersionParts(
                "2026.4",
                (("YYYY", 2026), ("MM", 4)),
                1,
                None,
                None,
                3,
                "2026.4.1.dev3",
                True,
                "",
            ),
        ),
        (
            "2026.4.20.1",
            DAY,
            False,
            VersionParts(
                "2026.4.20",
                (("YYYY", 2026), ("MM", 4), ("DD", 20)),
                1,
                None,
                None,
                None,
                "2026.4.20.1",
                True,
                "",
            ),
        ),
        (
            "2026.7",
            YEAR,
            False,
            VersionParts(
                "2026",
                (("YYYY", 2026),),
                7,
                None,
                None,
                None,
                "2026.7",
                True,
                "",
            ),
        ),
    ],
)
def test_a_valid_version_reports_its_parts(
    text: str, config: CalverConfig, is_tag: bool, expected: VersionParts
) -> None:
    """Report the parts of a valid version, with the stability and tag prefix."""
    assert validate_version(text, config, is_tag=is_tag).parts == expected


@pytest.mark.parametrize("text", ["2026.13.1", "not-a-version", "2026.4.2.3.4"])
def test_an_invalid_version_reports_no_parts(text: str) -> None:
    """Report no parts for an input that fails validation."""
    assert validate_version(text, MONTH).parts is None

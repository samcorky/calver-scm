from __future__ import annotations

import calendar
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from packaging.version import InvalidVersion

from calver_scm.calver_version import CalverVersion
from calver_scm.parser import _has_misplaced_stability_prefix

if TYPE_CHECKING:
    from calver_scm.config import CalverConfig

MAX_YEAR = 9999
MAX_ISO_WEEK = 53


class IssueCode(StrEnum):
    """Machine-readable reason a version or tag does not fit the CalVer policy."""

    MISSING_TAG_PREFIX = "missing_tag_prefix"
    INVALID_PEP440 = "invalid_pep440"
    MISSING_STABILITY_PREFIX = "missing_stability_prefix"
    UNEXPECTED_STABILITY_PREFIX = "unexpected_stability_prefix"
    INVALID_RELEASE_SHAPE = "invalid_release_shape"
    INVALID_YEAR = "invalid_year"
    INVALID_MONTH = "invalid_month"
    INVALID_WEEK = "invalid_week"
    INVALID_DAY = "invalid_day"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One reason the input is not acceptable."""

    code: IssueCode
    message: str


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Outcome of validating one version or tag against the CalVer policy."""

    input: str
    issues: tuple[ValidationIssue, ...]

    @property
    def valid(self) -> bool:
        """Whether the input satisfies the syntax and the CalVer policy."""
        return not self.issues


def validate_version(
    text: str, config: CalverConfig, *, is_tag: bool = False
) -> ValidationResult:
    """Check PEP 440 syntax and fit with the configured CalVer scheme; no I/O.

    Pre-release, post-release, dev and local suffixes are accepted when the
    release segment is valid. Calendar ranges are checked per component only:
    `YYYY.WW` takes its year from the calendar date, not the ISO week-year, so
    week 53 can legitimately appear in years that have 52 ISO weeks.
    """
    candidate = text
    if is_tag and config.tag_prefix:
        if not text.startswith(config.tag_prefix):
            return _invalid(
                text,
                IssueCode.MISSING_TAG_PREFIX,
                f"Tag must start with the configured prefix {config.tag_prefix!r}",
            )
        candidate = text.removeprefix(config.tag_prefix)

    try:
        version = CalverVersion(candidate)
    except InvalidVersion:
        return _invalid(
            text,
            IssueCode.INVALID_PEP440,
            f"{candidate!r} is not a valid PEP 440 version",
        )

    release = version.release
    if config.stable:
        if _has_misplaced_stability_prefix(candidate, version, config):
            return _invalid(
                text,
                IssueCode.UNEXPECTED_STABILITY_PREFIX,
                "Leading '0.' marks an unstable version but stable = true",
            )
    elif release[0] != 0:
        return _invalid(
            text,
            IssueCode.MISSING_STABILITY_PREFIX,
            "stable = false requires a leading '0.' release component",
        )
    else:
        release = release[1:]

    tokens = config.scheme_tokens
    if len(release) not in (len(tokens), len(tokens) + 1):
        return _invalid(
            text,
            IssueCode.INVALID_RELEASE_SHAPE,
            f"Scheme {'.'.join(tokens)} expects {len(tokens)} date components and an "
            f"optional patch, got {len(release)} release components",
        )

    return ValidationResult(
        text, tuple(_calendar_issues(tokens, release[: len(tokens)]))
    )


def _invalid(text: str, code: IssueCode, message: str) -> ValidationResult:
    return ValidationResult(text, (ValidationIssue(code, message),))


def _calendar_issues(
    tokens: tuple[str, ...], parts: tuple[int, ...]
) -> list[ValidationIssue]:
    """Check each date component against its calendar range."""
    values = dict(zip(tokens, parts, strict=True))
    issues: list[ValidationIssue] = []

    year: int | None = None
    if "YYYY" in values:
        year = values["YYYY"]
    elif "YY" in values:
        year = 2000 + values["YY"]
    if "YYYY" in values and not 1 <= values["YYYY"] <= MAX_YEAR:
        issues.append(
            _range(IssueCode.INVALID_YEAR, "Year", 1, MAX_YEAR, values["YYYY"])
        )
    if "YY" in values and not 0 <= values["YY"] <= 99:
        issues.append(_range(IssueCode.INVALID_YEAR, "Year", 0, 99, values["YY"]))

    month = values.get("MM")
    if month is not None and not 1 <= month <= 12:
        issues.append(_range(IssueCode.INVALID_MONTH, "Month", 1, 12, month))

    week = values.get("WW")
    if week is not None and not 1 <= week <= MAX_ISO_WEEK:
        issues.append(_range(IssueCode.INVALID_WEEK, "Week", 1, MAX_ISO_WEEK, week))

    day = values.get("DD")
    if day is not None:
        last_day = 31
        if year is not None and month is not None and 1 <= month <= 12:
            last_day = calendar.monthrange(year, month)[1]
        if not 1 <= day <= last_day:
            issues.append(_range(IssueCode.INVALID_DAY, "Day", 1, last_day, day))

    return issues


def _range(
    code: IssueCode, label: str, low: int, high: int, got: int
) -> ValidationIssue:
    return ValidationIssue(code, f"{label} must be between {low} and {high}, got {got}")

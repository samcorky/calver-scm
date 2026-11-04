from __future__ import annotations

import calendar
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from packaging.version import InvalidVersion

from calver_scm.calver_version import CalverVersion
from calver_scm.parser import (
    _has_misplaced_stability_prefix,
    _parse_tag,
    _release_components,
)
from calver_scm.release import NextTagError, TagKind, plan_next_tag, version_kind
from calver_scm.utils import _date_parts, _format_date_parts

if TYPE_CHECKING:
    import datetime
    from collections.abc import Collection, Iterable

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
    TAG_EXISTS = "tag_exists"
    PAST_PERIOD = "past_period"
    SKIPPED_PATCH = "skipped_patch"
    LOWER_THAN_EXISTING = "lower_than_existing"


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
    kind: TagKind | None = None
    """How the version is treated when numbering releases; only set when valid."""

    @property
    def valid(self) -> bool:
        """Whether the input satisfies the syntax and the CalVer policy."""
        return not self.issues

    @property
    def is_prerelease(self) -> bool | None:
        """Whether a valid input is a pre-release or dev release; None if invalid."""
        if self.kind is None:
            return None
        return self.kind in (TagKind.PRERELEASE, TagKind.DEV)


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

    issues = tuple(_calendar_issues(tokens, release[: len(tokens)]))
    return ValidationResult(text, issues, None if issues else version_kind(version))


def validate_against_repo(
    result: ValidationResult,
    config: CalverConfig,
    tags: Iterable[str],
    *,
    head_tags: Collection[str],
    today: datetime.date,
) -> ValidationResult:
    """Add the repository checks to a result for a tag; no I/O.

    Judges the tag as a new release in the given tags, so it answers whether
    the tag makes sense here, not only whether it is well-formed. A result that
    already has issues is returned unchanged, as there is nothing sound to
    compare.

    A tag in `head_tags` is the one being built, so it does not count as
    already existing and is left out of the comparison. Every other tag, on
    any branch, is compared with. Post-releases are only checked for existence
    and period, as they legitimately follow an older release.
    """
    if not result.valid:
        return result
    tag = result.input
    parsed = _parse_tag(tag, config)
    components = None if parsed is None else _release_components(parsed, config)
    assert parsed is not None
    assert components is not None
    period_parts, patch = components

    known = sorted(set(tags))
    building = tag in head_tags  # a tag-push build: the tag exists by design
    taken = [
        t
        for t in known
        if (t == tag or _parse_tag(t, config) == parsed) and not (t == tag and building)
    ]
    others = [t for t in known if not (building and t == tag)]
    issues: list[ValidationIssue] = []
    if taken:
        issues.append(
            ValidationIssue(IssueCode.TAG_EXISTS, f"Tag {taken[0]} already exists")
        )

    current = _date_parts(today, config)
    if period_parts < current:
        issues.append(
            ValidationIssue(
                IssueCode.PAST_PERIOD,
                f"Tag is in period {_format_date_parts(period_parts)} but the "
                f"current period is {_format_date_parts(current)}",
            )
        )
    elif period_parts == current and parsed.post is None and parsed.dev is None:
        issues.extend(_skipped_patch(others, config, today, patch))

    if _is_final(parsed):
        issues.extend(_lower_than_existing(others, config, parsed))
    all_issues = (*result.issues, *issues)
    return ValidationResult(tag, all_issues, None if all_issues else result.kind)


def _is_final(version: CalverVersion) -> bool:
    return version.pre is None and version.post is None and version.dev is None


def _skipped_patch(
    others: list[str], config: CalverConfig, today: datetime.date, patch: int
) -> list[ValidationIssue]:
    """Flag a patch beyond the one `next-tag` would use for a final or candidate."""
    try:
        expected = plan_next_tag(others, config, today=today)
    except NextTagError:
        return []  # patch = false and already released: nothing to number against
    if patch <= expected.patch:
        return []
    return [
        ValidationIssue(
            IssueCode.SKIPPED_PATCH,
            f"Patch {patch} skips ahead; next-tag would propose {expected.tag}",
        )
    ]


def _lower_than_existing(
    others: list[str], config: CalverConfig, parsed: CalverVersion
) -> list[ValidationIssue]:
    """Flag a final tag that sorts below an existing final tag."""
    higher = [
        (version, t)
        for t in others
        if (version := _parse_tag(t, config)) is not None
        and _is_final(version)
        and version > parsed
    ]
    if not higher:
        return []
    return [
        ValidationIssue(
            IssueCode.LOWER_THAN_EXISTING,
            f"Tag is lower than the existing release {max(higher)[1]}",
        )
    ]


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

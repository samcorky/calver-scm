from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from calver_scm.parser import _parse_tag, _release_components
from calver_scm.utils import _apply_stability_prefix, _base, _date_parts

if TYPE_CHECKING:
    import datetime
    from collections.abc import Iterable

    from calver_scm.calver_version import CalverVersion
    from calver_scm.config import CalverConfig


class PreReleaseChannel(StrEnum):
    """A PEP 440 pre-release channel, in the order PEP 440 ranks them."""

    A = "a"
    B = "b"
    RC = "rc"


class NextTagReason(StrEnum):
    """Why the next tag has the number it has."""

    NEW_PERIOD = "new_period"
    NEXT_PATCH = "next_patch"
    NEW_PRERELEASE = "new_prerelease"
    NEXT_PRERELEASE = "next_prerelease"
    PROMOTION = "promotion"
    NEW_POSTRELEASE = "new_postrelease"
    NEXT_POSTRELEASE = "next_postrelease"

    @property
    def label(self) -> str:
        """A short human-readable name for the reason."""
        return _NEXT_TAG_TEXT[self][0]

    @property
    def description(self) -> str:
        """One sentence explaining why the tag has this patch."""
        return _NEXT_TAG_TEXT[self][1]


_NEXT_TAG_TEXT: dict[NextTagReason, tuple[str, str]] = {
    NextTagReason.NEW_PERIOD: (
        "New period",
        "No release exists in this period yet, so numbering starts at 0.",
    ),
    NextTagReason.NEXT_PATCH: (
        "Next patch",
        "A release already exists in this period, so the patch moves on from it.",
    ),
    NextTagReason.NEW_PRERELEASE: (
        "First pre-release",
        "No pre-release of this channel exists for the next release yet, "
        "so numbering starts at 1.",
    ),
    NextTagReason.NEXT_PRERELEASE: (
        "Next pre-release",
        "A pre-release of this channel already exists for the next release, "
        "so the number moves on from it.",
    ),
    NextTagReason.PROMOTION: (
        "Promotion",
        "A pre-release exists for the next release, so the final tag promotes it.",
    ),
    NextTagReason.NEW_POSTRELEASE: (
        "First post-release",
        "The latest release has no post-release yet, so numbering starts at 1.",
    ),
    NextTagReason.NEXT_POSTRELEASE: (
        "Next post-release",
        "The latest release already has a post-release, "
        "so the number moves on from it.",
    ),
}


class NextTagError(Exception):
    """Raised when no safe next release tag can be proposed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class NextTag:
    """A proposed release tag and the evidence behind it."""

    tag: str
    version: str
    patch: int
    reason: NextTagReason
    latest_tag: str | None
    channel: PreReleaseChannel | None = None

    @property
    def is_prerelease(self) -> bool:
        """Whether the proposed tag is a pre-release."""
        return self.channel is not None


def plan_next_tag(
    tags: Iterable[str],
    config: CalverConfig,
    *,
    today: datetime.date,
    pre: PreReleaseChannel | None = None,
    promote: bool = False,
    post: bool = False,
) -> NextTag:
    """Propose the next release tag for the period containing `today`; no I/O.

    Every supplied tag counts, not only those reachable from HEAD, so a number
    used on another branch is never reused. Tags that do not fit the scheme are
    ignored, as are pre-releases and dev releases when numbering a final tag:
    they occupy no final number. Post-releases do occupy theirs.

    With `pre`, the proposal is the next pre-release of that channel for the
    final release that would otherwise be proposed. Numbering starts at 1 and
    is counted per period, patch and channel, so `rc1` and `a1` do not affect
    each other. Dev releases of a pre-release occupy no number.

    With `promote`, the proposal is the final tag for the latest pre-release
    (in PEP 440 order, any channel) of the release that would otherwise be
    proposed, and `latest_tag` names that pre-release.

    With `post`, the proposal is the next post-release of the latest release in
    the period. This is the one mode that adds to an existing release, so it
    works with `patch = false` and fails only when the period has no release.

    `pre`, `promote` and `post` cannot be combined.
    """
    if sum((pre is not None, promote, post)) > 1:
        raise ValueError("pre, promote and post are mutually exclusive")
    period = _date_parts(today, config)
    occupied: dict[int, str] = {}
    candidates: dict[int, list[tuple[CalverVersion, str]]] = {}
    posts: dict[int, list[tuple[int, str]]] = {}
    for tag in tags:
        parsed = _parse_tag(tag, config)
        if parsed is None:
            continue
        components = _release_components(parsed, config)
        if components is None or components[0] != period:
            continue
        if not parsed.is_prerelease:
            occupied[components[1]] = tag
            if parsed.post is not None:
                posts.setdefault(components[1], []).append((parsed.post, tag))
        elif parsed.dev is None and parsed.pre is not None:
            candidates.setdefault(components[1], []).append((parsed, tag))

    latest_patch = max(occupied, default=None)
    latest_tag = None if latest_patch is None else occupied[latest_patch]

    if post:
        if latest_patch is None:
            raise NextTagError(
                "no_release",
                f"no release exists for {_base(today, config)} to add a "
                "post-release to",
            )
        number, latest_tag = max(posts.get(latest_patch, []), default=(0, latest_tag))
        version = _apply_stability_prefix(
            f"{_base(today, config)}.{latest_patch}.post{number + 1}", config
        )
        reason = (
            NextTagReason.NEXT_POSTRELEASE if number else NextTagReason.NEW_POSTRELEASE
        )
        return NextTag(
            f"{config.tag_prefix}{version}", version, latest_patch, reason, latest_tag
        )

    if latest_patch is None:
        patch, reason = 0, NextTagReason.NEW_PERIOD
    elif config.patch:
        patch, reason = latest_patch + 1, NextTagReason.NEXT_PATCH
    else:
        raise NextTagError(
            "period_already_released",
            f"patch = false allows one release per period and {latest_tag} already "
            f"exists for {_base(today, config)}",
        )

    release = f"{_base(today, config)}.{patch}"
    found = candidates.get(patch, [])
    if pre is not None:
        numbers = [
            (v.pre[1], tag) for v, tag in found if v.pre and v.pre[0] == pre.value
        ]
        number, latest_tag = max(numbers, default=(0, None))
        reason = (
            NextTagReason.NEXT_PRERELEASE if number else NextTagReason.NEW_PRERELEASE
        )
        release = f"{release}{pre.value}{number + 1}"
    elif promote:
        if not found:
            raise NextTagError(
                "no_prerelease",
                f"no pre-release of {release} exists to promote",
            )
        latest_tag = max(found, key=lambda item: item[0])[1]
        reason = NextTagReason.PROMOTION

    version = _apply_stability_prefix(release, config)
    return NextTag(
        f"{config.tag_prefix}{version}", version, patch, reason, latest_tag, pre
    )

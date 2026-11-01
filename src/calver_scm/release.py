from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from calver_scm.parser import _parse_tag, _release_components
from calver_scm.utils import _apply_stability_prefix, _base, _date_parts

if TYPE_CHECKING:
    import datetime
    from collections.abc import Iterable

    from calver_scm.config import CalverConfig


class NextTagReason(StrEnum):
    """Why the next tag has the patch it has."""

    NEW_PERIOD = "new_period"
    NEXT_PATCH = "next_patch"

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


def plan_next_tag(
    tags: Iterable[str], config: CalverConfig, *, today: datetime.date
) -> NextTag:
    """Propose the next clean release tag for the period containing `today`; no I/O.

    Every supplied tag counts, not only those reachable from HEAD, so a number
    used on another branch is never reused. Tags that do not fit the scheme are
    ignored, as are pre-releases and dev releases, which occupy no final number.
    Post-releases do occupy theirs.
    """
    period = _date_parts(today, config)
    occupied: dict[int, str] = {}
    for tag in tags:
        parsed = _parse_tag(tag, config)
        if parsed is None or parsed.is_prerelease:
            continue
        components = _release_components(parsed, config)
        if components is not None and components[0] == period:
            occupied[components[1]] = tag

    latest_patch = max(occupied, default=None)
    latest_tag = None if latest_patch is None else occupied[latest_patch]

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

    version = _apply_stability_prefix(f"{_base(today, config)}.{patch}", config)
    return NextTag(f"{config.tag_prefix}{version}", version, patch, reason, latest_tag)

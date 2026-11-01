from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date


@dataclass(frozen=True, slots=True)
class ScmContext:
    """Immutable snapshot of the SCM state the CalVer engine needs.

    `tag` is the textual tag as setuptools-scm hands it to the version scheme.
    With setuptools-scm 10 that is already prefix-stripped and PEP 440
    normalized (`2026.4.2`), and a repository without tags arrives as `0.0` at
    a positive distance rather than as `None`. `None` remains valid input for
    callers that have no tag at all.

    `distance` is always an integer upstream, so it is not nullable here.
    `dirty` is the SCM dirty flag, not the local-version suffix.
    """

    tag: str | None
    distance: int
    dirty: bool


class ResolutionReason(StrEnum):
    """Which branch of the CalVer algorithm produced the public version."""

    NO_TAG_FALLBACK = "no_tag_fallback"
    INCOMPATIBLE_TAG_FALLBACK = "incompatible_tag_fallback"
    EXACT_TAG = "exact_tag"
    PATCH_INCREMENTED = "patch_incremented"
    PATCH_RESET = "patch_reset"


@dataclass(frozen=True, slots=True)
class VersionResolution:
    """Public version plus the decision path that produced it.

    `public_version` is the version scheme output only; setuptools-scm may
    still append a local suffix, so it can differ from the final build version.
    """

    public_version: str
    reason: ResolutionReason
    scm: ScmContext
    calculation_date: date

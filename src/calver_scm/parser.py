from __future__ import annotations

from typing import TYPE_CHECKING

from packaging.version import InvalidVersion

from calver_scm.calver_version import CalverVersion

if TYPE_CHECKING:
    from calver_scm.config import CalverConfig


def _parse_tag(tag: str, cfg: CalverConfig) -> CalverVersion | None:
    """Parse a tag into a CalverVersion."""
    stripped = tag.removeprefix(cfg.tag_prefix)

    try:
        return CalverVersion(stripped)
    except InvalidVersion:
        return None


def _release_components(
    version: CalverVersion,
    cfg: CalverConfig,
) -> tuple[tuple[int, ...], int] | None:
    """Extract (date parts, patch) from a parsed CalVer version."""
    release = version.release
    date_len = len(cfg.scheme_tokens)

    if len(release) == date_len:
        return release, 0

    if len(release) == date_len + 1:
        return release[:-1], release[-1]

    return None

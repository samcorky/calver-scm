from packaging.version import InvalidVersion

from calver_scm.calver_version import CalverVersion
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
) -> tuple[int, int, int, int] | None:
    """Extract (year, month, day, patch) from a parsed CalVer version."""
    release = version.release

    if cfg.mode == "day":
        if len(release) == 3:
            year, month, day = release
            return year, month, day, 0
        if len(release) == 4:
            year, month, day, patch = release
            return year, month, day, patch
        return None

    if len(release) == 2:
        year, month = release
        return year, month, 0, 0
    if len(release) == 3:
        year, month, patch = release
        return year, month, 0, patch
    return None

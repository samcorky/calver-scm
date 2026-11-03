from __future__ import annotations

from typing import TYPE_CHECKING

from packaging.version import InvalidVersion

from calver_scm.calver_version import CalverVersion

if TYPE_CHECKING:
    from calver_scm.config import CalverConfig


def _parse_tag(tag: str, cfg: CalverConfig) -> CalverVersion | None:
    """Parse a tag into a CalverVersion."""
    return _parse_tag_or_reason(tag, cfg)[0]


def _parse_tag_or_reason(
    tag: str, cfg: CalverConfig
) -> tuple[CalverVersion | None, str | None]:
    """Parse a tag, or say in a sentence why it cannot be parsed."""
    stripped = tag.removeprefix(cfg.tag_prefix)

    try:
        parsed = CalverVersion(stripped)
    except InvalidVersion:
        return None, "not a valid PEP 440 version"

    if _has_misplaced_stability_prefix(stripped, parsed, cfg):
        return (
            None,
            "starts with '0.', which marks an unstable version, but stable = true",
        )

    return parsed, None


def _has_misplaced_stability_prefix(
    stripped: str,
    version: CalverVersion,
    cfg: CalverConfig,
) -> bool:
    """Reject clearly unstable-prefixed tags when stable output is configured."""
    if not cfg.stable or not stripped.startswith("0."):
        return False

    first_token = cfg.scheme_tokens[0]
    if first_token != "YY":
        return True

    return len(version.release) > len(cfg.scheme_tokens) + 1


def _release_components(
    version: CalverVersion,
    cfg: CalverConfig,
) -> tuple[tuple[int, ...], int] | None:
    """Extract (date parts, patch) from a parsed CalVer version."""
    release = version.release
    if not cfg.stable and release and release[0] == 0:
        release = release[1:]
    date_len = len(cfg.scheme_tokens)

    if len(release) == date_len:
        return release, 0

    if len(release) == date_len + 1:
        return release[:-1], release[-1]

    return None

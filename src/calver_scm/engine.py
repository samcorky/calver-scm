from __future__ import annotations

from typing import TYPE_CHECKING

from calver_scm.models import ResolutionReason, ScmContext, VersionResolution
from calver_scm.parser import _parse_tag, _release_components
from calver_scm.utils import (
    _apply_stability_prefix,
    _base,
    _fallback_version,
    _format_date_parts,
    _format_dev_version,
    _is_same_period,
)

if TYPE_CHECKING:
    import datetime

    from calver_scm.config import CalverConfig


def resolve_version(
    scm: ScmContext,
    config: CalverConfig,
    *,
    today: datetime.date,
) -> VersionResolution:
    """Compute the CalVer public version and how it was derived; no I/O."""
    base = _base(today, config)

    def resolution(version: str, reason: ResolutionReason) -> VersionResolution:
        return VersionResolution(
            public_version=_apply_stability_prefix(version, config),
            reason=reason,
            scm=scm,
            calculation_date=today,
        )

    def fallback(reason: ResolutionReason) -> VersionResolution:
        return resolution(
            _fallback_version(
                base=base,
                distance=scm.distance,
                fallback=config.fallback,
                no_dev=config.no_dev,
            ),
            reason,
        )

    if scm.tag is None:
        return fallback(ResolutionReason.NO_TAG_FALLBACK)

    parsed = _parse_tag(scm.tag, config)
    components = None if parsed is None else _release_components(parsed, config)
    if parsed is None or components is None:
        return fallback(ResolutionReason.INCOMPATIBLE_TAG_FALLBACK)

    tag_date_parts, tag_patch = components

    if scm.distance == 0 and not scm.dirty:
        tag_base = _format_date_parts(tag_date_parts, config)
        return resolution(
            parsed.format_from_base(base=tag_base, patch=tag_patch),
            ResolutionReason.EXACT_TAG,
        )

    if _is_same_period(today, tag_date_parts, config) and config.patch:
        patch, reason = tag_patch + 1, ResolutionReason.PATCH_INCREMENTED
    else:
        patch, reason = 0, ResolutionReason.PATCH_RESET

    return resolution(
        _format_dev_version(
            base=base, patch=patch, distance=scm.distance, no_dev=config.no_dev
        ),
        reason,
    )

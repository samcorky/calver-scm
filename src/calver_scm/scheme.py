from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from calver_scm.config import _load_calver_config
from calver_scm.parser import _parse_tag, _release_components
from calver_scm.utils import (
    _apply_stability_prefix,
    _base,
    _fallback_version,
    _format_date_parts,
    _is_same_period,
    _today_in_timezone,
)

if TYPE_CHECKING:
    from setuptools_scm.version import ScmVersion


def calver_scm(version: ScmVersion) -> str:
    """Return a CalVer version string derived from SCM state."""
    root = Path(getattr(version.config, "root", None) or ".").resolve()
    cfg = _load_calver_config(root)
    today = _today_in_timezone(cfg.timezone)
    base = _base(today, cfg)

    if version.tag is None:
        return _apply_stability_prefix(
            _fallback_version(
                base=base,
                distance=version.distance,
                fallback=cfg.fallback
            ),
            cfg,
        )

    parsed = _parse_tag(str(version.tag), cfg)

    if parsed is None:
        return _apply_stability_prefix(
            _fallback_version(
                base=base,
                distance=version.distance,
                fallback=cfg.fallback
            ),
            cfg,
        )

    components = _release_components(parsed, cfg)

    if components is None:
        return _apply_stability_prefix(
            _fallback_version(
                base=base,
                distance=version.distance,
                fallback=cfg.fallback
            ),
            cfg,
        )

    tag_date_parts, tag_patch = components

    if version.distance == 0 and not version.dirty:
        tag_base = _format_date_parts(tag_date_parts, cfg)
        return _apply_stability_prefix(
            parsed.format_from_base(base=tag_base, patch=tag_patch),
            cfg,
        )

    same_period = _is_same_period(today, tag_date_parts, cfg)
    patch = (tag_patch + 1) if same_period and cfg.patch else 0

    return _apply_stability_prefix(f"{base}.{patch}.dev{version.distance}", cfg)

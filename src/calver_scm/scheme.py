import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from calver_scm.config import _load_calver_config
from calver_scm.parser import _parse_tag, _release_components
from calver_scm.utils import _base, _is_same_period

if TYPE_CHECKING:
    from setuptools_scm.version import ScmVersion



def calver_scm(version: ScmVersion) -> str:
    """Return a CalVer version string derived from SCM state."""
    root = Path(getattr(version.config, "root", None) or ".").resolve()
    cfg = _load_calver_config(root)
    today = datetime.date.today()
    base = _base(today, cfg)

    if version.tag is None:
        if cfg.fallback == "date":
            return f"{base}.0"
        return f"{base}.0.dev{version.distance}"

    parsed = _parse_tag(str(version.tag), cfg)

    if parsed is None:
        if cfg.fallback == "date":
            return f"{base}.0"
        return f"{base}.0.dev{version.distance}"

    components = _release_components(parsed, cfg)

    if components is None:
        if cfg.fallback == "date":
            return f"{base}.0"
        return f"{base}.0.dev{version.distance}"

    tag_year, tag_month, tag_day, tag_patch = components

    if version.distance == 0 and not version.dirty:
        return parsed.format(mode=cfg.mode)

    same_period = _is_same_period(today, tag_year, tag_month, tag_day, cfg)
    patch = (tag_patch + 1) if same_period and cfg.patch else 0

    return f"{base}.{patch}.dev{version.distance}"

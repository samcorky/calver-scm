from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from calver_scm.config import _load_calver_config
from calver_scm.engine import resolve_version
from calver_scm.models import ScmContext
from calver_scm.utils import _today_in_timezone

if TYPE_CHECKING:
    from setuptools_scm.version import ScmVersion

    from calver_scm.config import CalverConfig
    from calver_scm.models import VersionResolution


def _resolve_project_root(version: ScmVersion) -> Path:
    """Resolve the project-local directory used for config lookup."""
    config = version.config
    absolute_root: Path | None = getattr(config, "absolute_root", None)
    project_path: Path | None = getattr(config, "project_path", None)
    if absolute_root is not None and project_path is not None:
        return (Path(absolute_root) / Path(project_path)).resolve()

    root = getattr(config, "root", None) if config is not None else None
    return Path(root or ".").resolve()


def _scm_context(version: ScmVersion) -> ScmContext:
    """Convert a setuptools-scm version into the engine's input snapshot."""
    return ScmContext(
        tag=None if version.tag is None else str(version.tag),
        distance=version.distance,
        dirty=version.dirty,
    )


def resolve_scm_version(version: ScmVersion) -> tuple[VersionResolution, CalverConfig]:
    """Resolve the public version for a setuptools-scm version, with its config."""
    cfg = _load_calver_config(_resolve_project_root(version))
    today = _today_in_timezone(cfg.timezone)
    return resolve_version(_scm_context(version), cfg, today=today), cfg


def calver_scm(version: ScmVersion) -> str:
    """Return a CalVer version string derived from SCM state."""
    return resolve_scm_version(version)[0].public_version

from __future__ import annotations

import os
import subprocess
import tomllib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from setuptools_scm import get_version

from calver_scm.calver_version import CalverVersion
from calver_scm.scheme import resolve_scm_version

if TYPE_CHECKING:
    from pathlib import Path

    from setuptools_scm.version import ScmVersion

    from calver_scm.config import CalverConfig
    from calver_scm.models import VersionResolution

SCHEME_NAME = "calver-scm"

# Options that make setuptools-scm write files; resolving a version must not.
_WRITE_OPTIONS = frozenset(
    {"write_to", "write_to_template", "version_file", "version_file_template"}
)


class ResolutionError(Exception):
    """Raised when the build version cannot be resolved for a project."""


@dataclass(frozen=True, slots=True)
class BuildExplanation:
    """The full build version together with how the CalVer scheme produced it."""

    version: str
    resolution: VersionResolution
    config: CalverConfig
    env_overrides: tuple[tuple[str, str], ...]

    @property
    def local_segment(self) -> str | None:
        """The local version segment, if any, of the full build version."""
        return CalverVersion(self.version).local


def resolve_build_version(root: Path) -> str:
    """Return the full version the project's build backend would produce.

    Settings are read from the project's own configuration and handed to
    setuptools-scm's public `get_version`, exactly as the supported build
    integrations (setuptools and Hatch-VCS) do.
    """
    return _get_version(_checked_options(root))


def explain_build_version(root: Path) -> BuildExplanation:
    """Resolve the build version and capture how the CalVer scheme derived it.

    The scheme callback is wrapped, not re-implemented: setuptools-scm runs the
    same `resolve_scm_version` path as a real build and the result is recorded.
    """
    options = _checked_options(root)
    captured: list[tuple[VersionResolution, CalverConfig]] = []

    def capturing_scheme(version: ScmVersion) -> str:
        resolution, config = resolve_scm_version(version)
        captured.append((resolution, config))
        return resolution.public_version

    options["version_scheme"] = capturing_scheme
    full_version = _get_version(options)
    if not captured:
        raise ResolutionError(
            "setuptools-scm did not call the calver-scm version scheme; a pretend "
            "version override such as SETUPTOOLS_SCM_PRETEND_VERSION may be set"
        )
    resolution, config = captured[-1]
    overrides = tuple(
        sorted((k, v) for k, v in os.environ.items() if k.startswith("CALVER_SCM_"))
    )
    return BuildExplanation(full_version, resolution, config, overrides)


def _checked_options(root: Path) -> dict[str, Any]:
    """Read the project's setuptools-scm settings and require the CalVer scheme."""
    project_root = root.resolve()
    pyproject = project_root / "pyproject.toml"
    try:
        with pyproject.open("rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError as e:
        raise ResolutionError(f"No pyproject.toml found in {project_root}") from e
    except tomllib.TOMLDecodeError as e:
        raise ResolutionError(f"Invalid TOML in {pyproject}: {e}") from e

    options = _build_options(data, project_root, pyproject)
    scheme = options.get("version_scheme")
    if scheme != SCHEME_NAME:
        raise ResolutionError(
            f"{pyproject} configures version_scheme={scheme!r}, not {SCHEME_NAME!r}; "
            f"set version_scheme = {SCHEME_NAME!r} in the build integration settings"
        )

    for key in _WRITE_OPTIONS:
        options.pop(key, None)
    return options


def _get_version(options: dict[str, Any]) -> str:
    try:
        return get_version(**options)
    except LookupError as e:
        raise ResolutionError(f"setuptools-scm could not resolve a version: {e}") from e
    except RuntimeError as e:
        # The version scheme raises RuntimeError for an invalid CalVer configuration.
        raise ResolutionError(str(e)) from e


def _build_options(
    data: dict[str, Any], project_root: Path, pyproject: Path
) -> dict[str, Any]:
    """Translate the project's build settings into `get_version` keywords."""
    tool: dict[str, Any] = data.get("tool", {})

    if "setuptools_scm" in tool:
        options = _normalise_keys(tool["setuptools_scm"])
        options.setdefault("root", ".")
        options["relative_to"] = pyproject
        name = data.get("project", {}).get("name")
        if name is not None:
            options.setdefault("dist_name", name)
        return options

    hatch_version: dict[str, Any] = tool.get("hatch", {}).get("version", {})
    if hatch_version.get("source") == "vcs":
        options = _normalise_keys(hatch_version.get("raw-options", {}))
        # hatch-vcs hands root to setuptools-scm unchanged, which resolves it
        # against the working directory; builds run from the project directory.
        options["root"] = str((project_root / options.get("root", ".")).resolve())
        if tag_pattern := hatch_version.get("tag-pattern"):
            options["tag_regex"] = tag_pattern
        if fallback := hatch_version.get("fallback-version"):
            options["fallback_version"] = fallback
        return options

    raise ResolutionError(
        f"No setuptools-scm configuration found in {pyproject}: expected "
        "[tool.setuptools_scm] or [tool.hatch.version] with source = 'vcs'"
    )


def _normalise_keys(table: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with hyphenated keys converted to keyword names."""
    return {key.replace("-", "_"): value for key, value in table.items()}


def is_shallow_repository(project: Path) -> bool:
    """Whether the repository containing `project` is a shallow clone."""
    result = subprocess.run(
        ["git", "rev-parse", "--is-shallow-repository"],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def list_local_tags(project: Path) -> list[str]:
    """Return every tag known to the local repository containing `project`."""
    result = subprocess.run(
        ["git", "tag", "--list"],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ResolutionError(f"Could not list Git tags: {result.stderr.strip()}")
    return result.stdout.splitlines()


def commits_since(project: Path, tag: str) -> int | None:
    """Count the commits HEAD has beyond `tag`, or `None` if `tag` is not behind it."""
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", f"refs/tags/{tag}", "HEAD"],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    if ancestor.returncode == 1:
        return None
    count = subprocess.run(
        ["git", "rev-list", "--count", f"refs/tags/{tag}..HEAD"],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    if ancestor.returncode != 0 or count.returncode != 0:
        raise ResolutionError(
            f"Could not compare {tag} with HEAD: "
            f"{(ancestor.stderr or count.stderr).strip()}"
        )
    return int(count.stdout)

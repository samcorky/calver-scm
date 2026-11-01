from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING, Any

from setuptools_scm import get_version

if TYPE_CHECKING:
    from pathlib import Path

SCHEME_NAME = "calver-scm"

# Options that make setuptools-scm write files; resolving a version must not.
_WRITE_OPTIONS = frozenset(
    {"write_to", "write_to_template", "version_file", "version_file_template"}
)


class ResolutionError(Exception):
    """Raised when the build version cannot be resolved for a project."""


def resolve_build_version(root: Path) -> str:
    """Return the full version the project's build backend would produce.

    Settings are read from the project's own configuration and handed to
    setuptools-scm's public `get_version`, exactly as the supported build
    integrations (setuptools and Hatch-VCS) do.
    """
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

    try:
        return get_version(**options)
    except LookupError as e:
        raise ResolutionError(f"setuptools-scm could not resolve a version: {e}") from e


def _build_options(
    data: dict[str, Any], project_root: Path, pyproject: Path
) -> dict[str, Any]:
    """Translate the project's build settings into `get_version` keywords."""
    tool: dict[str, Any] = data.get("tool", {})

    if "setuptools_scm" in tool:
        options = _normalize_keys(tool["setuptools_scm"])
        options.setdefault("root", ".")
        options["relative_to"] = pyproject
        name = data.get("project", {}).get("name")
        if name is not None:
            options.setdefault("dist_name", name)
        return options

    hatch_version: dict[str, Any] = tool.get("hatch", {}).get("version", {})
    if hatch_version.get("source") == "vcs":
        options = _normalize_keys(hatch_version.get("raw-options", {}))
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


def _normalize_keys(table: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with hyphenated keys converted to keyword names."""
    return {key.replace("-", "_"): value for key, value in table.items()}

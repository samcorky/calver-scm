"""The CLI must report what the real build backends would produce."""

from __future__ import annotations

import contextlib
import re
import subprocess
import sys
from typing import TYPE_CHECKING, Any

import pytest
from hatchling.metadata.core import ProjectMetadata
from hatchling.plugin.manager import PluginManager

from calver_scm.cli_support import resolve_build_version

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

pytestmark = pytest.mark.e2e

TIMESTAMP = re.compile(r"\d{14}")


def mask_timestamp(version: str) -> str:
    """Hide node-and-timestamp's clock reading, which a subprocess cannot share."""
    return TIMESTAMP.sub("<timestamp>", version)


HEADER = '[project]\nname = "demo"\ndynamic = ["version"]\n'


def setuptools_pyproject(local_scheme: str, root: str | None = None) -> str:
    root_line = f'root = "{root}"\n' if root else ""
    return (
        f"{HEADER}[tool.setuptools_scm]\n"
        f'version_scheme = "calver-scm"\nlocal_scheme = "{local_scheme}"\n{root_line}'
    )


def hatch_pyproject(local_scheme: str, root: str | None = None) -> str:
    root_line = f'root = "{root}"\n' if root else ""
    return (
        f'[build-system]\nrequires = ["hatchling", "hatch-vcs"]\n'
        f'build-backend = "hatchling.build"\n{HEADER}'
        '[tool.hatch.version]\nsource = "vcs"\n[tool.hatch.version.raw-options]\n'
        f'version_scheme = "calver-scm"\nlocal_scheme = "{local_scheme}"\n{root_line}'
    )


def setuptools_build_version(project: Path) -> str:
    """Ask setuptools itself, with the setuptools-scm integration active."""
    result = subprocess.run(
        [sys.executable, "-c", "import setuptools; setuptools.setup()", "--version"],
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip().splitlines()[-1]


def hatch_build_version(project: Path) -> str:
    """Ask Hatchling itself, with the hatch-vcs version source active."""
    with contextlib.chdir(project):
        return ProjectMetadata(str(project), PluginManager()).version


SCENARIOS: dict[str, dict[str, Any]] = {
    "no-tag": {},
    "exact-tag": {"tag": "v2020.01.3"},
    "ahead-of-tag": {"tag": "v2020.01.3", "commits_after_tag": 2},
    "dirty-at-tag": {"tag": "v2020.01.3", "dirty": True},
    "dirty-ahead": {"tag": "v2020.01.3", "commits_after_tag": 1, "dirty": True},
}


@pytest.mark.parametrize("scenario", SCENARIOS)
@pytest.mark.parametrize(
    "local_scheme", ["no-local-version", "node-and-date", "node-and-timestamp"]
)
@pytest.mark.parametrize(
    ("make_pyproject", "build_version"),
    [
        pytest.param(setuptools_pyproject, setuptools_build_version, id="setuptools"),
        pytest.param(hatch_pyproject, hatch_build_version, id="hatch-vcs"),
    ],
)
def test_cli_matches_build_backend(
    make_git_project: Callable[..., Path],
    make_pyproject: Callable[..., str],
    build_version: Callable[[Path], str],
    local_scheme: str,
    scenario: str,
) -> None:
    """Resolve the same version as the build backend for each repository state."""
    project = make_git_project(make_pyproject(local_scheme), **SCENARIOS[scenario])
    expected = build_version(project)
    assert mask_timestamp(resolve_build_version(project)) == mask_timestamp(expected)


@pytest.mark.parametrize(
    ("make_pyproject", "build_version"),
    [
        pytest.param(setuptools_pyproject, setuptools_build_version, id="setuptools"),
        pytest.param(hatch_pyproject, hatch_build_version, id="hatch-vcs"),
    ],
)
def test_cli_matches_build_backend_in_a_subproject(
    make_git_project: Callable[..., Path],
    make_pyproject: Callable[..., str],
    build_version: Callable[[Path], str],
) -> None:
    """Resolve a project below the repository root using its configured root."""
    project = make_git_project(
        make_pyproject("no-local-version", root="../.."),
        tag="v2020.01.3",
        commits_after_tag=2,
        subdir="packages/demo",
    )
    assert resolve_build_version(project) == build_version(project)


@pytest.mark.parametrize(
    ("make_pyproject", "build_version"),
    [
        pytest.param(setuptools_pyproject, setuptools_build_version, id="setuptools"),
        pytest.param(hatch_pyproject, hatch_build_version, id="hatch-vcs"),
    ],
)
def test_cli_honours_calver_environment_overrides(
    make_git_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
    make_pyproject: Callable[..., str],
    build_version: Callable[[Path], str],
) -> None:
    """Apply CALVER_SCM_* overrides exactly as the build does."""
    monkeypatch.setenv("CALVER_SCM_NO_DEV", "true")
    project = make_git_project(
        make_pyproject("no-local-version"), tag="v2020.01.3", commits_after_tag=2
    )
    version = resolve_build_version(project)
    assert version == build_version(project)
    assert ".dev" not in version

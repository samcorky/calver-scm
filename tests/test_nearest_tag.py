from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Any

import pytest

from calver_scm.cli_support import nearest_build_tag, scopes_build_tags

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

PYPROJECT = '[project]\nname = "demo"\n'


def git(project: Path, *args: str) -> None:
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.com",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "tag.gpgsign=false",
            *args,
        ],
        cwd=project,
        check=True,
        capture_output=True,
    )


@pytest.mark.e2e
def test_nearest_tag_is_the_closest_one_of_any_name(
    make_git_project: Callable[..., Path],
) -> None:
    """Read the tag setuptools-scm would pick, whatever its prefix."""
    project = make_git_project(PYPROJECT, tag="api-v2026.11.1")
    (project / "x.txt").write_text("x", encoding="utf-8")
    git(project, "add", ".")
    git(project, "commit", "-q", "-m", "more")
    git(project, "tag", "web-v2026.11.3")
    assert nearest_build_tag(project) == "web-v2026.11.3"


@pytest.mark.e2e
def test_nearest_tag_ignores_tags_without_a_digit(
    make_git_project: Callable[..., Path],
) -> None:
    """Match setuptools-scm's default glob, which needs a digit."""
    project = make_git_project(PYPROJECT, tag="v2026.4.0")
    (project / "x.txt").write_text("x", encoding="utf-8")
    git(project, "add", ".")
    git(project, "commit", "-q", "-m", "more")
    git(project, "tag", "latest")
    assert nearest_build_tag(project) == "v2026.4.0"


@pytest.mark.e2e
def test_nearest_tag_is_none_without_tags(
    make_git_project: Callable[..., Path], tmp_path: Path
) -> None:
    assert nearest_build_tag(make_git_project(PYPROJECT)) is None
    assert nearest_build_tag(tmp_path) is None


@pytest.mark.unit
@pytest.mark.parametrize(
    ("options", "expected"),
    [
        ({}, False),
        ({"scm": {"git": {}}}, False),
        ({"scm": {"git": {"describe_command": "git describe"}}}, True),
        ({"git_describe_command": "git describe"}, True),
    ],
)
def test_scopes_build_tags(options: dict[str, Any], expected: bool) -> None:
    """Recognise every way a project can narrow which tags the build reads."""
    assert scopes_build_tags(options) is expected

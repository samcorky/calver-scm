from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

from calver_scm.cli import main

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

pytestmark = pytest.mark.e2e

SETUPTOOLS = """
[project]
name = "api"
dynamic = ["version"]
[tool.setuptools_scm]
version_scheme = "calver-scm"
local_scheme = "no-local-version"
{tag}
[tool.calver-scm]
tag_prefix = "api-v"
"""

HATCH = """
[project]
name = "api"
dynamic = ["version"]
[tool.hatch.version]
source = "vcs"
raw-options = {{ version_scheme = "calver-scm", {tag},
  local_scheme = "no-local-version" }}
[tool.calver-scm]
tag_prefix = "api-v"
"""


def two_packages(make_git_project: Callable[..., Path], pyproject: str) -> Path:
    """api tagged first, then a later commit tagged for web."""
    project = make_git_project(pyproject, tag="api-v2026.11.1")
    (project / "more.txt").write_text("more", encoding="utf-8")
    for args in (
        ["add", "."],
        ["commit", "-q", "-m", "more"],
        ["tag", "web-v2026.11.3"],
    ):
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=t",
                "-c",
                "user.email=t@e.com",
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
    return project


def version(capsys: pytest.CaptureFixture[str], root: Path) -> tuple[int, str, str]:
    code = main(["--format", "plain", "version", "-r", str(root)])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_tag_prefix_scopes_the_cli_like_the_build(
    make_git_project: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """Read api's own tag, not web's, as the build does with tag.prefix."""
    project = two_packages(
        make_git_project,
        SETUPTOOLS.format(tag='[tool.setuptools_scm.tag]\nprefix = "api-v"'),
    )
    code, out, _ = version(capsys, project)
    assert (code, out) == (0, "2026.11.2.dev1\n")


def test_tag_prefix_in_hatch_raw_options(
    make_git_project: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    project = two_packages(
        make_git_project, HATCH.format(tag='tag = { prefix = "api-v" }')
    )
    code, out, _ = version(capsys, project)
    assert (code, out) == (0, "2026.11.2.dev1\n")


def test_unsupported_tag_setting_is_a_clear_error(
    make_git_project: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """Refuse a tag key the CLI cannot honour rather than crash or ignore it."""
    project = two_packages(
        make_git_project,
        SETUPTOOLS.format(tag="[tool.setuptools_scm.tag]\nstrict = true"),
    )
    code, out, err = version(capsys, project)
    assert (code, out) == (2, "")
    assert err.startswith("error:")
    assert "tag.strict" in err
    assert "Traceback" not in err


def test_tag_regex_is_passed_on(
    make_git_project: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """Honour tag.regex as tag_regex."""
    project = make_git_project(
        SETUPTOOLS.format(
            tag='[tool.setuptools_scm.tag]\nregex = "^api-v(?P<version>.*)$"'
        ),
        tag="api-v2026.11.1",
    )
    assert version(capsys, project)[:2] == (0, "2026.11.1\n")


def test_own_describe_command_beats_tag_prefix(
    make_git_project: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """Keep a describe command the project set, as setuptools-scm does."""
    tag = (
        '[tool.setuptools_scm.tag]\nprefix = "web-v"\n'
        "[tool.setuptools_scm.scm.git]\n"
        'describe_command = "git describe --dirty --tags --long --match api-v*"'
    )
    project = two_packages(make_git_project, SETUPTOOLS.format(tag=tag))
    assert version(capsys, project)[:2] == (0, "2026.11.2.dev1\n")

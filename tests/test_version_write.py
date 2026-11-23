from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

import pytest

from calver_scm.cli import main

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

pytestmark = pytest.mark.e2e

SETUPTOOLS = """
[project]
name = "demo"
dynamic = ["version"]
[tool.setuptools_scm]
version_scheme = "calver-scm"
local_scheme = "no-local-version"
"""


@pytest.fixture
def project(make_git_project: Callable[..., Path]) -> Path:
    """A clean project released at v2026.04.2, which builds as 2026.4.2."""
    return make_git_project(SETUPTOOLS, tag="v2026.04.2")


def run(
    capsys: pytest.CaptureFixture[str], root: Path, *args: str
) -> tuple[int, str, str]:
    code = main(["--format", "plain", "version", *args, "-r", str(root)])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_write_python_module(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Write a module a package can import, and still print the version."""
    (project / "src").mkdir()
    code, out, err = run(capsys, project, "--write", "src/_version.py")
    assert (code, out) == (0, "2026.4.2\n")
    assert err == "wrote src/_version.py\n"
    text = (project / "src" / "_version.py").read_text(encoding="utf-8")
    assert "__version__ = version = '2026.4.2'" in text
    assert '__all__ = ["__version__", "version"]' in text
    namespace: dict[str, object] = {}
    exec(compile(text, "_version.py", "exec"), namespace)
    assert namespace["__version__"] == namespace["version"] == "2026.4.2"


def test_write_plain_text_for_any_other_extension(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Write just the version and a newline, for Docker builds and scripts."""
    for name in ("VERSION", "version.txt"):
        code, _, _ = run(capsys, project, "--write", name)
        assert code == 0
        assert (project / name).read_text(encoding="utf-8") == "2026.4.2\n"


def test_write_replaces_older_content(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Overwrite a previous version rather than append to it."""
    (project / "VERSION").write_text("1.0\nold\n", encoding="utf-8")
    assert run(capsys, project, "--write", "VERSION")[0] == 0
    assert (project / "VERSION").read_text(encoding="utf-8") == "2026.4.2\n"


def test_unchanged_file_is_left_alone(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Do not touch the file when it already holds the version, so builds stay quiet."""
    target = project / "VERSION"
    assert run(capsys, project, "--write", "VERSION")[0] == 0
    before = target.stat().st_mtime_ns
    code, out, err = run(capsys, project, "--write", "VERSION")
    assert (code, out) == (0, "2026.4.2\n")
    assert err == "unchanged VERSION\n"
    assert target.stat().st_mtime_ns == before


def test_write_is_atomic_and_leaves_no_temporary_files(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Replace the file in one step so a reader never sees half a version."""
    before = {p.name for p in project.iterdir()}
    assert run(capsys, project, "--write", "VERSION")[0] == 0
    assert {p.name for p in project.iterdir()} == before | {"VERSION"}


def test_dry_run_shows_the_content_and_writes_nothing(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Let a user see what would be written first."""
    code, out, err = run(capsys, project, "--write", "VERSION", "--dry-run")
    assert (code, out) == (0, "2026.4.2\n")
    assert err == "would write VERSION:\n2026.4.2\n"
    assert not (project / "VERSION").exists()


def test_dry_run_says_when_nothing_would_change(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Report an up to date file as unchanged even when not writing."""
    (project / "VERSION").write_text("2026.4.2\n", encoding="utf-8")
    code, _, err = run(capsys, project, "--write", "VERSION", "--dry-run")
    assert (code, err) == (0, "unchanged VERSION\n")


def test_dry_run_needs_write(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Refuse a flag that would do nothing."""
    code, out, err = run(capsys, project, "--dry-run")
    assert (code, out) == (2, "")
    assert "--dry-run needs --write" in err


@pytest.mark.parametrize("target", ["../escape.txt", "sub/../../escape.txt"])
def test_write_outside_the_project_root_is_refused(
    project: Path, capsys: pytest.CaptureFixture[str], target: str
) -> None:
    """Never write outside the project, however the path is spelled."""
    (project / "sub").mkdir()
    code, out, err = run(capsys, project, "--write", target)
    assert (code, out) == (2, "")
    assert "outside the project" in err
    assert not (project.parent / "escape.txt").exists()


def test_absolute_path_outside_the_root_is_refused(
    project: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An absolute path is judged the same as a relative one."""
    outside = tmp_path / "elsewhere.txt"
    code, _, err = run(capsys, project, "--write", str(outside))
    assert code == 2
    assert "outside the project" in err
    assert not outside.exists()


def test_absolute_path_inside_the_root_is_allowed(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Accept an absolute path that is within the project."""
    code, _, err = run(capsys, project, "--write", str(project / "VERSION"))
    assert code == 0
    assert err == "wrote VERSION\n"


def test_symlink_pointing_outside_the_root_is_refused(
    project: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Follow symlinks before judging the path, so a link cannot escape."""
    outside = tmp_path / "target.txt"
    (project / "link.txt").symlink_to(outside)
    code, _, err = run(capsys, project, "--write", "link.txt")
    assert code == 2
    assert "outside the project" in err
    assert not outside.exists()


def test_missing_directory_is_a_usage_error(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Do not invent directories; say which one is missing."""
    code, out, err = run(capsys, project, "--write", "nope/_version.py")
    assert (code, out) == (2, "")
    assert "directory does not exist" in err


def test_unwritable_target_is_a_usage_error(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Report an operating system failure as an error, not a traceback."""
    (project / "VERSION").mkdir()
    code, out, err = run(capsys, project, "--write", "VERSION")
    assert (code, out) == (2, "")
    assert err.startswith("error: cannot write VERSION")


def test_a_failed_write_leaves_the_old_file_and_no_temporary_files(
    project: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep the previous content when the replace step fails."""
    (project / "VERSION").write_text("old\n", encoding="utf-8")

    def broken(*_: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", broken)
    before = {p.name for p in project.iterdir()}
    code, _, err = run(capsys, project, "--write", "VERSION")
    assert code == 2
    assert "disk full" in err
    assert (project / "VERSION").read_text(encoding="utf-8") == "old\n"
    assert {p.name for p in project.iterdir()} == before


def test_nothing_is_written_when_the_version_cannot_be_resolved(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Skip the write when resolution fails, so a stale file is not blessed."""
    (tmp_path / "pyproject.toml").write_text(SETUPTOOLS, encoding="utf-8")
    code, out, err = run(capsys, tmp_path, "--write", "VERSION")
    assert (code, out) == (2, "")
    assert err.startswith("error:")
    assert "--write" not in err
    assert not (tmp_path / "VERSION").exists()


def test_json_stdout_is_unchanged_by_write(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Keep stdout to the result; the notes go to stderr."""
    code = main(["--json", "version", "--write", "VERSION", "-r", str(project)])
    captured = capsys.readouterr()
    assert code == 0
    assert json.loads(captured.out) == {"version": "2026.4.2"}
    assert captured.err == "wrote VERSION\n"

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest
import time_machine

from calver_scm.cli import main
from calver_scm.cli_output import _github_entry, _github_value

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

import datetime as dt

APRIL = dt.datetime(2026, 4, 15, 12, tzinfo=dt.UTC)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("value", "text"),
    [(None, ""), (True, "true"), (False, "false"), (3, "3"), ("v1", "v1")],
)
def test_github_value(value: object, text: str) -> None:
    """Render scalars the way Actions expressions compare them."""
    assert _github_value(value) == text


@pytest.mark.unit
def test_github_entry_is_a_plain_assignment_for_one_line() -> None:
    """Keep the common case in the simple key=value form."""
    assert _github_entry("tag", "v2026.4.0") == "tag=v2026.4.0\n"


@pytest.mark.unit
@pytest.mark.parametrize("value", ["a\nb=injected", "a\rb"])
def test_github_entry_guards_multiline_values(value: str) -> None:
    """Fence a value that could otherwise end its entry and add another."""
    entry = _github_entry("input", value)
    first, *_, last = entry.splitlines()
    delimiter = first.removeprefix("input<<")
    assert delimiter.startswith("ghadelimiter_")
    assert last == delimiter
    assert entry.count(delimiter) == 2
    assert not entry.startswith("input=")


def git(project: Path, *args: str) -> None:
    identity = ["-c", "user.name=test", "-c", "user.email=test@example.com"]
    subprocess.run(
        [
            "git",
            *identity,
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


@pytest.fixture
def repo(make_git_project: Callable[..., Path]) -> Path:
    """A repository released at v2026.04.2."""
    return make_git_project('[tool.calver-scm]\nmode = "month"\n', tag="v2026.04.2")


@pytest.fixture
def github_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point $GITHUB_OUTPUT at a temporary file, as Actions does."""
    path = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(path))
    return path


@pytest.mark.e2e
def test_next_tag_appends_its_outputs_and_still_prints_the_tag(
    repo: Path, github_output: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Write every scalar result for later steps, and keep the log readable."""
    github_output.write_text("earlier=1\n", encoding="utf-8")
    with time_machine.travel(APRIL, tick=False):
        assert main(["--format", "github", "next-tag", "-r", str(repo)]) == 0
    assert capsys.readouterr().out == "v2026.4.3\n"
    assert github_output.read_text(encoding="utf-8").splitlines() == [
        "earlier=1",
        "tag=v2026.4.3",
        "version=2026.4.3",
        "patch=3",
        "reason=next_patch",
        "latest_tag=v2026.04.2",
        "is_prerelease=false",
        "channel=",
    ]


@pytest.mark.e2e
def test_next_tag_pre_reports_the_channel(
    repo: Path, github_output: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Expose is_prerelease and channel so a workflow can mark a pre-release."""
    with time_machine.travel(APRIL, tick=False):
        assert main(["-f", "github", "next-tag", "--pre", "rc", "-r", str(repo)]) == 0
    lines = github_output.read_text(encoding="utf-8").splitlines()
    assert "tag=v2026.4.3rc1" in lines
    assert "is_prerelease=true" in lines
    assert "channel=rc" in lines


@pytest.mark.e2e
def test_version_writes_its_version(
    repo: Path, github_output: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Support the other flat command that CI reads."""
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "demo"\ndynamic = ["version"]\n'
        '[tool.setuptools_scm]\nversion_scheme = "calver-scm"\n'
        'local_scheme = "no-local-version"\n',
        encoding="utf-8",
    )
    assert main(["--format", "github", "version", "-r", str(repo)]) == 0
    printed = capsys.readouterr().out.strip()
    assert github_output.read_text(encoding="utf-8") == f"version={printed}\n"


@pytest.mark.e2e
def test_validate_writes_the_verdict_even_when_invalid(
    tmp_path: Path, github_output: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Record valid=false for a later step, while still exiting 1."""
    assert (
        main(["--format", "github", "validate", "2026.13.1", "-r", str(tmp_path)]) == 1
    )
    assert github_output.read_text(encoding="utf-8").splitlines() == [
        "valid=false",
        "input=2026.13.1",
    ]
    assert "invalid_month" in capsys.readouterr().out


@pytest.mark.e2e
def test_validate_writes_the_kind_of_a_valid_tag(
    tmp_path: Path, github_output: Path
) -> None:
    """Let a later step set the release's pre-release flag from the tag alone."""
    assert (
        main(["--format", "github", "validate", "2026.4.2rc1", "-r", str(tmp_path)])
        == 0
    )
    assert github_output.read_text(encoding="utf-8").splitlines() == [
        "valid=true",
        "input=2026.4.2rc1",
        "kind=prerelease",
        "is_prerelease=true",
    ]


@pytest.mark.e2e
def test_github_format_needs_github_output(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fail clearly, before doing any work, outside Actions."""
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    assert main(["--format", "github", "next-tag", "-r", str(repo)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "needs the GITHUB_OUTPUT environment variable" in captured.err
    monkeypatch.setenv("GITHUB_OUTPUT", "")
    assert main(["--format", "github", "next-tag", "-r", str(repo)]) == 2


@pytest.mark.e2e
@pytest.mark.parametrize("command", ["explain", "doctor", "tags"])
def test_github_format_refuses_commands_without_flat_results(
    repo: Path, github_output: Path, capsys: pytest.CaptureFixture[str], command: str
) -> None:
    """Say which commands support it rather than write nothing."""
    assert main(["--format", "github", command, "-r", str(repo)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert f"not supported by {command}" in captured.err
    assert not github_output.exists()

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

import pytest

from calver_scm.cli import main
from calver_scm.config import CalverConfig, CalverMode
from calver_scm.validation import newest_in_scopes, validate_version

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

MONTH = CalverConfig()
DAY = CalverConfig(mode=CalverMode.DAY)


def newest(
    tag: str, tags: list[str], config: CalverConfig = MONTH
) -> dict[str, bool] | None:
    result = newest_in_scopes(validate_version(tag, config, is_tag=True), config, tags)
    return result.newest


@pytest.mark.unit
@pytest.mark.parametrize(
    ("tag", "tags", "expected"),
    [
        # Nothing else released: newest everywhere.
        ("v2026.11.0", [], {"2026.11": True, "2026": True, "all": True}),
        # A hotfix for last month is newest only in its own period.
        (
            "v2026.10.0.post1",
            ["v2026.10.0", "v2026.11.0"],
            {"2026.10": True, "2026": False, "all": False},
        ),
        # The latest release of the year is not the latest overall.
        (
            "v2026.11.0",
            ["v2026.10.3", "v2027.1.0"],
            {"2026.11": True, "2026": True, "all": False},
        ),
        # Within a period, a higher patch or a later post-release wins.
        (
            "v2026.11.0.post1",
            ["v2026.11.0", "v2026.11.1"],
            {"2026.11": False, "2026": False, "all": False},
        ),
        (
            "v2026.11.0",
            ["v2026.11.0.post1"],
            {"2026.11": False, "2026": False, "all": False},
        ),
        # The tag itself and its other spellings never count against it.
        (
            "v2026.11.1",
            ["v2026.11.1", "v2026.011.1", "v2026.11.0"],
            {"2026.11": True, "2026": True, "all": True},
        ),
        # Pre-releases, dev releases and foreign tags are not counted.
        (
            "v2026.11.0",
            ["v2026.11.1rc1", "v2026.12.0.dev1", "latest"],
            {"2026.11": True, "2026": True, "all": True},
        ),
    ],
)
def test_newest_in_scopes(tag: str, tags: list[str], expected: dict[str, bool]) -> None:
    assert newest(tag, tags) == expected


@pytest.mark.unit
def test_newest_in_scopes_names_each_shorter_date_prefix() -> None:
    assert newest("v2026.11.4.0", ["v2026.11.9.0", "v2026.12.1.0"], DAY) == {
        "2026.11.4": True,
        "2026.11": False,
        "2026": False,
        "all": False,
    }


@pytest.mark.unit
def test_newest_in_scopes_leaves_an_invalid_result_alone() -> None:
    invalid = validate_version("v2026.13.0", MONTH, is_tag=True)
    assert newest_in_scopes(invalid, MONTH, ["v2026.1.0"]) is invalid
    assert invalid.newest is None


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


@pytest.fixture
def repo(make_git_project: Callable[..., Path]) -> Path:
    project = make_git_project('[tool.calver-scm]\nmode = "month"\n', tag="v2026.10.0")
    git(project, "commit", "--allow-empty", "-q", "-m", "second")
    git(project, "tag", "v2026.11.0")
    return project


def parse(repo: Path, *extra: str) -> int:
    return main(["parse", "v2026.10.0.post1", "--tag", "-r", str(repo), *extra])


@pytest.mark.e2e
def test_parse_against_repo_reports_newest_in_json(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(
            [
                "--json",
                "parse",
                "v2026.10.0.post1",
                "--tag",
                "--against-repo",
                "-r",
                str(repo),
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["newest"] == {"2026.10": True, "2026": False, "all": False}


@pytest.mark.e2e
def test_parse_against_repo_prints_newest_lines_in_plain_output(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert parse(repo, "--against-repo") == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[-3:] == [
        "newest.2026.10\ttrue",
        "newest.2026\tfalse",
        "newest.all\tfalse",
    ]


@pytest.mark.e2e
def test_parse_against_repo_shows_newest_in_rich_output(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(
            [
                "--format",
                "rich",
                "parse",
                "v2026.10.0.post1",
                "--tag",
                "--against-repo",
                "-r",
                str(repo),
            ]
        )
        == 0
    )
    assert "newest.2026.10" in capsys.readouterr().out


@pytest.mark.e2e
def test_parse_without_the_flag_has_no_newest(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--json", "parse", "v2026.10.0.post1", "--tag", "-r", str(repo)]) == 0
    assert "newest" not in json.loads(capsys.readouterr().out)


@pytest.mark.e2e
def test_parse_against_repo_needs_a_tag(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["parse", "2026.10.0", "--against-repo", "-r", str(repo)]) == 2
    assert "needs --tag" in capsys.readouterr().err


@pytest.mark.e2e
def test_parse_against_repo_skips_the_repository_for_an_invalid_tag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    assert (
        main(["parse", "v2026.13.0", "--tag", "--against-repo", "-r", str(tmp_path)])
        == 1
    )
    assert "invalid_month" in capsys.readouterr().out


@pytest.mark.e2e
@pytest.mark.filterwarnings("ignore:.*is shallow:UserWarning")
def test_parse_against_repo_refuses_a_shallow_clone(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    shallow = tmp_path / "shallow"
    subprocess.run(
        ["git", "clone", "-q", "--depth=1", f"file://{repo}", str(shallow)],
        check=True,
        capture_output=True,
    )
    assert parse(shallow, "--against-repo") == 3
    assert "[shallow_checkout]" in capsys.readouterr().err


@pytest.mark.e2e
def test_parse_against_repo_outside_a_repository_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert parse(tmp_path, "--against-repo") == 2
    assert capsys.readouterr().err.startswith("error: ")

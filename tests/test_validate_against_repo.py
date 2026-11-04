from __future__ import annotations

import datetime as dt
import json
import subprocess
from typing import TYPE_CHECKING

import pytest
import time_machine

from calver_scm.cli import main
from calver_scm.config import CalverConfig
from calver_scm.validation import (
    IssueCode,
    ValidationResult,
    validate_against_repo,
    validate_version,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

APR = dt.date(2026, 4, 15)
MONTH = CalverConfig()


def check(
    tag: str,
    tags: list[str],
    *,
    head: tuple[str, ...] = (),
    config: CalverConfig = MONTH,
) -> list[IssueCode]:
    result = validate_against_repo(
        validate_version(tag, config, is_tag=True),
        config,
        tags,
        head_tags=head,
        today=APR,
    )
    return [issue.code for issue in result.issues]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("tag", "tags", "head", "expected"),
    [
        # The next tag in sequence is fine, and so is the first of a period.
        ("v2026.4.3", ["v2026.4.2", "v2026.3.9"], (), []),
        ("v2026.4.0", [], (), []),
        # A tag-push build: the tag exists and points at HEAD.
        ("v2026.4.3", ["v2026.4.2", "v2026.4.3"], ("v2026.4.3",), []),
        # The same tag elsewhere, or under another spelling, already exists.
        ("v2026.4.2", ["v2026.4.2"], (), [IssueCode.TAG_EXISTS]),
        ("v2026.4.2", ["v2026.04.2"], (), [IssueCode.TAG_EXISTS]),
        (
            "v2026.4.2",
            ["v2026.04.2", "v2026.4.2"],
            ("v2026.4.2",),
            [IssueCode.TAG_EXISTS],
        ),
        # Skipping a patch, and being lower than an existing release.
        ("v2026.4.5", ["v2026.4.2"], (), [IssueCode.SKIPPED_PATCH]),
        ("v2026.4.1", ["v2026.4.2", "v2026.4.3"], (), [IssueCode.LOWER_THAN_EXISTING]),
        (
            "v2026.4.2",
            ["v2026.4.2", "v2026.4.5"],
            (),
            [IssueCode.TAG_EXISTS, IssueCode.LOWER_THAN_EXISTING],
        ),
        # A past period is flagged, and not also for its patch.
        (
            "v2026.3.9",
            ["v2026.4.0"],
            (),
            [IssueCode.PAST_PERIOD, IssueCode.LOWER_THAN_EXISTING],
        ),
        ("v2026.3.9", [], (), [IssueCode.PAST_PERIOD]),
        # Candidates are numbered like finals; dev and post-releases are not.
        ("v2026.4.3rc1", ["v2026.4.2"], (), []),
        ("v2026.4.5rc1", ["v2026.4.2"], (), [IssueCode.SKIPPED_PATCH]),
        ("v2026.4.9.post1", ["v2026.4.2"], (), []),
        ("v2026.4.2.post1", ["v2026.4.2", "v2026.4.5"], (), []),
        ("v2026.4.9.dev1", ["v2026.4.2"], (), []),
        # Other tags that are not releases never count against the tag.
        (
            "v2026.4.3",
            ["junk", "v2026.4.2rc1", "v2026.4.1.dev3"],
            (),
            [IssueCode.SKIPPED_PATCH],
        ),
    ],
)
def test_validate_against_repo(
    tag: str, tags: list[str], head: tuple[str, ...], expected: list[IssueCode]
) -> None:
    """Judge a tag as a new release among the existing tags."""
    assert check(tag, tags, head=head) == expected


@pytest.mark.unit
def test_validate_against_repo_leaves_an_invalid_result_alone() -> None:
    """Report only the syntax problem; there is nothing sound to compare."""
    result = validate_version("v2026.13.1", MONTH, is_tag=True)
    assert (
        validate_against_repo(result, MONTH, ["v2026.4.2"], head_tags=(), today=APR)
        is result
    )


@pytest.mark.unit
def test_validate_against_repo_without_patches_skips_the_numbering_check() -> None:
    """Report an existing release without also complaining about its patch."""
    config = CalverConfig(patch=False)
    assert check("v2026.4.0", ["v2026.4"], config=config) == [IssueCode.TAG_EXISTS]


@pytest.mark.unit
def test_validate_against_repo_keeps_the_syntax_result_type() -> None:
    """Return a result for the same input that stays valid when nothing is wrong."""
    result = validate_against_repo(
        validate_version("v2026.4.0", MONTH, is_tag=True),
        MONTH,
        [],
        head_tags=(),
        today=APR,
    )
    assert isinstance(result, ValidationResult)
    assert result.valid
    assert result.input == "v2026.4.0"


@pytest.mark.unit
def test_validate_against_repo_keeps_the_kind_only_while_valid() -> None:
    """Report the kind of a tag that passes, and none for one the repo refuses."""
    ok = validate_against_repo(
        validate_version("v2026.4.0rc1", MONTH, is_tag=True),
        MONTH,
        [],
        head_tags=(),
        today=APR,
    )
    assert ok.is_prerelease is True
    taken = validate_against_repo(
        validate_version("v2026.4.0rc1", MONTH, is_tag=True),
        MONTH,
        ["v2026.4.0rc1"],
        head_tags=(),
        today=APR,
    )
    assert not taken.valid
    assert taken.kind is None


NOW = dt.datetime(2026, 4, 15, 12, tzinfo=dt.UTC)


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
    """A repository released at v2026.04.2, with HEAD on that release."""
    project = make_git_project('[tool.calver-scm]\nmode = "month"\n', tag="v2026.04.0")
    git(project, "commit", "--allow-empty", "-q", "-m", "second")
    git(project, "tag", "v2026.04.1")
    git(project, "commit", "--allow-empty", "-q", "-m", "third")
    git(project, "tag", "v2026.04.2")
    return project


def run(repo: Path, tag: str, *extra: str) -> int:
    with time_machine.travel(NOW, tick=False):
        return main(
            ["validate", tag, "--tag", "--against-repo", "-r", str(repo), *extra]
        )


@pytest.mark.e2e
def test_against_repo_accepts_the_tag_being_built(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Pass on a tag-push build, where the tag exists and points at HEAD."""
    assert run(repo, "v2026.04.2") == 0
    assert capsys.readouterr().out == "valid: v2026.04.2\n"


@pytest.mark.e2e
def test_against_repo_accepts_the_next_tag(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Pass for a tag that is not made yet and follows on."""
    assert run(repo, "v2026.4.3") == 0
    assert capsys.readouterr().out == "valid: v2026.4.3\n"


@pytest.mark.e2e
def test_against_repo_reports_every_problem_in_all_formats(
    repo: Path, capsys: pytest.CaptureFixture[str], flat: Callable[[str], str]
) -> None:
    """Fail an existing tag that is not at HEAD, in plain, JSON and rich output."""
    git(repo, "commit", "--allow-empty", "-q", "-m", "moved on")
    assert run(repo, "v2026.4.1") == 1
    plain = capsys.readouterr().out
    assert plain.splitlines()[0] == "invalid: v2026.4.1"
    assert "tag_exists: Tag v2026.04.1 already exists" in plain
    assert "lower_than_existing:" in plain
    assert run(repo, "v2026.4.1", "--format", "json") == 1
    data = json.loads(capsys.readouterr().out)
    assert [e["code"] for e in data["errors"]] == ["tag_exists", "lower_than_existing"]
    assert run(repo, "v2026.4.1", "--format", "rich") == 1
    assert "tag_exists" in flat(capsys.readouterr().out)


@pytest.mark.e2e
@pytest.mark.parametrize(
    ("tag", "code"),
    [("v2026.4.6", "skipped_patch"), ("v2026.3.4", "past_period")],
)
def test_against_repo_flags_skips_and_past_periods(
    repo: Path, capsys: pytest.CaptureFixture[str], tag: str, code: str
) -> None:
    """Exit 1 with the matching code."""
    assert run(repo, tag) == 1
    assert f"{code}:" in capsys.readouterr().out


@pytest.mark.e2e
def test_against_repo_reports_a_syntax_error_without_reading_git(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Need no repository when the input is malformed anyway."""
    assert run(tmp_path, "v2026.13.1") == 1
    assert "invalid_month" in capsys.readouterr().out


@pytest.mark.e2e
def test_against_repo_needs_a_tag(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Reject the flag on a bare version as a usage error."""
    assert main(["validate", "2026.4.3", "--against-repo", "-r", str(repo)]) == 2
    assert "needs --tag" in capsys.readouterr().err


@pytest.mark.e2e
def test_against_repo_outside_a_repository_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Report that the tags could not be listed."""
    assert run(tmp_path, "v2026.4.3") == 2
    assert capsys.readouterr().err.startswith("error: Could not list Git tags")


@pytest.mark.e2e
@pytest.mark.filterwarnings("ignore:.*is shallow:UserWarning")
def test_against_repo_refuses_a_shallow_clone(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit 3 because the tag list cannot be trusted."""
    shallow = tmp_path / "shallow"
    subprocess.run(
        ["git", "clone", "-q", "--depth=1", f"file://{repo}", str(shallow)],
        check=True,
        capture_output=True,
    )
    assert run(shallow, "v2026.4.3") == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "[shallow_checkout]" in captured.err


@pytest.mark.e2e
def test_against_repo_without_a_head_commit_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Report a repository that has no commits to compare against."""
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    git(tmp_path, "init", "-q")
    assert run(tmp_path, "v2026.4.3") == 2
    assert capsys.readouterr().err.startswith("error: Could not list tags at HEAD")


@pytest.mark.e2e
def test_validate_without_the_flag_still_needs_no_repository(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Leave plain validate exactly as it was."""
    assert main(["validate", "v2026.4.3", "--tag", "-r", str(tmp_path)]) == 0
    assert capsys.readouterr().out == "valid: v2026.4.3\n"

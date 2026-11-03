from __future__ import annotations

import datetime as dt
import json
import subprocess
from typing import TYPE_CHECKING

import pytest
import time_machine

from calver_scm.cli import main

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

pytestmark = pytest.mark.e2e

APRIL = dt.datetime(2026, 4, 15, 12, tzinfo=dt.UTC)


def git(project: Path, *args: str) -> None:
    # Explicit identity: CI runners have no global user.name or user.email.
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
    """A repository tagged twice this period, once earlier, plus noise."""
    project = make_git_project('[tool.calver-scm]\nmode = "month"\n', tag="v2026.04.0")
    for tag in ("v2026.04.2", "v2026.03.9", "v2026.04.3rc1", "not-a-version"):
        git(project, "tag", tag)
    return project


def test_next_tag_prints_only_the_tag_when_piped(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Make the plain output directly usable as a command argument."""
    with time_machine.travel(APRIL, tick=False):
        assert main(["next-tag", "--root", str(repo)]) == 0
    assert capsys.readouterr().out == "v2026.4.3\n"


def test_next_tag_json_and_rich(
    repo: Path, capsys: pytest.CaptureFixture[str], flat: Callable[[str], str]
) -> None:
    """Report the evidence behind the proposal in the structured and rich formats."""
    with time_machine.travel(APRIL, tick=False):
        assert main(["--json", "next-tag", "--root", str(repo)]) == 0
        data = json.loads(capsys.readouterr().out)
        assert main(["--format", "rich", "next-tag", "--root", str(repo)]) == 0
        rich = flat(capsys.readouterr().out)
    assert data == {
        "tag": "v2026.4.3",
        "version": "2026.4.3",
        "patch": 3,
        "reason": "next_patch",
        "latest_tag": "v2026.04.2",
        "is_prerelease": False,
        "channel": None,
    }
    for fragment in (
        "next-tag",
        "Next tag v2026.4.3",
        "Next patch",
        "Latest release v2026.04.2",
    ):
        assert fragment in rich


def test_next_tag_starts_a_new_period_at_zero(
    repo: Path, capsys: pytest.CaptureFixture[str], flat: Callable[[str], str]
) -> None:
    """Restart the patch in a month with no release yet."""
    may = dt.datetime(2026, 5, 2, 12, tzinfo=dt.UTC)
    with time_machine.travel(may, tick=False):
        assert main(["--format", "rich", "next-tag", "--root", str(repo)]) == 0
    out = flat(capsys.readouterr().out)
    assert "Next tag v2026.5.0" in out
    assert "New period" in out
    assert "numbering starts at 0." in out
    assert "Latest release" not in out


def test_next_tag_exits_3_when_the_period_is_already_released(
    make_git_project: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """Refuse a second release when patch = false."""
    project = make_git_project("[tool.calver-scm]\npatch = false\n", tag="v2026.04.0")
    with time_machine.travel(APRIL, tick=False):
        assert main(["next-tag", "--root", str(project)]) == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.endswith("[period_already_released]\n")


@pytest.mark.filterwarnings("ignore:.*is shallow:UserWarning")
def test_next_tag_refuses_a_shallow_clone(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit 3 because the tag list cannot be trusted."""
    git(repo, "commit", "--allow-empty", "-q", "-m", "second")
    shallow = tmp_path / "shallow"
    subprocess.run(
        ["git", "clone", "-q", "--depth=1", f"file://{repo}", str(shallow)],
        check=True,
        capture_output=True,
    )
    assert main(["next-tag", "--root", str(shallow)]) == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "[shallow_checkout]" in captured.err


def test_next_tag_reports_invalid_configuration(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit 2, not 3, when the CalVer settings are unusable."""
    monkeypatch.setenv("CALVER_SCM_MODE", "decade")
    assert main(["next-tag", "--root", str(repo)]) == 2
    assert capsys.readouterr().err.startswith("error: Invalid config")


def test_next_tag_outside_a_repository_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Report that the tags could not be listed."""
    assert main(["next-tag", "--root", str(tmp_path)]) == 2
    assert capsys.readouterr().err.startswith("error: Could not list Git tags")


@pytest.mark.parametrize("flag", ["--date", "-d"])
def test_next_tag_date_overrides_today(
    repo: Path, capsys: pytest.CaptureFixture[str], flag: str
) -> None:
    """Plan for the given date instead of the clock, so a new period restarts at 0."""
    with time_machine.travel(APRIL, tick=False):
        assert main(["next-tag", "--root", str(repo), flag, "2026-05-03"]) == 0
    assert capsys.readouterr().out == "v2026.5.0\n"


def test_next_tag_date_in_a_past_period_continues_that_period(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Number against the tags of the period containing the date."""
    with time_machine.travel(APRIL, tick=False):
        assert main(["next-tag", "-r", str(repo), "-d", "2026-03-01"]) == 0
    assert capsys.readouterr().out == "v2026.3.10\n"


@pytest.mark.parametrize("value", ["2026-13-01", "yesterday", "2026/04/15"])
def test_next_tag_malformed_date_is_a_usage_error(
    repo: Path, capsys: pytest.CaptureFixture[str], value: str
) -> None:
    """Reject anything that is not an ISO calendar date, naming the bad value."""
    assert main(["next-tag", "--root", str(repo), "--date", value]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert value in captured.err
    assert "Unknown option" not in captured.err


def test_next_tag_pre_proposes_the_next_candidate(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Number the candidate against the tags already present, per channel."""
    with time_machine.travel(APRIL, tick=False):
        assert main(["next-tag", "--root", str(repo), "--pre", "rc"]) == 0
        assert capsys.readouterr().out == "v2026.4.3rc2\n"
        assert main(["next-tag", "--root", str(repo), "--pre", "a"]) == 0
        assert capsys.readouterr().out == "v2026.4.3a1\n"


def test_next_tag_pre_json_and_rich(
    repo: Path, capsys: pytest.CaptureFixture[str], flat: Callable[[str], str]
) -> None:
    """Report the channel and the latest pre-release in every format."""
    with time_machine.travel(APRIL, tick=False):
        assert main(["--json", "next-tag", "-r", str(repo), "--pre", "rc"]) == 0
        data = json.loads(capsys.readouterr().out)
        assert (
            main(["--format", "rich", "next-tag", "-r", str(repo), "--pre", "rc"]) == 0
        )
        rich = flat(capsys.readouterr().out)
    assert data == {
        "tag": "v2026.4.3rc2",
        "version": "2026.4.3rc2",
        "patch": 3,
        "reason": "next_prerelease",
        "latest_tag": "v2026.04.3rc1",
        "is_prerelease": True,
        "channel": "rc",
    }
    assert "Next tag v2026.4.3rc2" in rich
    assert "Latest pre-release v2026.04.3rc1" in rich


def test_next_tag_pre_rejects_an_unknown_channel(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Treat a channel other than a, b or rc as a usage error."""
    assert main(["next-tag", "--root", str(repo), "--pre", "alpha"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "alpha" in captured.err


def test_next_tag_pre_refuses_a_released_period_without_patches(
    make_git_project: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """Share the final tag's refusal rather than starting another period."""
    project = make_git_project("[tool.calver-scm]\npatch = false\n", tag="v2026.04.0")
    with time_machine.travel(APRIL, tick=False):
        assert main(["next-tag", "--root", str(project), "--pre", "rc"]) == 3
    assert capsys.readouterr().err.endswith("[period_already_released]\n")


@pytest.fixture
def promoting(make_git_project: Callable[..., Path]) -> Path:
    """A repository whose HEAD is exactly on a release candidate."""
    project = make_git_project('[tool.calver-scm]\nmode = "month"\n', tag="v2026.04.0")
    git(project, "commit", "--allow-empty", "-q", "-m", "candidate")
    git(project, "tag", "v2026.04.1rc1")
    return project


def test_next_tag_promote_proposes_the_final_tag(
    promoting: Path, capsys: pytest.CaptureFixture[str], flat: Callable[[str], str]
) -> None:
    """Finalise the candidate in every format, silently when HEAD is on it."""
    with time_machine.travel(APRIL, tick=False):
        assert main(["next-tag", "--root", str(promoting), "--promote"]) == 0
        captured = capsys.readouterr()
        assert (captured.out, captured.err) == ("v2026.4.1\n", "")
        assert main(["--json", "next-tag", "-r", str(promoting), "--promote"]) == 0
        data = json.loads(capsys.readouterr().out)
        assert main(["-f", "rich", "next-tag", "-r", str(promoting), "--promote"]) == 0
        rich = flat(capsys.readouterr().out)
    assert data["reason"] == "promotion"
    assert data["latest_tag"] == "v2026.04.1rc1"
    assert (data["is_prerelease"], data["channel"]) == (False, None)
    assert "Next tag v2026.4.1" in rich
    assert "Promoting v2026.04.1rc1" in rich


def test_next_tag_promote_warns_when_head_has_moved(
    promoting: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Still propose the tag, but say HEAD is beyond the candidate."""
    git(promoting, "commit", "--allow-empty", "-q", "-m", "after")
    with time_machine.travel(APRIL, tick=False):
        assert main(["next-tag", "--root", str(promoting), "--promote"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "v2026.4.1\n"
    assert "warning: HEAD is 1 commit ahead of v2026.04.1rc1" in captured.err
    git(promoting, "commit", "--allow-empty", "-q", "-m", "again")
    with time_machine.travel(APRIL, tick=False):
        assert main(["next-tag", "--root", str(promoting), "--promote"]) == 0
    assert "HEAD is 2 commits ahead" in capsys.readouterr().err


def test_next_tag_promote_refuses_a_candidate_off_the_branch(
    promoting: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit 3 when HEAD does not contain the candidate."""
    git(promoting, "checkout", "-q", "-b", "other", "v2026.04.0")
    with time_machine.travel(APRIL, tick=False):
        assert main(["next-tag", "--root", str(promoting), "--promote"]) == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.endswith("[prerelease_not_ancestor]\n")


def test_next_tag_promote_without_a_candidate_exits_3(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit 3 when the next release has no pre-release."""
    git(repo, "tag", "v2026.04.9")
    with time_machine.travel(APRIL, tick=False):
        assert main(["next-tag", "--root", str(repo), "--promote"]) == 3
    assert capsys.readouterr().err.endswith("[no_prerelease]\n")


def test_next_tag_pre_and_promote_cannot_be_combined(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Reject the combination as a usage error."""
    assert main(["next-tag", "--root", str(repo), "--pre", "rc", "--promote"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "cannot be combined" in captured.err

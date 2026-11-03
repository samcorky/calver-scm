from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

import pytest

from calver_scm.cli import main
from calver_scm.config import CalverConfig
from calver_scm.release import TagInfo, TagKind, classify_tags

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

MONTH = CalverConfig()


@pytest.mark.unit
def test_classify_tags_describes_every_kind_and_orders_them() -> None:
    """Order understood tags by period and version, then ignored ones by name."""
    tags = [
        "zzz",
        "v2026.10.0",
        "v2026.4.2.post1",
        "v2026.4.2",
        "v2026.4.3rc1",
        "v2026.4.3.dev2",
        "v2026.4.3a1.dev1",
        "v2025.12.0",
        "v2026.4.2",
        "not-a-version",
        "v2026.4.1.2.3",
        "0.4.1",
    ]
    infos = classify_tags(tags, MONTH)
    assert [(i.tag, i.kind, i.period, i.patch) for i in infos if i.reason is None] == [
        ("v2025.12.0", TagKind.FINAL, "2025.12", 0),
        ("v2026.4.2", TagKind.FINAL, "2026.4", 2),
        ("v2026.4.2.post1", TagKind.POSTRELEASE, "2026.4", 2),
        ("v2026.4.3.dev2", TagKind.DEV, "2026.4", 3),
        ("v2026.4.3a1.dev1", TagKind.DEV, "2026.4", 3),
        ("v2026.4.3rc1", TagKind.PRERELEASE, "2026.4", 3),
        ("v2026.10.0", TagKind.FINAL, "2026.10", 0),
    ]
    ignored = {i.tag: i for i in infos if i.kind is TagKind.IGNORED}
    assert list(ignored) == ["0.4.1", "not-a-version", "v2026.4.1.2.3", "zzz"]
    assert ignored["zzz"].reason == "not a valid PEP 440 version"
    assert "stable = true" in (ignored["0.4.1"].reason or "")
    assert ignored["v2026.4.1.2.3"].reason == (
        "5 release components do not fit the scheme YYYY.MM"
    )
    assert all(i.period is None and i.patch is None for i in ignored.values())


@pytest.mark.unit
def test_counted_matches_what_occupies_a_number() -> None:
    """Count finals and post-releases only, as next-tag does."""
    counted = {
        i.kind: i.counted
        for i in classify_tags(
            ["v2026.4.1", "v2026.4.1.post1", "v2026.4.2rc1", "v2026.4.2.dev1", "x"],
            MONTH,
        )
    }
    assert counted == {
        TagKind.FINAL: True,
        TagKind.POSTRELEASE: True,
        TagKind.PRERELEASE: False,
        TagKind.DEV: False,
        TagKind.IGNORED: False,
    }


@pytest.mark.unit
def test_classify_tags_of_nothing_is_empty() -> None:
    """Return no rows for no tags."""
    assert classify_tags([], MONTH) == []
    assert isinstance(TagInfo("t", TagKind.IGNORED, None, None, "r"), TagInfo)


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
    """A repository with a final, a candidate and an unrelated tag."""
    project = make_git_project('[tool.calver-scm]\nmode = "month"\n', tag="v2026.04.2")
    for tag in ("v2026.04.3rc1", "latest"):
        git(project, "tag", tag)
    return project


@pytest.mark.e2e
def test_tags_plain_output_is_tab_separated(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Give scripts one stable line per tag."""
    assert main(["tags", "--root", str(repo)]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "v2026.04.2\tfinal\t2026.4\t2",
        "v2026.04.3rc1\tprerelease\t2026.4\t3",
        "latest\tignored\t-\t-\tnot a valid PEP 440 version",
    ]


@pytest.mark.e2e
def test_tags_json_output(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Report the same facts as structured data."""
    assert main(["--json", "tags", "-r", str(repo)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["tags"][1] == {
        "tag": "v2026.04.3rc1",
        "kind": "prerelease",
        "period": "2026.4",
        "patch": 3,
        "counted": False,
        "reason": None,
    }
    assert [t["kind"] for t in data["tags"]] == ["final", "prerelease", "ignored"]


@pytest.mark.e2e
def test_tags_rich_output(
    repo: Path, capsys: pytest.CaptureFixture[str], flat: Callable[[str], str]
) -> None:
    """Show a table that says why a tag is not counted."""
    assert main(["--format", "rich", "tags", "-r", str(repo)]) == 0
    out = flat(capsys.readouterr().out)
    for fragment in (
        "Tag Kind Period Patch Note",
        "v2026.04.2 final 2026.4 2",
        "v2026.04.3rc1 prerelease 2026.4 3 not counted",
        "latest ignored - - not a valid PEP 440 version",
    ):
        assert fragment in out


@pytest.mark.e2e
def test_tags_rich_output_without_tags(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Say so rather than print an empty table."""
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    git(tmp_path, "init", "-q")
    assert main(["--format", "rich", "tags", "-r", str(tmp_path)]) == 0
    assert "No tags in this repository." in capsys.readouterr().out
    assert main(["tags", "-r", str(tmp_path)]) == 0
    assert capsys.readouterr().out == "\n"


@pytest.mark.e2e
def test_tags_honours_the_tag_prefix_and_scheme(
    make_git_project: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """Read tags under the configured scheme, not the default."""
    project = make_git_project(
        '[tool.calver-scm]\nscheme = "YY.MM"\ntag_prefix = "rel-"\n', tag="rel-26.4.1"
    )
    git(project, "tag", "latest")
    assert main(["tags", "-r", str(project)]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "rel-26.4.1\tfinal\t26.4\t1",
        "latest\tignored\t-\t-\tnot a valid PEP 440 version",
    ]


@pytest.mark.e2e
def test_tags_outside_a_repository_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Report that the tags could not be listed."""
    assert main(["tags", "-r", str(tmp_path)]) == 2
    assert capsys.readouterr().err.startswith("error: Could not list Git tags")


@pytest.mark.e2e
@pytest.mark.filterwarnings("ignore:.*is shallow:UserWarning")
def test_tags_warns_on_a_shallow_clone(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Still list, but say tags may be missing."""
    git(repo, "commit", "--allow-empty", "-q", "-m", "second")
    shallow = tmp_path / "shallow"
    subprocess.run(
        ["git", "clone", "-q", "--depth=1", f"file://{repo}", str(shallow)],
        check=True,
        capture_output=True,
    )
    assert main(["tags", "-r", str(shallow)]) == 0
    assert "warning: this is a shallow clone" in capsys.readouterr().err

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from calver_scm.cli import main
from calver_scm.cli_output import Output, OutputFormat, _md_cell

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

SETUPTOOLS = """
[project]
name = "demo"
dynamic = ["version"]
[tool.setuptools_scm]
version_scheme = "calver-scm"
local_scheme = "no-local-version"
"""


@pytest.fixture
def summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point $GITHUB_STEP_SUMMARY at a temporary file, as Actions does."""
    path = tmp_path / "step_summary"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(path))
    return path


@pytest.fixture
def project(make_git_project: Callable[..., Path]) -> Path:
    """A project released at v2026.04.2 that every command can read."""
    return make_git_project(SETUPTOOLS, tag="v2026.04.2")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("plain", "plain"),
        ("a|b", r"a\|b"),
        ("two\nlines", "two lines"),
        ("<script>x</script>", "&lt;script&gt;x&lt;/script&gt;"),
        ("`code`", r"\`code\`"),
        ("*bold* _it_", r"\*bold\* \_it\_"),
        ("[link](u)", r"\[link\](u)"),
        (None, ""),
        (True, "true"),
        (3, "3"),
    ],
)
def test_md_cell_escapes_markdown_and_html(raw: object, expected: str) -> None:
    """Neutralise anything a tag name or setting could use to break the layout."""
    assert _md_cell(raw) == expected


@pytest.mark.unit
def test_summary_is_appended_not_overwritten(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Keep what earlier steps wrote, and leave the printed result alone."""
    path = tmp_path / "step_summary"
    path.write_text("earlier step\n", encoding="utf-8")
    Output(OutputFormat.PLAIN, step_summary=path).version("2026.4.3")
    text = path.read_text(encoding="utf-8")
    assert text.startswith("earlier step\n")
    assert "## calver-scm version" in text
    assert "2026.4.3" in text
    assert capsys.readouterr().out == "2026.4.3\n"


@pytest.mark.e2e
def test_doctor_summary_is_a_table_of_checks(
    project: Path, summary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Show every check with its severity, and the overall status."""
    assert main(["--summary", "doctor", "-r", str(project)]) == 0
    capsys.readouterr()
    lines = summary.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "## calver-scm doctor"
    assert "**Status:** ok" in lines
    assert "| Severity | Check | Summary | Detail | Fix |" in lines
    assert any(line.startswith("| ok | `build_config` |") for line in lines)
    assert any(line.startswith("| ok | `resolution` |") for line in lines)


@pytest.mark.e2e
def test_summary_leaves_stdout_and_the_exit_code_unchanged(
    project: Path, summary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Writing the summary is additional: the result is printed as before."""
    plain = main(["--format", "plain", "doctor", "-r", str(project)])
    expected = capsys.readouterr().out
    with_summary = main(
        ["--summary", "--format", "plain", "doctor", "-r", str(project)]
    )
    assert (with_summary, capsys.readouterr().out) == (plain, expected)
    assert summary.exists()


@pytest.mark.e2e
def test_failing_doctor_still_writes_its_summary(
    make_git_project: Callable[..., Path],
    summary: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Explain a failed run on the run page, the moment it is most needed."""
    broken = make_git_project("[project]\nname = 'demo'\n", tag="v2026.04.2")
    assert main(["--summary", "doctor", "-r", str(broken)]) == 1
    capsys.readouterr()
    text = summary.read_text(encoding="utf-8")
    assert "**Status:** error" in text
    assert "| error | `build_config` |" in text


@pytest.mark.e2e
@pytest.mark.parametrize(
    ("args", "heading"),
    [
        (["version"], "## calver-scm version"),
        (["explain"], "## calver-scm explain"),
        (["next-tag"], "## calver-scm next-tag"),
        (["tags"], "## calver-scm tags"),
        (["validate", "v2026.4.2", "--tag"], "## calver-scm validate"),
        (["parse", "v2026.4.2", "--tag"], "## calver-scm parse"),
    ],
    ids=lambda value: value if isinstance(value, str) else value[0],
)
def test_every_command_can_write_a_summary(
    project: Path,
    summary: Path,
    capsys: pytest.CaptureFixture[str],
    args: list[str],
    heading: str,
) -> None:
    """Give each command, including the ones --format github refuses, a summary."""
    command, *rest = args
    assert main(["--summary", command, *rest, "-r", str(project)]) == 0
    capsys.readouterr()
    assert summary.read_text(encoding="utf-8").startswith(f"{heading}\n")


@pytest.mark.e2e
def test_explain_summary_names_where_each_setting_came_from(
    project: Path, summary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Carry the provenance, which is the point of explain, into the summary."""
    assert main(["--summary", "explain", "-r", str(project)]) == 0
    capsys.readouterr()
    text = summary.read_text(encoding="utf-8")
    assert "| Setting | Value | Source |" in text
    assert "| `mode` | month | `default` |" in text


@pytest.mark.e2e
def test_tags_summary_is_a_table_of_tags(
    project: Path, summary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """List each tag and how it reads under the scheme."""
    assert main(["--summary", "tags", "-r", str(project)]) == 0
    capsys.readouterr()
    text = summary.read_text(encoding="utf-8")
    assert "| Tag | Kind | Period | Patch | Counted | Reason |" in text
    assert "| v2026.04.2 |" in text


@pytest.mark.e2e
def test_invalid_input_lists_its_findings_in_the_summary(
    tmp_path: Path, summary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Show why a tag was rejected, and still exit 1."""
    assert main(["--summary", "validate", "2026.13.1", "-r", str(tmp_path)]) == 1
    capsys.readouterr()
    text = summary.read_text(encoding="utf-8")
    assert "**Result:** invalid" in text
    assert "- `" in text


@pytest.mark.e2e
def test_hostile_tag_cannot_break_the_summary(
    tmp_path: Path, summary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Escape the input echoed back, so a crafted tag injects no markup."""
    hostile = "v1|<img src=x onerror=alert(1)>\n## injected"
    assert main(["--summary", "validate", hostile, "--tag", "-r", str(tmp_path)]) == 1
    capsys.readouterr()
    text = summary.read_text(encoding="utf-8")
    assert "<img" not in text
    assert "\n## injected" not in text


@pytest.mark.e2e
def test_summary_and_github_output_work_together(
    project: Path,
    summary: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Let one step export an output and write its summary."""
    output = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    assert (
        main(["--summary", "--format", "github", "next-tag", "-r", str(project)]) == 0
    )
    capsys.readouterr()
    assert output.read_text(encoding="utf-8").startswith("tag=")
    assert summary.read_text(encoding="utf-8").startswith("## calver-scm next-tag")


@pytest.mark.e2e
@pytest.mark.parametrize("value", [None, ""])
def test_summary_needs_github_step_summary(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    value: str | None,
) -> None:
    """Refuse before doing any work when Actions has not set the variable."""
    if value is None:
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    else:
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", value)
    assert main(["--summary", "version", "-r", str(project)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "needs the GITHUB_STEP_SUMMARY environment variable" in captured.err


@pytest.mark.e2e
def test_explain_summary_lists_environment_overrides(
    project: Path,
    summary: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Say which CALVER_SCM_* variables changed the result."""
    monkeypatch.setenv("CALVER_SCM_NO_DEV", "true")
    assert main(["--summary", "explain", "-r", str(project)]) == 0
    capsys.readouterr()
    text = summary.read_text(encoding="utf-8")
    assert "### Environment overrides" in text
    assert "| CALVER\\_SCM\\_NO\\_DEV | true |" in text

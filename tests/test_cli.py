from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import time_machine

from calver_scm.cli import MISSING_EXTRA_MESSAGE, main
from calver_scm.diagnostics import CheckCode
from calver_scm.models import ResolutionReason
from calver_scm.release import NextTagReason
from calver_scm.validation import IssueCode

if TYPE_CHECKING:
    from collections.abc import Callable

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
    """A project three commits past a tag from an earlier month."""
    return make_git_project(SETUPTOOLS, tag="v2020.01.4", commits_after_tag=3)


@pytest.mark.e2e
def test_version_prints_the_build_version(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Print one plain version string on stdout."""
    with time_machine.travel(_noon(2026, 4, 15), tick=False):
        assert main(["version", "--root", str(project)]) == 0
    captured = capsys.readouterr()
    assert captured.out == "2026.4.0.dev3\n"
    assert captured.err == ""


@pytest.mark.e2e
def test_version_json(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Print only a JSON object on stdout when --json is given."""
    with time_machine.travel(_noon(2026, 4, 15), tick=False):
        assert main(["version", "--root", str(project), "--json"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"version": "2026.4.0.dev3"}
    assert captured.err == ""


@pytest.mark.e2e
def test_version_defaults_to_the_current_directory(
    project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Resolve the project in the working directory when --root is omitted."""
    monkeypatch.chdir(project)
    with time_machine.travel(_noon(2026, 4, 15), tick=False):
        assert main(["version"]) == 0
    assert capsys.readouterr().out == "2026.4.0.dev3\n"


@pytest.mark.unit
def test_resolution_failure_exits_2_with_message_on_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Keep stdout empty and explain the failure on stderr."""
    assert main(["version", "--root", str(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("error: No pyproject.toml")


@pytest.mark.unit
def test_invalid_invocation_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    """Report unknown options as usage errors."""
    assert main(["version", "--bogus"]) == 2
    assert capsys.readouterr().out == ""


@pytest.mark.unit
def test_help_and_version_flags_succeed(capsys: pytest.CaptureFixture[str]) -> None:
    """Show help and the installed package version without error."""
    assert main(["--help"]) == 0
    assert "version" in capsys.readouterr().out
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip()


@pytest.mark.unit
def test_missing_cli_extra_gives_install_guidance(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fail with an install hint, not a traceback, when Cyclopts is absent."""
    monkeypatch.setitem(sys.modules, "cyclopts", None)
    assert main(["version"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == MISSING_EXTRA_MESSAGE


def _noon(year: int, month: int, day: int) -> dt.datetime:
    return dt.datetime(year, month, day, 12, tzinfo=dt.UTC)


def _project_config(tmp_path: Path, body: str) -> Path:
    (tmp_path / "pyproject.toml").write_text(
        f"[tool.calver-scm]\n{body}\n", encoding="utf-8"
    )
    return tmp_path


@pytest.mark.unit
def test_validate_accepts_a_valid_version(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Print the verdict on stdout and exit 0."""
    root = _project_config(tmp_path, 'mode = "month"')
    assert main(["validate", "2026.4.2", "--root", str(root)]) == 0
    assert capsys.readouterr().out == "valid: 2026.4.2\n"


@pytest.mark.unit
def test_validate_rejects_an_invalid_version_with_exit_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Print each issue on stdout and exit 1, leaving stderr empty."""
    root = _project_config(tmp_path, 'mode = "month"')
    assert main(["validate", "2026.13.1", "--root", str(root)]) == 1
    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        "invalid: 2026.13.1",
        "  invalid_month: Month must be between 1 and 12, got 13",
    ]
    assert captured.err == ""


@pytest.mark.unit
def test_validate_json_reports_errors_on_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Keep JSON parseable on failure and still exit 1."""
    root = _project_config(tmp_path, 'mode = "month"')
    assert main(["validate", "2026.13.1", "--json", "--root", str(root)]) == 1
    assert json.loads(capsys.readouterr().out) == {
        "valid": False,
        "input": "2026.13.1",
        "errors": [
            {
                "code": "invalid_month",
                "message": "Month must be between 1 and 12, got 13",
            }
        ],
    }


@pytest.mark.unit
def test_validate_json_reports_the_kind_of_a_valid_version(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Say whether a valid version is a pre-release, for callers that publish it."""
    root = _project_config(tmp_path, 'mode = "month"')
    assert main(["validate", "2026.4.2rc1", "--json", "--root", str(root)]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "valid": True,
        "input": "2026.4.2rc1",
        "errors": [],
        "kind": "prerelease",
        "is_prerelease": True,
        "period": "2026.4",
        "date": {"YYYY": 2026, "MM": 4},
        "patch": 2,
        "pre": "rc1",
        "post": None,
        "dev": None,
    }


@pytest.mark.unit
def test_validate_tag_uses_the_configured_prefix(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Require the project's tag prefix in --tag mode."""
    root = _project_config(tmp_path, 'tag_prefix = "release-"')
    assert main(["validate", "release-2026.4.2", "--tag", "--root", str(root)]) == 0
    capsys.readouterr()
    assert main(["validate", "v2026.4.2", "--tag", "--root", str(root)]) == 1
    assert "missing_tag_prefix" in capsys.readouterr().out


@pytest.mark.unit
def test_validate_without_a_pyproject_uses_defaults(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fall back to the default scheme when the project has no configuration."""
    assert main(["validate", "2026.4.2", "--root", str(tmp_path)]) == 0
    assert capsys.readouterr().out == "valid: 2026.4.2\n"


@pytest.mark.unit
def test_validate_reports_configuration_errors_with_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Treat an invalid project configuration as an error, not a verdict."""
    root = _project_config(tmp_path, 'mode = "decade"')
    assert main(["validate", "2026.4.2", "--root", str(root)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("error: Invalid config")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("args", "fragments"),
    [
        (
            ["--format", "plain"],
            [
                "invalid: 2026.13.1",
                "  invalid_month: Month must be between 1 and 12, got 13",
            ],
        ),
        (
            ["--format", "rich"],
            [
                "invalid",
                "✗ 2026.13.1",
                "invalid_month",
                "Month must be between 1 and 12, got 13",
            ],
        ),
    ],
    ids=["plain", "rich"],
)
@pytest.mark.parametrize("position", ["before", "after"])
def test_format_flag_works_before_or_after_the_command(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    args: list[str],
    fragments: list[str],
    position: str,
) -> None:
    """Accept the global --format option on either side of the command."""
    command = ["validate", "2026.13.1", "--root", str(tmp_path)]
    argv = [*args, *command] if position == "before" else [*command, *args]
    assert main(argv) == 1
    out = capsys.readouterr().out
    assert all(fragment in out for fragment in fragments)


@pytest.mark.unit
@pytest.mark.parametrize(
    "argv",
    [["--json", "validate", "2026.4.2"], ["validate", "2026.4.2", "--format", "json"]],
)
def test_json_shorthand_and_format_json_agree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], argv: list[str]
) -> None:
    """Treat --json as shorthand for --format json."""
    assert main([*argv, "--root", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "valid": True,
        "input": "2026.4.2",
        "errors": [],
        "kind": "final",
        "is_prerelease": False,
        "period": "2026.4",
        "date": {"YYYY": 2026, "MM": 4},
        "patch": 2,
        "pre": None,
        "post": None,
        "dev": None,
    }


@pytest.mark.unit
def test_rich_valid_verdict(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Render a valid verdict with a tick."""
    assert (
        main(["--format", "rich", "validate", "2026.4.2", "--root", str(tmp_path)]) == 0
    )
    out = capsys.readouterr().out
    assert "✓ 2026.4.2" in out
    assert "is valid" in out


@pytest.mark.e2e
def test_rich_version(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Show the version in a titled panel in rich output."""
    with time_machine.travel(_noon(2026, 4, 15), tick=False):
        assert main(["--format", "rich", "version", "--root", str(project)]) == 0
    out = capsys.readouterr().out
    assert "version" in out
    assert "2026.4.0.dev3" in out


@pytest.mark.e2e
def test_format_json_version_matches_json_shorthand(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Emit the same JSON for version whichever way it is requested."""
    with time_machine.travel(_noon(2026, 4, 15), tick=False):
        assert main(["--format", "json", "version", "--root", str(project)]) == 0
    assert json.loads(capsys.readouterr().out) == {"version": "2026.4.0.dev3"}


@pytest.mark.unit
def test_auto_format_is_rich_on_a_terminal_and_plain_otherwise(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Pick the output style from whether stdout is interactive."""
    argv = ["validate", "2026.4.2", "--root", str(tmp_path)]
    assert main(argv) == 0
    assert capsys.readouterr().out == "valid: 2026.4.2\n"

    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    assert main(argv) == 0
    assert "is valid" in capsys.readouterr().out


@pytest.mark.unit
def test_unknown_format_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    """Reject values outside auto, rich, plain and json."""
    assert main(["--format", "yaml", "validate", "2026.4.2"]) == 2
    assert capsys.readouterr().out == ""


def _plain_explanation(out: str) -> dict[str, str]:
    return dict(line.split(": ", 1) for line in out.splitlines())


@pytest.mark.e2e
def test_explain_describes_a_patch_reset(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Report each fact behind a version from an earlier tagged period."""
    with time_machine.travel(_noon(2026, 4, 15), tick=False):
        assert main(["explain", "--root", str(project)]) == 0
    facts = _plain_explanation(capsys.readouterr().out)
    assert facts == {
        "version": "2026.4.0.dev3",
        "public_version": "2026.4.0.dev3",
        "local_segment": "none",
        "reason": "patch_reset",
        "scm.tag": "2020.1.4",
        "scm.distance": "3",
        "scm.dirty": "false",
        "calculation.date": "2026-04-15",
        "calculation.timezone": "UTC",
        "calculation.base": "2026.4",
        "calculation.tag_base": "2020.1",
        "calculation.tag_patch": "4",
        "calculation.patch": "0",
        "config.mode": "month",
        "config.scheme": "YYYY.MM",
        "config.patch": "true",
        "config.stable": "true",
        "config.no_dev": "false",
        "config.fallback": "dev",
        "config.tag_prefix": "v",
    }


@pytest.mark.e2e
def test_explain_distinguishes_public_version_from_local_segment(
    make_git_project: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """Show the suffix setuptools-scm adds after the CalVer scheme has run."""
    project = make_git_project(
        SETUPTOOLS.replace("no-local-version", "node-and-date"),
        tag="v2026.04.2",
        commits_after_tag=1,
    )
    with time_machine.travel(_noon(2026, 4, 15), tick=False):
        assert main(["--json", "explain", "--root", str(project)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["public_version"] == "2026.4.3.dev1"
    assert data["reason"] == "patch_incremented"
    assert data["local_segment"].startswith("g")
    assert data["version"] == f"{data['public_version']}+{data['local_segment']}"
    assert data["calculation"]["tag_patch"] == 2
    assert data["calculation"]["patch"] == 3


@pytest.mark.e2e
def test_explain_reports_exact_tag_and_environment_overrides(
    make_git_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Report a clean tag as is, and list the active CALVER_SCM_* variables."""
    monkeypatch.setenv("CALVER_SCM_NO_DEV", "true")
    project = make_git_project(SETUPTOOLS, tag="v2026.04.2")
    assert main(["--json", "explain", "--root", str(project)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["reason"] == "exact_tag"
    assert data["version"] == "2026.4.2"
    assert data["env_overrides"] == {"CALVER_SCM_NO_DEV": "true"}
    assert data["config"]["no_dev"] is True


@pytest.mark.e2e
def test_explain_a_repository_without_tags_uses_the_fallback(
    make_git_project: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """Explain the fallback; setuptools-scm supplies tag 0.0 when none exists."""
    project = make_git_project(SETUPTOOLS)
    with time_machine.travel(_noon(2026, 4, 15), tick=False):
        assert main(["--json", "explain", "--root", str(project)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["reason"] == "incompatible_tag_fallback"
    assert data["scm"]["tag"] == "0.0"
    assert data["calculation"]["tag_base"] is None
    assert data["calculation"]["tag_patch"] is None


@pytest.mark.e2e
def test_explain_rich_output_has_labelled_sections(
    project: Path,
    capsys: pytest.CaptureFixture[str],
    flat: Callable[[str], str],
) -> None:
    """Group the facts under headings and summarise the decision in words."""
    with time_machine.travel(_noon(2026, 4, 15), tick=False):
        assert main(["--format", "rich", "explain", "--root", str(project)]) == 0
    out = flat(capsys.readouterr().out)
    for fragment in (
        "calver-scm explain",
        "Version 2026.4.0.dev3",
        "Patch reset",
        "so the patch starts again at 0.",
        "2020.1.4 +3 commits → patch reset → 2026.4.0.dev3",
        "SCM",
        "Calculation",
        "Configuration",
        "No CALVER_SCM_* overrides are set.",
    ):
        assert fragment in out


@pytest.mark.e2e
def test_explain_fails_when_the_scheme_is_bypassed(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Refuse to explain a version that setuptools-scm took from an override."""
    monkeypatch.setenv("SETUPTOOLS_SCM_PRETEND_VERSION", "9.9.9")
    assert main(["explain", "--root", str(project)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "did not call the calver-scm version scheme" in captured.err


@pytest.mark.unit
def test_explain_reports_resolution_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit 2 with a message on stderr when the project cannot be resolved."""
    assert main(["explain", "--root", str(tmp_path)]) == 2
    assert capsys.readouterr().err.startswith("error: No pyproject.toml")


@pytest.mark.e2e
@pytest.mark.parametrize("command", ["version", "explain"])
def test_invalid_calver_configuration_is_a_clean_error(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    """Exit 2 with a message, not a traceback, when the CalVer settings are invalid."""
    monkeypatch.setenv("CALVER_SCM_MODE", "decade")
    assert main([command, "--root", str(project)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: Invalid config: Invalid mode: 'decade'\n"


@pytest.mark.unit
def test_root_help_lists_every_command_with_examples_and_exit_codes(
    capsys: pytest.CaptureFixture[str], flat: Callable[[str], str]
) -> None:
    """Make the top-level help enough to get started without the README."""
    assert main(["--help"]) == 0
    out = flat(capsys.readouterr().out)
    for command in ("version", "validate", "explain", "doctor", "next-tag", "tags"):
        assert f"calver-scm {command}" in out
    for fragment in ("Examples", "Exit codes", "--format", "--json", "Output"):
        assert fragment in out


@pytest.mark.unit
@pytest.mark.parametrize(
    "command", ["version", "validate", "explain", "doctor", "next-tag", "tags"]
)
def test_every_command_help_has_examples(
    command: str, capsys: pytest.CaptureFixture[str], flat: Callable[[str], str]
) -> None:
    """Give each command a description, its options and worked examples."""
    assert main([command, "--help"]) == 0
    out = flat(capsys.readouterr().out)
    assert f"calver-scm {command}" in out
    assert "Examples" in out
    assert "--root" in out


@pytest.mark.unit
def test_validate_help_shows_one_positional_argument(
    capsys: pytest.CaptureFixture[str], flat: Callable[[str], str]
) -> None:
    """Document the version as an argument only, not also as a keyword option."""
    assert main(["validate", "--help"]) == 0
    out = flat(capsys.readouterr().out)
    assert "VERSION" in out
    assert "--candidate" not in out
    assert "--version" not in out.split("Usage:")[1].split("Examples")[0]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("command", "reasons"),
    [("explain", list(ResolutionReason)), ("next-tag", list(NextTagReason))],
)
def test_help_lists_every_reason_with_its_wording(
    command: str,
    reasons: list[ResolutionReason | NextTagReason],
    capsys: pytest.CaptureFixture[str],
    flat: Callable[[str], str],
) -> None:
    """Generate the help from the enums so it cannot drift from the code."""
    assert main([command, "--help"]) == 0
    out = flat(capsys.readouterr().out)
    for reason in reasons:
        assert reason.value in out
        assert reason.label in out


@pytest.mark.unit
def test_readme_documents_every_reason() -> None:
    """Fail when a new reason is added without documenting it in the README."""
    readme = (Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8")
    for reason in [*ResolutionReason, *NextTagReason]:
        assert f"`{reason.value}`" in readme


@pytest.mark.unit
def test_readme_documents_every_error_and_check_code() -> None:
    """Fail when a validate error code or doctor check code is undocumented."""
    readme = (Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8")
    for code in [*IssueCode, *CheckCode]:
        assert f"`{code.value}`" in readme


@pytest.mark.unit
@pytest.mark.parametrize("argv", [[], ["--json"], ["--format", "plain"]])
def test_no_command_shows_the_help_and_succeeds(
    argv: list[str], capsys: pytest.CaptureFixture[str], flat: Callable[[str], str]
) -> None:
    """Show usage, not a traceback, when only global options are given."""
    assert main(argv) == 0
    captured = capsys.readouterr()
    out = flat(captured.out)
    assert "Usage: calver-scm COMMAND" in out
    assert "Examples" in out
    assert captured.err == ""


@pytest.mark.unit
def test_short_root_flag_matches_long_form(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Accept -r wherever --root is accepted."""
    assert main(["--json", "validate", "2026.4.2", "-r", str(tmp_path)]) == 0
    short = capsys.readouterr().out
    assert main(["--json", "validate", "2026.4.2", "--root", str(tmp_path)]) == 0
    assert short == capsys.readouterr().out


@pytest.mark.unit
def test_short_tag_flag_matches_long_form(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Accept -t as --tag on validate."""
    assert main(["validate", "v2026.4.2", "-t", "-r", str(tmp_path)]) == 0
    capsys.readouterr()
    assert main(["validate", "2026.4.2", "-t", "-r", str(tmp_path)]) == 1
    assert "missing_tag_prefix" in capsys.readouterr().out


@pytest.mark.unit
@pytest.mark.parametrize("position", ["before", "after"])
@pytest.mark.parametrize(
    "short",
    [["-j"], ["-f", "json"]],
    ids=["-j", "-f"],
)
def test_short_output_flags_match_long_forms(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    short: list[str],
    position: str,
) -> None:
    """Accept -j and -f on either side of the command, like --json and --format."""
    command = ["validate", "2026.4.2", "-r", str(tmp_path)]
    argv = [*short, *command] if position == "before" else [*command, *short]
    assert main(argv) == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True


@pytest.mark.unit
def test_parse_json_reports_the_parts_of_a_tag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Give a script the parts of a tag without re-parsing it against the scheme."""
    root = _project_config(tmp_path, 'mode = "month"\nstable = false')
    argv = ["--json", "parse", "v0.2026.11.0.post1", "--tag", "--root", str(root)]
    assert main(argv) == 0
    assert json.loads(capsys.readouterr().out) == {
        "valid": True,
        "input": "v0.2026.11.0.post1",
        "errors": [],
        "kind": "postrelease",
        "is_prerelease": False,
        "period": "2026.11",
        "date": {"YYYY": 2026, "MM": 11},
        "patch": 0,
        "pre": None,
        "post": 1,
        "dev": None,
    }


@pytest.mark.unit
def test_parse_plain_prints_a_line_per_part(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Print tab-separated parts, with an empty value for a part that is absent."""
    root = _project_config(tmp_path, 'mode = "month"')
    assert main(["parse", "2026.4.2rc1", "--root", str(root)]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "kind\tprerelease",
        "period\t2026.4",
        "date.YYYY\t2026",
        "date.MM\t4",
        "patch\t2",
        "pre\trc1",
        "post\t",
        "dev\t",
    ]


@pytest.mark.unit
def test_parse_rich_shows_a_table(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Render the parts in a panel titled with the input."""
    root = _project_config(tmp_path, 'mode = "month"')
    assert main(["--format", "rich", "parse", "2026.4.2", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "2026.4.2" in out
    assert "date.YYYY" in out
    assert "2026" in out


@pytest.mark.unit
def test_parse_reports_an_invalid_input_like_validate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Print the findings and exit 1, so a script stops on a bad tag."""
    root = _project_config(tmp_path, 'mode = "month"')
    assert main(["parse", "2026.13.1", "--root", str(root)]) == 1
    assert capsys.readouterr().out.startswith("invalid: 2026.13.1")


@pytest.mark.unit
def test_parse_fails_on_an_unusable_configuration(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit 2 with the reason, as validate does."""
    root = _project_config(tmp_path, 'mode = "fortnight"')
    assert main(["parse", "2026.4.2", "--root", str(root)]) == 2
    assert capsys.readouterr().err.startswith("error:")

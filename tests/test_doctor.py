from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING, Any

import pytest

from calver_scm.cli import main
from calver_scm.diagnostics import CheckCode, Diagnostic, DoctorReport, Severity

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

SETUPTOOLS = """
[project]
name = "demo"
dynamic = ["version"]
[tool.setuptools_scm]
version_scheme = "calver-scm"
local_scheme = "{local_scheme}"
"""


def run_doctor(
    capsys: pytest.CaptureFixture[str], project: Path
) -> tuple[int, dict[str, Any]]:
    code = main(["--json", "doctor", "--root", str(project)])
    return code, json.loads(capsys.readouterr().out)


def by_code(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {check["code"]: check for check in report["checks"]}


@pytest.fixture
def healthy(make_git_project: Callable[..., Path]) -> Path:
    return make_git_project(
        SETUPTOOLS.format(local_scheme="no-local-version"), tag="v2026.04.2"
    )


@pytest.mark.e2e
def test_healthy_project_reports_ok(
    healthy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Pass every check on a tagged, clean, correctly configured project."""
    code, report = run_doctor(capsys, healthy)
    assert code == 0
    assert report["status"] == "ok"
    assert [(c["code"], c["severity"]) for c in report["checks"]] == [
        ("build_config", "ok"),
        ("calver_config", "ok"),
        ("git_available", "ok"),
        ("resolution", "ok"),
    ]


@pytest.mark.e2e
def test_untagged_dirty_project_warns_without_failing(
    make_git_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Report fallback, dirty tree, no_dev and overrides as non-fatal findings."""
    monkeypatch.setenv("CALVER_SCM_NO_DEV", "true")
    project = make_git_project(
        SETUPTOOLS.format(local_scheme="node-and-date"), dirty=True
    )
    code, report = run_doctor(capsys, project)
    checks = by_code(report)
    assert code == 0
    assert report["status"] == "warning"
    assert checks["no_compatible_tag"]["severity"] == "warning"
    assert checks["no_compatible_tag"]["remediation"].startswith("Tag a release")
    assert checks["no_dev_local_segment"]["severity"] == "warning"
    assert checks["dirty_tree"]["severity"] == "info"
    assert checks["env_overrides"]["detail"] == "CALVER_SCM_NO_DEV=true"


@pytest.mark.e2e
def test_strict_fails_on_a_warning(
    make_git_project: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit 1 under --strict when a finding is a warning, still printing the report."""
    project = make_git_project(SETUPTOOLS.format(local_scheme="no-local-version"))
    code = main(["--json", "doctor", "--strict", "--root", str(project)])
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "warning"
    assert code == 1


@pytest.mark.e2e
def test_strict_passes_a_healthy_project(
    healthy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit 0 under --strict when every check is ok."""
    code = main(["--json", "doctor", "--strict", "--root", str(healthy)])
    assert json.loads(capsys.readouterr().out)["status"] == "ok"
    assert code == 0


@pytest.mark.e2e
def test_strict_ignores_info_findings(
    healthy: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Exit 0 under --strict when the worst finding is info (an env override)."""
    monkeypatch.setenv("CALVER_SCM_STABLE", "true")
    code = main(["--json", "doctor", "--strict", "--root", str(healthy)])
    checks = by_code(json.loads(capsys.readouterr().out))
    assert checks["env_overrides"]["severity"] == "info"
    assert code == 0


@pytest.mark.e2e
@pytest.mark.filterwarnings("ignore:.*is shallow:UserWarning")
def test_shallow_clone_is_flagged(
    make_git_project: Callable[..., Path],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Warn that tags and distance cannot be trusted in a shallow clone."""
    source = make_git_project(
        SETUPTOOLS.format(local_scheme="no-local-version"),
        tag="v2026.04.2",
        commits_after_tag=2,
    )
    shallow = tmp_path / "shallow"
    subprocess.run(
        ["git", "clone", "-q", "--depth=1", f"file://{source}", str(shallow)],
        check=True,
        capture_output=True,
    )
    code, report = run_doctor(capsys, shallow)
    assert code == 0
    assert by_code(report)["shallow_checkout"]["severity"] == "warning"


@pytest.mark.unit
def test_broken_build_configuration_fails_and_skips_resolution(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fail on an unusable build configuration; resolution depends on it."""
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\n')
    code, report = run_doctor(capsys, tmp_path)
    checks = by_code(report)
    assert code == 1
    assert report["status"] == "error"
    assert checks["build_config"]["severity"] == "error"
    assert checks["calver_config"]["severity"] == "ok"
    assert "resolution" not in checks


@pytest.mark.e2e
def test_invalid_calver_configuration_does_not_stop_other_checks(
    healthy: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Report a bad CALVER_SCM_* value and still run the remaining checks."""
    monkeypatch.setenv("CALVER_SCM_MODE", "decade")
    code, report = run_doctor(capsys, healthy)
    checks = by_code(report)
    assert code == 1
    assert checks["calver_config"]["severity"] == "error"
    assert checks["build_config"]["severity"] == "ok"
    assert checks["resolution"]["severity"] == "error"


@pytest.mark.unit
def test_resolution_failure_outside_a_repository(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fail when setuptools-scm finds no repository to read."""
    (tmp_path / "pyproject.toml").write_text(
        SETUPTOOLS.format(local_scheme="no-local-version")
    )
    code, report = run_doctor(capsys, tmp_path)
    assert code == 1
    assert by_code(report)["resolution"]["severity"] == "error"


@pytest.mark.e2e
def test_missing_git_is_an_error_but_configuration_checks_still_run(
    healthy: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Report an absent Git executable without hiding the configuration checks."""
    monkeypatch.setattr("calver_scm.diagnostics.shutil.which", lambda _name: None)
    code, report = run_doctor(capsys, healthy)
    checks = by_code(report)
    assert code == 1
    assert checks["git_available"]["severity"] == "error"
    assert checks["calver_config"]["severity"] == "ok"
    assert "shallow_checkout" not in checks


@pytest.mark.unit
@pytest.mark.parametrize(
    ("severities", "expected"),
    [
        ([], Severity.OK),
        ([Severity.OK, Severity.INFO], Severity.OK),
        ([Severity.INFO, Severity.WARNING], Severity.WARNING),
        ([Severity.WARNING, Severity.ERROR, Severity.OK], Severity.ERROR),
    ],
)
def test_report_status_is_the_most_serious_severity(
    severities: list[Severity], expected: Severity
) -> None:
    """Treat informational results as healthy and errors as the worst case."""
    report = DoctorReport(
        tuple(Diagnostic(CheckCode.RESOLUTION, s, "summary") for s in severities)
    )
    assert report.status is expected


@pytest.mark.e2e
def test_plain_and_rich_reports(
    make_git_project: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
    flat: Callable[[str], str],
) -> None:
    """Render summaries, details and fixes in both human formats."""
    project = make_git_project(SETUPTOOLS.format(local_scheme="no-local-version"))
    assert main(["--format", "plain", "doctor", "--root", str(project)]) == 0
    plain = capsys.readouterr().out.splitlines()
    assert "ok build_config: The build uses the calver-scm version scheme" in plain
    assert (
        "warning no_compatible_tag: No tag fits the configured CalVer scheme" in plain
    )
    assert any(line.startswith("  fix: Tag a release") for line in plain)
    assert plain[-1] == "status: warning"

    assert main(["--format", "rich", "doctor", "--root", str(project)]) == 0
    rich = flat(capsys.readouterr().out)
    assert "build_config" in rich
    assert "The build uses the calver-scm version scheme" in rich
    assert "no_compatible_tag" in rich
    assert "→ Tag a release" in rich
    assert "status: warning" in rich
    assert "1 warning" in rich


def _project(
    make_git_project: Callable[..., Path],
    *,
    pyproject: str | None = None,
    settings: str | None = None,
) -> Path:
    """A tagged project with an optional pyproject.toml and calver-scm.toml."""
    build = SETUPTOOLS.format(local_scheme="no-local-version")
    return make_git_project(
        None if pyproject is None else build + pyproject,
        files=None if settings is None else {"calver-scm.toml": settings},
        tag="v2026.04.2",
    )


@pytest.mark.e2e
def test_settings_source_names_pyproject_toml(
    make_git_project: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """Say when settings come from [tool.calver-scm] in pyproject.toml."""
    project = _project(
        make_git_project, pyproject="[tool.calver-scm]\nstable = false\n"
    )
    _, report = run_doctor(capsys, project)
    check = by_code(report)["settings_source"]
    assert check["severity"] == "info"
    assert check["summary"] == "Settings read from pyproject.toml"


@pytest.mark.e2e
def test_settings_source_names_calver_scm_toml_without_a_pyproject(
    make_git_project: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """Work, and say where settings came from, with no pyproject.toml at all."""
    project = _project(make_git_project, settings="stable = false\n")
    code, report = run_doctor(capsys, project)
    assert code == 0
    assert report["status"] == "ok"
    assert (
        by_code(report)["settings_source"]["summary"]
        == "Settings read from calver-scm.toml"
    )


@pytest.mark.e2e
def test_settings_source_names_both_files_in_precedence_order(
    make_git_project: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """List pyproject.toml then calver-scm.toml, the order they are applied."""
    project = _project(
        make_git_project,
        pyproject="[tool.calver-scm]\nstable = false\n",
        settings="stable = false\n",
    )
    _, report = run_doctor(capsys, project)
    checks = by_code(report)
    assert (
        checks["settings_source"]["summary"]
        == "Settings read from pyproject.toml and calver-scm.toml"
    )
    assert "settings_conflict" not in checks


@pytest.mark.e2e
def test_conflicting_settings_warn_without_failing(
    make_git_project: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """Warn about a key set differently in both files; calver-scm.toml wins."""
    project = _project(
        make_git_project,
        pyproject='[tool.calver-scm]\ntag_prefix = "v"\nstable = false\n',
        settings='tag_prefix = "w"\nstable = true\n',
    )
    code, report = run_doctor(capsys, project)
    check = by_code(report)["settings_conflict"]
    assert code == 0
    assert report["status"] == "warning"
    assert check["severity"] == "warning"
    assert check["detail"] == "Keys: stable, tag_prefix. calver-scm.toml wins."
    assert check["remediation"] == "Keep each setting in one file."


@pytest.mark.e2e
def test_invalid_calver_scm_toml_is_a_configuration_error(
    make_git_project: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """Report malformed calver-scm.toml once, not as source or conflict noise."""
    project = _project(make_git_project, pyproject="", settings="stable = \n")
    code, report = run_doctor(capsys, project)
    checks = by_code(report)
    assert code == 1
    assert checks["calver_config"]["severity"] == "error"
    assert "Invalid calver-scm.toml" in checks["calver_config"]["detail"]
    assert "calver-scm.toml" in checks["calver_config"]["remediation"]
    assert "settings_source" not in checks
    assert "settings_conflict" not in checks


@pytest.mark.e2e
def test_env_overrides_are_said_to_override_the_settings_files(
    healthy: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Do not claim the variables only override pyproject.toml."""
    monkeypatch.setenv("CALVER_SCM_NO_DEV", "true")
    _, report = run_doctor(capsys, healthy)
    assert (
        by_code(report)["env_overrides"]["summary"]
        == "CALVER_SCM_* variables override the settings files"
    )


@pytest.mark.e2e
def test_build_configuration_remediation_mentions_calver_scm_toml(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Point at calver-scm.toml as an option when no build setup is found."""
    _, report = run_doctor(capsys, tmp_path)
    assert "calver-scm.toml" in by_code(report)["build_config"]["remediation"]

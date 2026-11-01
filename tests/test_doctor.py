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

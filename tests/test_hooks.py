from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import yaml

from calver_scm.hooks import main

if TYPE_CHECKING:
    from collections.abc import Mapping

ROOT = Path(__file__).resolve().parent.parent


def run_hook(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    project: Path,
    env: Mapping[str, str],
) -> tuple[int, str, str]:
    """Run the pre-push hook from `project` with only the given pre-commit variables."""
    monkeypatch.chdir(project)
    monkeypatch.delenv("PRE_COMMIT_REMOTE_BRANCH", raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    code = main()
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.mark.e2e
def test_a_valid_pushed_tag_passes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Accept a tag that fits the default scheme and prefix."""
    code, out, _ = run_hook(
        monkeypatch,
        capsys,
        tmp_path,
        {"PRE_COMMIT_REMOTE_BRANCH": "refs/tags/v2026.4.2"},
    )
    assert code == 0
    assert "v2026.4.2" in out


@pytest.mark.e2e
def test_an_invalid_pushed_tag_fails_with_the_findings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Stop the push of a tag that does not fit, and say why."""
    code, out, _ = run_hook(
        monkeypatch,
        capsys,
        tmp_path,
        {"PRE_COMMIT_REMOTE_BRANCH": "refs/tags/2026.4.2"},
    )
    assert code == 1
    assert "missing_tag_prefix" in out


@pytest.mark.e2e
def test_the_project_settings_decide_what_is_valid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Read calver-scm.toml from the repository the hook runs in."""
    (tmp_path / "calver-scm.toml").write_text('tag_prefix = "rel-"\n', encoding="utf-8")
    env = {"PRE_COMMIT_REMOTE_BRANCH": "refs/tags/rel-2026.4.2"}
    assert run_hook(monkeypatch, capsys, tmp_path, env)[0] == 0
    env = {"PRE_COMMIT_REMOTE_BRANCH": "refs/tags/v2026.4.2"}
    assert run_hook(monkeypatch, capsys, tmp_path, env)[0] == 1


@pytest.mark.e2e
@pytest.mark.parametrize("ref", ["refs/heads/main", "refs/heads/v2026.99.99", "HEAD"])
def test_pushing_something_other_than_a_tag_is_ignored(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    ref: str,
) -> None:
    """Say nothing about a branch push, even one named like a bad version."""
    code, out, err = run_hook(
        monkeypatch, capsys, tmp_path, {"PRE_COMMIT_REMOTE_BRANCH": ref}
    )
    assert (code, out, err) == (0, "", "")


@pytest.mark.e2e
def test_outside_a_pre_push_hook_it_says_so(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Fail loudly when it is run in a stage that sets no pushed ref."""
    code, out, err = run_hook(monkeypatch, capsys, tmp_path, {})
    assert (code, out) == (2, "")
    assert "pre-push" in err


def load(name: str) -> Any:
    return yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))


@pytest.mark.unit
def test_hook_definitions_point_at_installed_commands() -> None:
    """Keep each hook's entry a console script this package actually installs."""
    hooks = load(".pre-commit-hooks.yaml")
    scripts = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]["scripts"]
    assert [h["id"] for h in hooks] == ["calver-scm-doctor", "calver-scm-validate-tag"]
    for hook in hooks:
        assert hook["entry"].split()[0] in scripts
        assert hook["language"] == "python"
        assert hook["pass_filenames"] is False
        assert hook["always_run"] is True
        assert "pre-push" in hook["stages"]
        assert hook["additional_dependencies"] == [".[cli]"]


def action_script() -> str:
    """The shell script of the action's step that runs calver-scm."""
    steps = load("action.yml")["runs"]["steps"]
    return str(next(s["run"] for s in steps if s.get("id") == "run"))


@pytest.mark.unit
def test_action_never_interpolates_inputs_into_the_shell() -> None:
    """Pass inputs through env so a crafted value cannot become shell code."""
    action = load("action.yml")
    for step in action["runs"]["steps"]:
        if "run" in step:
            assert "${{" not in step["run"]
            assert step["shell"] == "bash"


@pytest.mark.unit
def test_action_inputs_and_outputs_are_documented_and_wired() -> None:
    """Describe every input and output, and take outputs from the run step."""
    action = load("action.yml")
    assert set(action["inputs"]) == {
        "command",
        "tag",
        "pre",
        "strict",
        "against-repo",
        "root",
        "summary",
        "calver-scm-version",
    }
    for spec in action["inputs"].values():
        assert spec["description"]
    run_step = next(s for s in action["runs"]["steps"] if s.get("id") == "run")
    for name, spec in action["outputs"].items():
        assert spec["description"]
        assert spec["value"] == f"${{{{ steps.run.outputs.{name} }}}}"
    for name in action["inputs"]:
        assert f"inputs.{name}" in str(run_step["env"].values())


@pytest.mark.unit
def test_action_installs_uv_from_a_pinned_release() -> None:
    """Use a versioned action, as the repository's own workflows do."""
    steps = load("action.yml")["runs"]["steps"]
    uses = [s["uses"] for s in steps if "uses" in s]
    assert uses
    assert all("@v" in u or ("@" in u and len(u.split("@")[1]) == 40) for u in uses)


STUB = """#!/bin/sh
echo "$(basename "$0") $*"
"""

CASE_ENV = {
    "COMMAND": "doctor",
    "TAG": "",
    "PRE": "",
    "STRICT": "false",
    "AGAINST_REPO": "false",
    "ROOT": ".",
    "SUMMARY": "true",
    "CALVER_SCM_VERSION": "",
}


def run_action(tmp_path: Path, **overrides: str) -> subprocess.CompletedProcess[str]:
    """Run the action's script with `uvx` and `calver-scm` replaced by stubs."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name in ("uvx", "calver-scm"):
        stub = bin_dir / name
        stub.write_text(STUB, encoding="utf-8")
        stub.chmod(0o755)
    script = tmp_path / "step.sh"
    script.write_text(action_script(), encoding="utf-8")
    env = {
        "PATH": f"{bin_dir}{os.pathsep}/usr/bin{os.pathsep}/bin",
        **CASE_ENV,
        **overrides,
    }
    return subprocess.run(
        ["bash", str(script)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


bash_only = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None,
    reason="the action's script needs bash and a POSIX shell",
)


@bash_only
@pytest.mark.unit
@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, "uvx --from calver-scm[cli] calver-scm --summary doctor --root ."),
        (
            {"STRICT": "true"},
            "uvx --from calver-scm[cli] calver-scm --summary doctor --strict --root .",
        ),
        (
            {"SUMMARY": "false"},
            "uvx --from calver-scm[cli] calver-scm doctor --root .",
        ),
        (
            {"COMMAND": "next-tag", "PRE": "rc", "ROOT": "backend"},
            "uvx --from calver-scm[cli] calver-scm --summary --format github "
            "next-tag --pre rc --root backend",
        ),
        (
            {"COMMAND": "next-tag"},
            "uvx --from calver-scm[cli] calver-scm --summary --format github "
            "next-tag --root .",
        ),
        (
            {"COMMAND": "validate", "TAG": "v2026.4.2", "AGAINST_REPO": "true"},
            "uvx --from calver-scm[cli] calver-scm --summary --format github "
            "validate v2026.4.2 --tag --against-repo --root .",
        ),
        (
            {"COMMAND": "parse", "TAG": "v2026.4.2"},
            "uvx --from calver-scm[cli] calver-scm --summary --format github "
            "parse v2026.4.2 --tag --root .",
        ),
        (
            {"COMMAND": "version"},
            "uvx --from calver-scm[cli] calver-scm --summary --format github "
            "version --root .",
        ),
        (
            {"COMMAND": "explain"},
            "uvx --from calver-scm[cli] calver-scm --summary explain --root .",
        ),
        (
            {"COMMAND": "tags"},
            "uvx --from calver-scm[cli] calver-scm --summary tags --root .",
        ),
        (
            {"CALVER_SCM_VERSION": "1.11.1"},
            "uvx --from calver-scm[cli]==1.11.1 calver-scm --summary doctor --root .",
        ),
        (
            {"CALVER_SCM_VERSION": "installed"},
            "calver-scm --summary doctor --root .",
        ),
    ],
    ids=lambda value: value if isinstance(value, str) else "-".join(value.values()),
)
def test_action_builds_the_command_line(
    tmp_path: Path, overrides: dict[str, str], expected: str
) -> None:
    """Turn the inputs into exactly the calver-scm command a workflow would type."""
    result = run_action(tmp_path, **overrides)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected


@bash_only
@pytest.mark.unit
@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"COMMAND": "rm"}, "Unknown command"),
        ({"COMMAND": ""}, "Unknown command"),
        ({"COMMAND": "validate"}, "needs the tag input"),
        ({"COMMAND": "parse", "TAG": ""}, "needs the tag input"),
        ({"COMMAND": "validate", "TAG": "--root"}, "must not start with"),
        ({"CALVER_SCM_VERSION": "1.0 --index-url x"}, "not a version"),
        ({"CALVER_SCM_VERSION": "latest; rm"}, "not a version"),
    ],
)
def test_action_rejects_bad_inputs_before_running_anything(
    tmp_path: Path, overrides: dict[str, str], message: str
) -> None:
    """Fail with a workflow error, and never reach uvx with a hostile value."""
    result = run_action(tmp_path, **overrides)
    assert result.returncode == 2
    assert result.stdout.startswith("::error::")
    assert message in result.stdout
    assert "calver-scm[cli]" not in result.stdout  # the stub was never reached

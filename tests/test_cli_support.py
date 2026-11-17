from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from calver_scm.cli_support import ResolutionError, commits_since, resolve_build_version

if TYPE_CHECKING:
    from pathlib import Path


pytestmark = pytest.mark.unit


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace setuptools-scm's get_version and record the keywords it receives."""
    calls: dict[str, Any] = {}

    def fake_get_version(**kwargs: Any) -> str:
        calls.update(kwargs)
        return "1.2.3"

    monkeypatch.setattr("calver_scm.cli_support.get_version", fake_get_version)
    return calls


def _write(tmp_path: Path, text: str) -> Path:
    (tmp_path / "pyproject.toml").write_text(text, encoding="utf-8")
    return tmp_path


def test_setuptools_table_is_passed_to_get_version(
    tmp_path: Path, captured: dict[str, Any]
) -> None:
    """Hand [tool.setuptools_scm] to setuptools-scm relative to pyproject.toml."""
    root = _write(
        tmp_path,
        """
[project]
name = "demo"
dynamic = ["version"]
[tool.setuptools_scm]
version_scheme = "calver-scm"
local_scheme = "no-local-version"
fallback-version = "0.0.1"
write_to = "demo/_version.py"
root = ".."
""",
    )
    assert resolve_build_version(root) == "1.2.3"
    assert captured == {
        "version_scheme": "calver-scm",
        "local_scheme": "no-local-version",
        "fallback_version": "0.0.1",
        "root": "..",
        "relative_to": root.resolve() / "pyproject.toml",
        "dist_name": "demo",
    }


def test_setuptools_table_without_project_name_or_root(
    tmp_path: Path, captured: dict[str, Any]
) -> None:
    """Default the root to '.' and omit dist_name when there is no project name."""
    root = _write(tmp_path, '[tool.setuptools_scm]\nversion_scheme = "calver-scm"\n')
    resolve_build_version(root)
    assert captured["root"] == "."
    assert "dist_name" not in captured


def test_hatch_vcs_settings_are_translated(
    tmp_path: Path, captured: dict[str, Any]
) -> None:
    """Map Hatch-VCS raw-options, tag-pattern and fallback-version like hatch-vcs."""
    root = _write(
        tmp_path,
        """
[tool.hatch.version]
source = "vcs"
tag-pattern = "^rel-(?P<version>.*)$"
fallback-version = "0.0.1"
[tool.hatch.version.raw-options]
version_scheme = "calver-scm"
local_scheme = "node-and-timestamp"
write_to = "demo/_version.py"
""",
    )
    resolve_build_version(root)
    assert captured == {
        "version_scheme": "calver-scm",
        "local_scheme": "node-and-timestamp",
        "root": str(root.resolve()),
        "tag_regex": "^rel-(?P<version>.*)$",
        "fallback_version": "0.0.1",
    }


def test_hatch_vcs_raw_options_root_wins(
    tmp_path: Path, captured: dict[str, Any]
) -> None:
    """Respect an explicit root in raw-options."""
    root = _write(
        tmp_path,
        """
[tool.hatch.version]
source = "vcs"
[tool.hatch.version.raw-options]
version_scheme = "calver-scm"
root = ".."
""",
    )
    resolve_build_version(root)
    assert captured["root"] == str(root.resolve().parent)


@pytest.mark.parametrize(
    "toml",
    [
        '[tool.setuptools_scm]\nlocal_scheme = "no-local-version"\n',
        '[tool.setuptools_scm]\nversion_scheme = "guess-next-dev"\n',
        '[tool.hatch.version]\nsource = "vcs"\n',
    ],
    ids=["setuptools-default", "setuptools-other", "hatch-default"],
)
def test_other_version_scheme_is_rejected(
    tmp_path: Path, captured: dict[str, Any], toml: str
) -> None:
    """Refuse to report a version produced by a different scheme."""
    with pytest.raises(ResolutionError, match="not 'calver-scm'"):
        resolve_build_version(_write(tmp_path, toml))
    assert captured == {}


def test_missing_build_configuration_is_rejected(
    tmp_path: Path, captured: dict[str, Any]
) -> None:
    """Explain which settings are expected when none are found."""
    root = _write(tmp_path, '[project]\nname = "demo"\n')
    with pytest.raises(ResolutionError, match=r"\[tool\.setuptools_scm\]"):
        resolve_build_version(root)
    assert captured == {}


def test_missing_pyproject_is_rejected(tmp_path: Path) -> None:
    """Report a project directory without pyproject.toml."""
    with pytest.raises(ResolutionError, match=r"No pyproject\.toml"):
        resolve_build_version(tmp_path)


def test_invalid_toml_is_rejected(tmp_path: Path) -> None:
    """Report malformed pyproject.toml instead of raising a raw parser error."""
    with pytest.raises(ResolutionError, match="Invalid TOML"):
        resolve_build_version(_write(tmp_path, "[tool.setuptools_scm"))


def test_scm_lookup_failure_is_wrapped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Turn setuptools-scm's LookupError into a ResolutionError."""

    def failing(**_: Any) -> str:
        raise LookupError("no repository")

    monkeypatch.setattr("calver_scm.cli_support.get_version", failing)
    root = _write(tmp_path, '[tool.setuptools_scm]\nversion_scheme = "calver-scm"\n')
    with pytest.raises(ResolutionError, match="no repository"):
        resolve_build_version(root)


def test_commits_since_reports_an_unreadable_repository(tmp_path: Path) -> None:
    """Raise a resolution error when git cannot compare the tag with HEAD."""
    with pytest.raises(ResolutionError, match="Could not compare v1 with HEAD"):
        commits_since(tmp_path, "v1")


def _write_settings(root: Path, text: str) -> Path:
    (root / "calver-scm.toml").write_text(text, encoding="utf-8")
    return root


def test_options_are_synthesised_from_calver_scm_toml(
    tmp_path: Path, captured: dict[str, Any]
) -> None:
    """Resolve with no pyproject.toml: only the scheme and root are passed."""
    root = _write_settings(tmp_path, "")
    assert resolve_build_version(root) == "1.2.3"
    assert captured == {"version_scheme": "calver-scm", "root": str(root.resolve())}


def test_local_scheme_is_passed_through_from_calver_scm_toml(
    tmp_path: Path, captured: dict[str, Any]
) -> None:
    """Honour local_scheme, the one build option calver-scm.toml may set."""
    root = _write_settings(tmp_path, 'local_scheme = "no-local-version"\n')
    resolve_build_version(root)
    assert captured["local_scheme"] == "no-local-version"


def test_non_string_local_scheme_is_rejected(
    tmp_path: Path, captured: dict[str, Any]
) -> None:
    """Refuse a local_scheme that is not a string before calling setuptools-scm."""
    root = _write_settings(tmp_path, "local_scheme = 3\n")
    with pytest.raises(ResolutionError, match=r"calver-scm\.toml.*local_scheme"):
        resolve_build_version(root)
    assert captured == {}


def test_pyproject_build_section_wins_over_calver_scm_toml(
    tmp_path: Path, captured: dict[str, Any]
) -> None:
    """Mirror the real build: pyproject.toml's build options take priority."""
    root = _write(
        tmp_path,
        '[tool.setuptools_scm]\nversion_scheme = "calver-scm"\n'
        'local_scheme = "dirty-tag"\n',
    )
    _write_settings(root, 'local_scheme = "no-local-version"\n')
    resolve_build_version(root)
    assert captured["local_scheme"] == "dirty-tag"
    assert "relative_to" in captured


def test_pyproject_without_build_section_falls_back_to_calver_scm_toml(
    tmp_path: Path, captured: dict[str, Any]
) -> None:
    """A pyproject.toml that only names the project does not block the fallback."""
    root = _write(tmp_path, '[project]\nname = "demo"\n')
    _write_settings(root, "")
    resolve_build_version(root)
    assert captured == {"version_scheme": "calver-scm", "root": str(root.resolve())}


def test_other_scheme_in_pyproject_is_still_rejected_with_calver_scm_toml(
    tmp_path: Path, captured: dict[str, Any]
) -> None:
    """The real build would not use calver-scm, so the CLI must not pretend to."""
    root = _write(
        tmp_path, '[tool.setuptools_scm]\nversion_scheme = "guess-next-dev"\n'
    )
    _write_settings(root, "")
    with pytest.raises(ResolutionError, match="not 'calver-scm'"):
        resolve_build_version(root)
    assert captured == {}


def test_invalid_calver_scm_toml_is_rejected(tmp_path: Path) -> None:
    """Report malformed calver-scm.toml instead of a raw parser error."""
    root = _write_settings(tmp_path, "stable = \n")
    with pytest.raises(ResolutionError, match=r"Invalid calver-scm\.toml"):
        resolve_build_version(root)


def test_missing_files_error_mentions_both_options(tmp_path: Path) -> None:
    """Tell the user about calver-scm.toml when no configuration exists."""
    with pytest.raises(ResolutionError) as excinfo:
        resolve_build_version(tmp_path)
    assert "pyproject.toml" in str(excinfo.value)
    assert "calver-scm.toml" in str(excinfo.value)


def test_missing_build_section_error_mentions_calver_scm_toml(
    tmp_path: Path,
) -> None:
    """Suggest calver-scm.toml when pyproject.toml has no build section."""
    root = _write(tmp_path, '[project]\nname = "demo"\n')
    with pytest.raises(ResolutionError, match=r"calver-scm\.toml"):
        resolve_build_version(root)

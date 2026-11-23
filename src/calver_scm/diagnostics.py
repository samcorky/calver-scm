from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from calver_scm.cli_support import (
    BuildExplanation,
    ResolutionError,
    _checked_options,
    explain_build_version,
    is_shallow_repository,
    list_local_tags,
    nearest_build_tag,
    scopes_build_tags,
)
from calver_scm.config import (
    CONFIG_FILE_NAME,
    PYPROJECT_FILE_NAME,
    SETTING_ENV_VARS,
    _load_calver_config,
    describe_settings_files,
)
from calver_scm.models import ResolutionReason
from calver_scm.parser import _parse_tag

if TYPE_CHECKING:
    from pathlib import Path

FALLBACK_REASONS = frozenset(
    {ResolutionReason.NO_TAG_FALLBACK, ResolutionReason.INCOMPATIBLE_TAG_FALLBACK}
)


class CheckCode(StrEnum):
    """Stable identifier of one doctor check."""

    BUILD_CONFIG = "build_config"
    CALVER_CONFIG = "calver_config"
    SETTINGS_SOURCE = "settings_source"
    SETTINGS_CONFLICT = "settings_conflict"
    ENV_OVERRIDES = "env_overrides"
    UNKNOWN_ENV_OVERRIDES = "unknown_env_overrides"
    GIT_AVAILABLE = "git_available"
    RESOLUTION = "resolution"
    SHALLOW_CHECKOUT = "shallow_checkout"
    NO_COMPATIBLE_TAG = "no_compatible_tag"
    FOREIGN_BUILD_TAG = "foreign_build_tag"
    DIRTY_TREE = "dirty_tree"
    NO_DEV_LOCAL_SEGMENT = "no_dev_local_segment"


class Severity(StrEnum):
    """How seriously a diagnostic should be taken."""

    OK = "ok"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """The result of one independent check."""

    code: CheckCode
    severity: Severity
    summary: str
    detail: str | None = None
    remediation: str | None = None


@dataclass(frozen=True, slots=True)
class DoctorReport:
    """Every diagnostic produced for a project."""

    diagnostics: tuple[Diagnostic, ...]

    @property
    def status(self) -> Severity:
        """The most serious severity found; informational results count as ok."""
        severities = {d.severity for d in self.diagnostics}
        for level in (Severity.ERROR, Severity.WARNING):
            if level in severities:
                return level
        return Severity.OK


def diagnose(root: Path) -> DoctorReport:
    """Run every check, continuing past independent failures.

    Warnings never make the report fail; only errors do.
    """
    results: list[Diagnostic] = []
    project = root.resolve()

    build_config = _check_build_config(project)
    results.append(build_config)
    calver_config = _check_calver_config(project)
    results.append(calver_config)
    if calver_config.severity is Severity.OK:
        results.extend(_check_settings_files(project))
    results.extend(_check_env_overrides())

    git = shutil.which("git")
    if git is None:
        results.append(
            Diagnostic(
                CheckCode.GIT_AVAILABLE,
                Severity.ERROR,
                "Git was not found on PATH",
                "setuptools-scm needs Git to read tags and commits.",
                "Install Git and make sure it is on PATH.",
            )
        )
    else:
        results.append(
            Diagnostic(CheckCode.GIT_AVAILABLE, Severity.OK, "Git is available")
        )

    if build_config.severity is Severity.OK:
        results.extend(_check_resolution(project, git_available=git is not None))
    return DoctorReport(tuple(results))


def _check_build_config(project: Path) -> Diagnostic:
    try:
        _checked_options(project)
    except ResolutionError as e:
        return Diagnostic(
            CheckCode.BUILD_CONFIG,
            Severity.ERROR,
            "The build configuration cannot be used",
            str(e),
            "Configure [tool.setuptools_scm] or Hatch-VCS with "
            "version_scheme = 'calver-scm', or add a "
            f"{CONFIG_FILE_NAME} to use the CLI without a {PYPROJECT_FILE_NAME}.",
        )
    return Diagnostic(
        CheckCode.BUILD_CONFIG,
        Severity.OK,
        "The build uses the calver-scm version scheme",
    )


def _check_calver_config(project: Path) -> Diagnostic:
    try:
        _load_calver_config(project)
    except RuntimeError as e:
        return Diagnostic(
            CheckCode.CALVER_CONFIG,
            Severity.ERROR,
            "The CalVer configuration is invalid",
            str(e),
            f"Fix [tool.calver-scm] in {PYPROJECT_FILE_NAME}, {CONFIG_FILE_NAME} or "
            "the CALVER_SCM_* variables.",
        )
    return Diagnostic(
        CheckCode.CALVER_CONFIG, Severity.OK, "The CalVer configuration is valid"
    )


def _check_settings_files(project: Path) -> list[Diagnostic]:
    """Say which files supply settings, and warn when they disagree."""
    files = describe_settings_files(project)
    results: list[Diagnostic] = []
    if files.files:
        results.append(
            Diagnostic(
                CheckCode.SETTINGS_SOURCE,
                Severity.INFO,
                f"Settings read from {' and '.join(files.files)}",
            )
        )
    if files.conflicts:
        results.append(
            Diagnostic(
                CheckCode.SETTINGS_CONFLICT,
                Severity.WARNING,
                f"The same setting is defined in both {PYPROJECT_FILE_NAME} and "
                f"{CONFIG_FILE_NAME} with different values",
                f"Keys: {', '.join(files.conflicts)}. {CONFIG_FILE_NAME} wins.",
                "Keep each setting in one file.",
            )
        )
    return results


def _check_env_overrides() -> list[Diagnostic]:
    named = sorted(name for name in os.environ if name.startswith("CALVER_SCM_"))
    active = [name for name in named if name in SETTING_ENV_VARS]
    unknown = [name for name in named if name not in SETTING_ENV_VARS]
    results: list[Diagnostic] = []
    if active:
        results.append(
            Diagnostic(
                CheckCode.ENV_OVERRIDES,
                Severity.INFO,
                "CALVER_SCM_* variables override the settings files",
                ", ".join(f"{name}={os.environ[name]}" for name in active),
            )
        )
    if unknown:
        results.append(
            Diagnostic(
                CheckCode.UNKNOWN_ENV_OVERRIDES,
                Severity.WARNING,
                "CALVER_SCM_* variables that are not settings are ignored",
                ", ".join(unknown),
                "Check the spelling. The settings are "
                + ", ".join(sorted(SETTING_ENV_VARS))
                + ".",
            )
        )
    return results


def _check_resolution(project: Path, *, git_available: bool) -> list[Diagnostic]:
    try:
        explanation = explain_build_version(project)
    except ResolutionError as e:
        return [
            Diagnostic(
                CheckCode.RESOLUTION,
                Severity.ERROR,
                "The version could not be resolved",
                str(e),
                "Run inside a Git repository with its history, or see "
                "'calver-scm explain'.",
            )
        ]

    results = [
        Diagnostic(
            CheckCode.RESOLUTION,
            Severity.OK,
            f"The version resolves to {explanation.version}",
        )
    ]
    if git_available and is_shallow_repository(project):
        results.append(
            Diagnostic(
                CheckCode.SHALLOW_CHECKOUT,
                Severity.WARNING,
                "This is a shallow clone",
                "Tags and commit distance may be missing, so the version can be wrong.",
                "Run 'git fetch --unshallow --tags' (or set fetch-depth: 0 in CI).",
            )
        )
    results.extend(_check_explanation(explanation))
    if git_available:
        results.extend(_check_foreign_build_tag(project, explanation))
    return results


def _check_foreign_build_tag(
    project: Path, explanation: BuildExplanation
) -> list[Diagnostic]:
    """Warn when the build reads another package's tag instead of this one's."""
    if scopes_build_tags(_checked_options(project)):
        return []
    tag = nearest_build_tag(project)
    config = explanation.config
    if tag is None or _parse_tag(tag, config) is not None:
        return []
    if not any(_parse_tag(t, config) for t in list_local_tags(project)):
        return []
    prefix = config.tag_prefix
    command = f"git describe --dirty --tags --long --match {prefix}*"
    return [
        Diagnostic(
            CheckCode.FOREIGN_BUILD_TAG,
            Severity.WARNING,
            "The build reads a tag that is not this project's",
            f"The build uses the tag {tag!r}, which does not start with the "
            f"configured prefix {prefix!r}, so the version is built from "
            "another package's tag.",
            "Limit the tags the build reads. With setuptools-scm add to "
            "pyproject.toml: [tool.setuptools_scm.scm.git] "
            f'describe_command = "{command}"'
            ". With Hatch-VCS add to [tool.hatch.version]: "
            f'raw-options = {{ scm.git.describe_command = "{command}" }}.',
        )
    ]


def _check_explanation(explanation: BuildExplanation) -> list[Diagnostic]:
    resolution = explanation.resolution
    results: list[Diagnostic] = []
    if resolution.reason in FALLBACK_REASONS:
        results.append(
            Diagnostic(
                CheckCode.NO_COMPATIBLE_TAG,
                Severity.WARNING,
                "No tag fits the configured CalVer scheme",
                f"The fallback applied; the tag seen was {resolution.scm.tag!r}.",
                f"Tag a release, for example {explanation.config.tag_prefix}"
                f"{resolution.base}.0, or ignore this if the fallback is intended.",
            )
        )
    if resolution.scm.dirty:
        results.append(
            Diagnostic(
                CheckCode.DIRTY_TREE,
                Severity.INFO,
                "The working tree has uncommitted changes",
                "This is expected during development.",
            )
        )
    if explanation.config.no_dev and explanation.local_segment:
        results.append(
            Diagnostic(
                CheckCode.NO_DEV_LOCAL_SEGMENT,
                Severity.WARNING,
                "no_dev does not remove the local version segment",
                f"The full version still ends in +{explanation.local_segment}.",
                "Use local_scheme = 'no-local-version' if the suffix is unwanted.",
            )
        )
    return results

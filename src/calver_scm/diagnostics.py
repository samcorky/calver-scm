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
)
from calver_scm.config import _load_calver_config
from calver_scm.models import ResolutionReason

if TYPE_CHECKING:
    from pathlib import Path

FALLBACK_REASONS = frozenset(
    {ResolutionReason.NO_TAG_FALLBACK, ResolutionReason.INCOMPATIBLE_TAG_FALLBACK}
)


class CheckCode(StrEnum):
    """Stable identifier of one doctor check."""

    BUILD_CONFIG = "build_config"
    CALVER_CONFIG = "calver_config"
    ENV_OVERRIDES = "env_overrides"
    GIT_AVAILABLE = "git_available"
    RESOLUTION = "resolution"
    SHALLOW_CHECKOUT = "shallow_checkout"
    NO_COMPATIBLE_TAG = "no_compatible_tag"
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
    results.append(_check_calver_config(project))
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
            "version_scheme = 'calver-scm'.",
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
            "Fix [tool.calver-scm] in pyproject.toml or the CALVER_SCM_* variables.",
        )
    return Diagnostic(
        CheckCode.CALVER_CONFIG, Severity.OK, "The CalVer configuration is valid"
    )


def _check_env_overrides() -> list[Diagnostic]:
    active = sorted(name for name in os.environ if name.startswith("CALVER_SCM_"))
    if not active:
        return []
    return [
        Diagnostic(
            CheckCode.ENV_OVERRIDES,
            Severity.INFO,
            "CALVER_SCM_* variables override pyproject.toml",
            ", ".join(f"{name}={os.environ[name]}" for name in active),
        )
    ]


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
    return results


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

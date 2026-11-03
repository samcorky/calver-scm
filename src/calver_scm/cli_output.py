from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from calver_scm.cli_rich import (
    render_explanation,
    render_next_tag,
    render_report,
    render_validation,
    render_version,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from calver_scm.cli_support import BuildExplanation
    from calver_scm.diagnostics import DoctorReport
    from calver_scm.release import NextTag
    from calver_scm.validation import ValidationResult

Payload = dict[str, Any]


class OutputFormat(StrEnum):
    """How command results are written to stdout."""

    AUTO = "auto"
    RICH = "rich"
    PLAIN = "plain"
    JSON = "json"


def resolve_format(requested: OutputFormat, *, is_tty: bool) -> OutputFormat:
    """Pick a concrete format: rich on a terminal, plain when piped or captured."""
    if requested is not OutputFormat.AUTO:
        return requested
    return OutputFormat.RICH if is_tty else OutputFormat.PLAIN


@dataclass(frozen=True, slots=True)
class Output:
    """Writes command results to stdout in one resolved format.

    Every result is a payload dictionary. JSON prints it as is; plain and rich
    are views of the same data, so the three formats cannot disagree. Plain is
    the stable, undecorated format meant for scripts. Errors are not routed
    through here: they always go to stderr as plain text.
    """

    format: OutputFormat

    def version(self, value: str) -> None:
        """Write a resolved version."""
        self._emit({"version": value}, value, render_version)

    def explanation(self, explanation: BuildExplanation) -> None:
        """Write how the build version was derived."""
        payload = _explanation_payload(explanation)
        self._emit(payload, "\n".join(_flatten(payload)), render_explanation)

    def next_tag(self, plan: NextTag) -> None:
        """Write the proposed release tag."""
        payload: Payload = {
            "tag": plan.tag,
            "version": plan.version,
            "patch": plan.patch,
            "reason": plan.reason.value,
            "latest_tag": plan.latest_tag,
            "is_prerelease": plan.is_prerelease,
            "channel": plan.channel.value if plan.channel else None,
        }
        self._emit(payload, plan.tag, render_next_tag)

    def report(self, report: DoctorReport) -> None:
        """Write the doctor diagnostics."""
        payload = _report_payload(report)
        self._emit(payload, "\n".join(_report_plain(payload)), render_report)

    def validation(self, result: ValidationResult) -> None:
        """Write a validation verdict."""
        payload = _validation_payload(result)
        self._emit(payload, "\n".join(_validation_plain(payload)), render_validation)

    def _emit(
        self, payload: Payload, plain: str, rich: Callable[[Payload], None]
    ) -> None:
        match self.format:
            case OutputFormat.JSON:
                print(json.dumps(payload))
            case OutputFormat.RICH:
                rich(payload)
            case _:
                print(plain)


def _validation_payload(result: ValidationResult) -> Payload:
    return {
        "valid": result.valid,
        "input": result.input,
        "errors": [
            {"code": issue.code.value, "message": issue.message}
            for issue in result.issues
        ],
    }


def _validation_plain(payload: Payload) -> list[str]:
    if payload["valid"]:
        return [f"valid: {payload['input']}"]
    lines = [f"invalid: {payload['input']}"]
    lines.extend(f"  {e['code']}: {e['message']}" for e in payload["errors"])
    return lines


def _explanation_payload(explanation: BuildExplanation) -> Payload:
    resolution = explanation.resolution
    config = explanation.config
    return {
        "version": explanation.version,
        "public_version": resolution.public_version,
        "local_segment": explanation.local_segment,
        "reason": resolution.reason.value,
        "scm": {
            "tag": resolution.scm.tag,
            "distance": resolution.scm.distance,
            "dirty": resolution.scm.dirty,
        },
        "calculation": {
            "date": resolution.calculation_date.isoformat(),
            "timezone": config.timezone,
            "base": resolution.base,
            "tag_base": resolution.tag_base,
            "tag_patch": resolution.tag_patch,
            "patch": resolution.patch,
        },
        "config": {
            "mode": config.mode.value,
            "scheme": ".".join(config.scheme_tokens),
            "patch": config.patch,
            "stable": config.stable,
            "no_dev": config.no_dev,
            "fallback": config.fallback.value,
            "tag_prefix": config.tag_prefix,
        },
        "env_overrides": dict(explanation.env_overrides),
    }


def _scalar(value: object) -> str:
    if value is None:
        return "none"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _flatten(payload: Payload) -> list[str]:
    """Render the payload as `key: value` lines, nesting with dotted keys."""
    lines: list[str] = []
    for key, value in payload.items():
        if isinstance(value, dict):
            lines.extend(f"{key}.{inner}: {_scalar(v)}" for inner, v in value.items())
        else:
            lines.append(f"{key}: {_scalar(value)}")
    return lines


def _report_payload(report: DoctorReport) -> Payload:
    return {
        "status": report.status.value,
        "checks": [
            {
                "code": d.code,
                "severity": d.severity.value,
                "summary": d.summary,
                "detail": d.detail,
                "remediation": d.remediation,
            }
            for d in report.diagnostics
        ],
    }


def _report_plain(payload: Payload) -> list[str]:
    lines: list[str] = []
    for check in payload["checks"]:
        lines.append(f"{check['severity']} {check['code']}: {check['summary']}")
        if check["detail"]:
            lines.append(f"  detail: {check['detail']}")
        if check["remediation"]:
            lines.append(f"  fix: {check['remediation']}")
    lines.append(f"status: {payload['status']}")
    return lines

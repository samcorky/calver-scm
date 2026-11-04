from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from calver_scm.cli_rich import (
    render_explanation,
    render_next_tag,
    render_parsed,
    render_report,
    render_tags,
    render_validation,
    render_version,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from calver_scm.cli_support import BuildExplanation
    from calver_scm.diagnostics import DoctorReport
    from calver_scm.release import NextTag, TagInfo
    from calver_scm.validation import ValidationResult

Payload = dict[str, Any]


class OutputFormat(StrEnum):
    """How command results are written to stdout."""

    AUTO = "auto"
    RICH = "rich"
    PLAIN = "plain"
    JSON = "json"
    GITHUB = "github"


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

    The GitHub format appends the payload's top-level scalar values to the
    `github_output` file, which is `$GITHUB_OUTPUT` in Actions, and still prints
    the plain form so the step log shows the result.
    """

    format: OutputFormat
    github_output: Path | None = None

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

    def tags(self, infos: list[TagInfo]) -> None:
        """Write how each local tag reads under the scheme."""
        payload: Payload = {
            "tags": [
                {
                    "tag": info.tag,
                    "kind": info.kind.value,
                    "period": info.period,
                    "patch": info.patch,
                    "counted": info.counted,
                    "reason": info.reason,
                }
                for info in infos
            ]
        }
        self._emit(payload, "\n".join(_tags_plain(payload)), render_tags)

    def report(self, report: DoctorReport) -> None:
        """Write the doctor diagnostics."""
        payload = _report_payload(report)
        self._emit(payload, "\n".join(_report_plain(payload)), render_report)

    def validation(self, result: ValidationResult) -> None:
        """Write a validation verdict."""
        payload = _validation_payload(result)
        self._emit(payload, "\n".join(_validation_plain(payload)), render_validation)

    def parsed(self, result: ValidationResult) -> None:
        """Write the parts of a valid version, or the findings for an invalid one."""
        if not result.valid:
            self.validation(result)
            return
        payload = _validation_payload(result)
        self._emit(payload, "\n".join(_parsed_plain(payload)), render_parsed)

    def _emit(
        self, payload: Payload, plain: str, rich: Callable[[Payload], None]
    ) -> None:
        match self.format:
            case OutputFormat.JSON:
                print(json.dumps(payload))
            case OutputFormat.RICH:
                rich(payload)
            case OutputFormat.GITHUB:
                self._write_github_output(payload)
                print(plain)
            case _:
                print(plain)

    def _write_github_output(self, payload: Payload) -> None:
        if self.github_output is None:  # pragma: no cover - checked by the launcher
            raise RuntimeError("GITHUB_OUTPUT is not set")
        with self.github_output.open("a", encoding="utf-8") as handle:
            for key, value in payload.items():
                if not isinstance(value, dict | list):
                    handle.write(_github_entry(key, _github_value(value)))


def _tags_plain(payload: Payload) -> list[str]:
    """One tab-separated line per tag: tag, kind, period, patch, then any reason."""
    return [
        "\t".join(
            [
                entry["tag"],
                entry["kind"],
                entry["period"] or "-",
                "-" if entry["patch"] is None else str(entry["patch"]),
                *([entry["reason"]] if entry["reason"] else []),
            ]
        )
        for entry in payload["tags"]
    ]


def _github_value(value: object) -> str:
    """Render a scalar as GitHub Actions expects: lowercase booleans, empty for none."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _github_entry(key: str, value: str) -> str:
    """Format one `$GITHUB_OUTPUT` entry, guarding values that span lines.

    A value with a newline could otherwise end its entry early and inject
    another output, so it is written between a random delimiter.
    """
    if "\n" not in value and "\r" not in value:
        return f"{key}={value}\n"
    delimiter = f"ghadelimiter_{uuid.uuid4().hex}"
    return f"{key}<<{delimiter}\n{value}\n{delimiter}\n"


def _validation_payload(result: ValidationResult) -> Payload:
    payload: Payload = {
        "valid": result.valid,
        "input": result.input,
        "errors": [
            {"code": issue.code.value, "message": issue.message}
            for issue in result.issues
        ],
    }
    if result.kind is not None:
        payload["kind"] = result.kind.value
        payload["is_prerelease"] = result.is_prerelease
    if result.parts is not None:
        parts = result.parts
        payload["period"] = parts.period
        payload["date"] = dict(parts.date)
        payload["patch"] = parts.patch
        payload["pre"] = parts.pre
        payload["post"] = parts.post
        payload["dev"] = parts.dev
    return payload


def _parsed_plain(payload: Payload) -> list[str]:
    """One tab-separated line per part; a part the version lacks is empty."""

    def line(name: str, value: object) -> str:
        return f"{name}\t{'' if value is None else value}"

    lines = [line("kind", payload["kind"]), line("period", payload["period"])]
    lines.extend(line(f"date.{token}", n) for token, n in payload["date"].items())
    lines.extend(line(key, payload[key]) for key in ("patch", "pre", "post", "dev"))
    return lines


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

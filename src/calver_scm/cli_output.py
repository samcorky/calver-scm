from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from rich.console import Console
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from calver_scm.cli_support import BuildExplanation
    from calver_scm.diagnostics import DoctorReport
    from calver_scm.models import ResolutionReason
    from calver_scm.release import NextTag
    from calver_scm.validation import ValidationResult


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

    Errors are not routed through here: they always go to stderr as plain text.
    """

    format: OutputFormat

    def version(self, value: str) -> None:
        """Write a resolved version."""
        match self.format:
            case OutputFormat.JSON:
                print(json.dumps({"version": value}))
            case OutputFormat.RICH:
                line = Text.assemble(("Version ", "dim"), (value, "bold green"))
                _console().print(line)
            case _:
                print(value)

    def explanation(self, explanation: BuildExplanation) -> None:
        """Write how the build version was derived."""
        payload = _explanation_payload(explanation)
        match self.format:
            case OutputFormat.JSON:
                print(json.dumps(payload))
            case OutputFormat.RICH:
                _print_explanation_rich(payload, explanation)
            case _:
                print("\n".join(_flatten(payload)))

    def next_tag(self, plan: NextTag) -> None:
        """Write the proposed release tag."""
        match self.format:
            case OutputFormat.JSON:
                print(
                    json.dumps(
                        {
                            "tag": plan.tag,
                            "version": plan.version,
                            "patch": plan.patch,
                            "reason": plan.reason.value,
                            "latest_tag": plan.latest_tag,
                        }
                    )
                )
            case OutputFormat.RICH:
                console = _console()
                console.print(
                    Text.assemble(("Next tag ", "dim"), (plan.tag, "bold green"))
                )
                after = "no earlier release this period"
                if plan.latest_tag:
                    after = f"after {plan.latest_tag}"
                console.print(
                    Text(
                        f"{plan.reason.value.replace('_', ' ')}, {after}",
                        style="italic",
                    )
                )
            case _:
                print(plan.tag)

    def report(self, report: DoctorReport) -> None:
        """Write the doctor diagnostics."""
        match self.format:
            case OutputFormat.JSON:
                print(json.dumps(_report_payload(report)))
            case OutputFormat.RICH:
                _print_report_rich(report)
            case _:
                print("\n".join(_report_plain(report)))

    def validation(self, result: ValidationResult) -> None:
        """Write a validation verdict."""
        match self.format:
            case OutputFormat.JSON:
                print(json.dumps(_validation_payload(result)))
            case OutputFormat.RICH:
                _print_validation_rich(result)
            case _:
                print(_validation_plain(result))


def _console() -> Console:
    # Resolve stdout when printing so redirection and test capture are honoured.
    return Console(highlight=False, soft_wrap=True)


def _validation_payload(result: ValidationResult) -> dict[str, object]:
    return {
        "valid": result.valid,
        "input": result.input,
        "errors": [
            {"code": issue.code.value, "message": issue.message}
            for issue in result.issues
        ],
    }


def _validation_plain(result: ValidationResult) -> str:
    if result.valid:
        return f"valid: {result.input}"
    lines = [f"invalid: {result.input}"]
    lines.extend(f"  {issue.code.value}: {issue.message}" for issue in result.issues)
    return "\n".join(lines)


def _print_validation_rich(result: ValidationResult) -> None:
    console = _console()
    if result.valid:
        console.print(Text.assemble(("✓ valid ", "bold green"), result.input))
        return
    console.print(Text.assemble(("✗ invalid ", "bold red"), result.input))
    table = Table(box=None, show_header=False, pad_edge=False)
    table.add_column(style="yellow", no_wrap=True)
    table.add_column()
    for issue in result.issues:
        table.add_row(issue.code.value, issue.message)
    console.print(table)


REASON_SUMMARIES = {
    "exact_tag": "HEAD is exactly on a clean tag, so the tag's version is used as is.",
    "patch_incremented": (
        "Commits since the tag fall in the current period, so the patch increases."
    ),
    "patch_reset": (
        "The tag is from an earlier period (or patch is disabled), so the patch is 0."
    ),
    "no_tag_fallback": "There is no tag, so the configured fallback applies.",
    "incompatible_tag_fallback": (
        "The tag does not fit the CalVer scheme, so the configured fallback applies."
    ),
}


def _explanation_payload(explanation: BuildExplanation) -> dict[str, object]:
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


def _flatten(payload: dict[str, object]) -> list[str]:
    """Render the payload as `key: value` lines, nesting with dotted keys."""
    lines: list[str] = []
    for key, value in payload.items():
        if isinstance(value, dict):
            lines.extend(f"{key}.{inner}: {_scalar(v)}" for inner, v in value.items())
        else:
            lines.append(f"{key}: {_scalar(value)}")
    return lines


def _print_explanation_rich(
    payload: dict[str, object], explanation: BuildExplanation
) -> None:
    console = _console()
    reason: ResolutionReason = explanation.resolution.reason
    console.print(
        Text.assemble(("Version ", "dim"), (explanation.version, "bold green"))
    )
    console.print(Text(REASON_SUMMARIES[reason.value], style="italic"))
    for section, value in payload.items():
        if not isinstance(value, dict):
            continue
        console.print()
        console.print(Text(section.replace("_", " ").title(), style="bold"))
        table = Table(box=None, show_header=False, pad_edge=False)
        table.add_column(style="cyan", no_wrap=True)
        table.add_column()
        for inner, v in value.items():
            table.add_row(inner, _scalar(v))
        if not value:
            table.add_row("(none)", "")
        console.print(table)
    console.print()
    console.print(
        Text.assemble(
            ("Public version ", "dim"),
            _scalar(payload["public_version"]),
            ("   Local segment ", "dim"),
            _scalar(payload["local_segment"]),
        )
    )


SEVERITY_STYLES = {
    "ok": ("✓", "green"),
    "info": ("i", "cyan"),
    "warning": ("!", "yellow"),
    "error": ("✗", "red"),
}


def _report_payload(report: DoctorReport) -> dict[str, object]:
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


def _report_plain(report: DoctorReport) -> list[str]:
    lines: list[str] = []
    for d in report.diagnostics:
        lines.append(f"{d.severity.value} {d.code}: {d.summary}")
        if d.detail:
            lines.append(f"  detail: {d.detail}")
        if d.remediation:
            lines.append(f"  fix: {d.remediation}")
    lines.append(f"status: {report.status.value}")
    return lines


def _print_report_rich(report: DoctorReport) -> None:
    console = _console()
    for d in report.diagnostics:
        icon, style = SEVERITY_STYLES[d.severity.value]
        console.print(Text.assemble((f"{icon} ", f"bold {style}"), d.summary))
        if d.detail:
            console.print(Text(f"    {d.detail}", style="dim"))
        if d.remediation:
            console.print(Text.assemble(("    fix: ", "bold"), d.remediation))
    icon, style = SEVERITY_STYLES[report.status.value]
    console.print()
    console.print(
        Text.assemble(("Status ", "dim"), (report.status.value, f"bold {style}"))
    )

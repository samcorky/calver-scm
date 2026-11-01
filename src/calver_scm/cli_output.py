from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from rich.console import Console
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
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

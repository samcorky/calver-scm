from __future__ import annotations

from collections import Counter
from typing import Any

from rich import box
from rich.columns import Columns
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from calver_scm.models import ResolutionReason
from calver_scm.release import NextTagReason

Payload = dict[str, Any]

SEVERITY_STYLES = {
    "ok": ("✓", "green"),
    "info": ("i", "cyan"),
    "warning": ("!", "yellow"),
    "error": ("✗", "red"),
}

ARROW = ("  →  ", "dim")
MIN_WIDTH_FOR_COLUMNS = 78


def console() -> Console:
    """Create a console on whatever stdout is now, honouring redirection."""
    return Console(highlight=False)


def version_text(version: str) -> Text:
    """Show the public version in bold green and any local segment dimmed."""
    public, plus, local = version.partition("+")
    text = Text(public, style="bold green")
    if plus:
        text.append(f"+{local}", style="dim")
    return text


def value_text(value: object) -> Text:
    """Style a scalar: booleans as yes/no, missing values as dim 'none'."""
    if value is None:
        return Text("none", style="dim italic")
    if isinstance(value, bool):
        return Text("yes", style="green") if value else Text("no", style="dim")
    return Text(str(value))


def render_version(payload: Payload) -> None:
    """Show a resolved version in a compact panel."""
    console().print(
        Panel.fit(
            version_text(payload["version"]),
            title="version",
            border_style="green",
            box=box.ROUNDED,
            padding=(0, 2),
        )
    )


def render_validation(payload: Payload) -> None:
    """Show a validation verdict, with a table of issues when invalid."""
    subject = Text(payload["input"], style="bold")
    body: RenderableType
    if payload["valid"]:
        body = Text.assemble(("✓ ", "bold green"), subject, ("  is valid", "green"))
        colour = "green"
    else:
        issues = Table.grid(padding=(0, 2))
        issues.add_column(style="yellow", no_wrap=True)
        issues.add_column()
        for error in payload["errors"]:
            issues.add_row(error["code"], error["message"])
        body = Group(Text.assemble(("✗ ", "bold red"), subject), Text(), issues)
        colour = "red"
    console().print(
        Panel.fit(
            body,
            title="valid" if payload["valid"] else "invalid",
            border_style=colour,
            box=box.ROUNDED,
            padding=(0, 2),
        )
    )


def render_explanation(payload: Payload) -> None:
    """Show how a build version was derived, as a summary plus fact panels."""
    out = console()
    scm, calc = payload["scm"], payload["calculation"]
    reason = ResolutionReason(payload["reason"])

    commits = scm["distance"]
    origin = Text(scm["tag"] or "no tag", style="cyan")
    if commits:
        origin.append(f"  +{commits} commit{'s' if commits != 1 else ''}", "dim")
    if scm["dirty"]:
        origin.append("  dirty", "yellow")
    flow = Text.assemble(
        origin,
        ARROW,
        (reason.label.lower(), "yellow"),
        ARROW,
        version_text(payload["public_version"]),
    )
    if payload["local_segment"]:
        flow.append("  +  ", "dim")
        flow.append(payload["local_segment"], "magenta")

    header = Group(
        Text.assemble(("Version  ", "dim"), version_text(payload["version"])),
        Text.assemble(("◆ ", "bold yellow"), (reason.label, "bold")),
        Text(reason.description, style="italic"),
        Text(),
        flow,
    )
    out.print(
        Panel(
            header,
            title="calver-scm explain",
            title_align="left",
            border_style="green",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )

    facts = [
        ("SCM", scm),
        ("Calculation", calc),
        ("Configuration", payload["config"]),
    ]
    # Three equal panels side by side when they fit, otherwise stacked full width.
    side_by_side = out.width >= MIN_WIDTH_FOR_COLUMNS
    width = (out.width - 2) // len(facts) if side_by_side else out.width
    height = max(len(rows) for _, rows in facts) + 2 if side_by_side else None
    panels = [_facts(title, rows, width, height) for title, rows in facts]
    out.print(Columns(panels, padding=(0, 1)) if side_by_side else Group(*panels))

    if payload["env_overrides"]:
        out.print(
            _facts(
                "Environment overrides",
                payload["env_overrides"],
                out.width,
                humanise=False,
            )
        )
    else:
        out.print(Text("No CALVER_SCM_* overrides are set.", style="dim italic"))


def _facts(
    title: str,
    rows: Payload,
    width: int,
    height: int | None = None,
    *,
    humanise: bool = True,
) -> Panel:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="cyan", no_wrap=True)
    table.add_column()
    for key, value in rows.items():
        table.add_row(key.replace("_", " ") if humanise else key, value_text(value))
    return Panel(
        table,
        title=title,
        title_align="left",
        border_style="blue",
        box=box.ROUNDED,
        width=width,
        height=height,
    )


def render_next_tag(payload: Payload) -> None:
    """Show the proposed tag and why it has that number."""
    reason = NextTagReason(payload["reason"])
    lines: list[Text] = [
        Text.assemble(("Next tag  ", "dim"), (payload["tag"], "bold green")),
        Text.assemble(("◆ ", "bold yellow"), (reason.label, "bold")),
        Text(reason.description, style="italic"),
    ]
    if payload["latest_tag"]:
        label = (
            "Promoting"
            if reason is NextTagReason.PROMOTION
            else "Latest pre-release"
            if payload.get("is_prerelease")
            else "Latest release"
        )
        lines.append(Text.assemble((f"{label}  ", "dim"), payload["latest_tag"]))
    console().print(
        Panel.fit(
            Group(*lines),
            title="next-tag",
            border_style="green",
            box=box.ROUNDED,
            padding=(0, 2),
        )
    )


TAG_KIND_STYLES = {
    "final": "green",
    "postrelease": "green",
    "prerelease": "cyan",
    "dev": "cyan",
    "ignored": "yellow",
}


def render_parsed(payload: Payload) -> None:
    """Show the parts of a valid version as a table."""
    rows = [
        ("kind", payload["kind"]),
        ("version", payload["version"]),
        ("period", payload["period"]),
    ]
    rows.extend((f"date.{token}", n) for token, n in payload["date"].items())
    rows.extend(
        (key, payload[key])
        for key in ("patch", "pre", "post", "dev", "stable", "tag_prefix")
    )
    table = Table(box=box.ROUNDED, show_header=False, expand=False)
    table.add_column(style="bold", no_wrap=True)
    table.add_column()
    for name, value in rows:
        table.add_row(name, Text("-", style="dim") if value is None else str(value))
    console().print(
        Panel.fit(
            table,
            title=payload["input"],
            border_style="green",
            box=box.ROUNDED,
            padding=(0, 1),
        )
    )


def render_tags(payload: Payload) -> None:
    """Show every tag with how it is read, and why ignored tags are skipped."""
    if not payload["tags"]:
        console().print(Text("No tags in this repository.", style="dim"))
        return
    table = Table(box=box.ROUNDED, header_style="bold", expand=False)
    table.add_column("Tag", style="bold", no_wrap=True)
    table.add_column("Kind", no_wrap=True)
    table.add_column("Period", no_wrap=True)
    table.add_column("Patch", justify="right", no_wrap=True)
    table.add_column("Note", overflow="fold")
    for entry in payload["tags"]:
        note = entry["reason"] or ("" if entry["counted"] else "not counted")
        table.add_row(
            entry["tag"],
            Text(entry["kind"], style=TAG_KIND_STYLES[entry["kind"]]),
            entry["period"] or "-",
            "-" if entry["patch"] is None else str(entry["patch"]),
            note,
        )
    console().print(table)


def render_report(payload: Payload) -> None:
    """Show doctor results as a grouped table with a status summary."""
    table = Table(box=box.ROUNDED, header_style="bold", expand=False)
    table.add_column("", no_wrap=True, width=1)
    table.add_column("Check", style="bold", no_wrap=True)
    table.add_column("Result", overflow="fold")
    for check in payload["checks"]:
        icon, colour = SEVERITY_STYLES[check["severity"]]
        rows: list[tuple[Text, str, Text]] = [
            (Text(icon, style=f"bold {colour}"), check["code"], Text(check["summary"]))
        ]
        if check["detail"]:
            rows.append((Text(), "", Text(check["detail"], style="dim")))
        if check["remediation"]:
            rows.append((Text(), "", Text(f"→ {check['remediation']}", style="cyan")))
        for position, row in enumerate(rows):
            table.add_row(*row, end_section=position == len(rows) - 1)

    counts = Counter(check["severity"] for check in payload["checks"])
    summary = Text()
    for severity in ("ok", "info", "warning", "error"):
        icon, colour = SEVERITY_STYLES[severity]
        if summary:
            summary.append("   ")
        summary.append(f"{icon} {counts[severity]} {severity}", style=colour)
    status_colour = SEVERITY_STYLES[payload["status"]][1]
    out = console()
    out.print(table)
    out.print(
        Panel.fit(
            summary,
            title=f"status: {payload['status']}",
            border_style=status_colour,
            box=box.ROUNDED,
            padding=(0, 2),
        )
    )

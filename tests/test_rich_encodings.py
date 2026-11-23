from __future__ import annotations

import io
import os
import subprocess
import sys
from typing import TYPE_CHECKING, Any

import pytest
from rich.console import Console

from calver_scm import cli_rich
from calver_scm.cli import main
from calver_scm.cli_rich import render_explanation, render_report, render_validation

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

ENCODINGS = ["utf-8", "cp1252", "cp437", "cp850", "latin-1", "ascii"]

TERMINALS: dict[str, dict[str, Any]] = {
    "pipe": {"force_terminal": False},
    "tty-16": {"force_terminal": True, "color_system": "standard"},
    "tty-truecolor": {"force_terminal": True, "color_system": "truecolor"},
    "monochrome": {"force_terminal": True, "no_color": True},
    "narrow": {"force_terminal": True, "width": 60},
}

CHECKS = [
    {
        "code": code,
        "severity": severity,
        "summary": "s",
        "detail": "d",
        "remediation": "fix it",
    }
    for code, severity in (("a", "ok"), ("b", "info"), ("c", "warning"), ("d", "error"))
]


def render_doctor() -> None:
    render_report({"status": "error", "checks": CHECKS})


def render_valid() -> None:
    render_validation({"valid": True, "input": "2026.4.2", "errors": []})


def render_invalid() -> None:
    render_validation(
        {
            "valid": False,
            "input": "2026.13.1",
            "errors": [{"code": "invalid_month", "message": "Month must be 1-12."}],
        }
    )


EXPLANATION = {
    "version": "2026.4.3.dev3+g1a2b3c4",
    "public_version": "2026.4.3.dev3",
    "local_segment": "g1a2b3c4",
    "reason": "patch_incremented",
    "scm": {"tag": "2026.4.2", "distance": 3, "dirty": True},
    "calculation": {
        "date": "2026-04-15",
        "timezone": "UTC",
        "base": "2026.4",
        "tag_base": "2026.4",
        "tag_patch": 2,
        "patch": 3,
    },
    "config": {"mode": "month", "scheme": "YYYY.MM", "patch": True},
    "config_sources": {"mode": "default", "scheme": "default", "patch": "default"},
    "env_overrides": {"CALVER_SCM_NO_DEV": "true"},
}


def render_explain() -> None:
    render_explanation(EXPLANATION)


RENDERERS: dict[str, Callable[[], None]] = {
    "doctor": render_doctor,
    "valid": render_valid,
    "invalid": render_invalid,
    "explain": render_explain,
}


def strict_console(encoding: str, terminal: dict[str, Any]) -> tuple[Console, Any, Any]:
    """A console on a stream that raises on a character its encoding lacks."""
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding=encoding, errors="strict")
    return Console(file=stream, highlight=False, **terminal), stream, raw


@pytest.mark.unit
@pytest.mark.parametrize("encoding", ENCODINGS)
@pytest.mark.parametrize("terminal", TERMINALS.values(), ids=TERMINALS.keys())
@pytest.mark.parametrize("render", RENDERERS.values(), ids=RENDERERS.keys())
def test_rich_output_encodes(
    encoding: str,
    terminal: dict[str, Any],
    render: Callable[[], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Never write a glyph the console's encoding cannot represent."""
    out, stream, raw = strict_console(encoding, terminal)
    monkeypatch.setattr(cli_rich, "console", lambda: out)
    render()
    stream.flush()
    raw.getvalue().decode(encoding)


@pytest.mark.unit
@pytest.mark.parametrize("encoding", ["cp1252", "ascii"])
def test_ascii_stand_ins_keep_the_meaning(
    encoding: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Show plain stand-ins for the tick, cross and arrow, not blanks."""
    out, stream, raw = strict_console(encoding, TERMINALS["pipe"])
    monkeypatch.setattr(cli_rich, "console", lambda: out)
    render_doctor()
    render_invalid()
    stream.flush()
    text = raw.getvalue().decode(encoding)
    assert "+ 1 ok" in text
    assert "x 1 error" in text
    assert "-> fix it" in text


@pytest.mark.unit
def test_utf8_keeps_the_unicode_glyphs(monkeypatch: pytest.MonkeyPatch) -> None:
    out, stream, raw = strict_console("utf-8", TERMINALS["pipe"])
    monkeypatch.setattr(cli_rich, "console", lambda: out)
    render_doctor()
    stream.flush()
    text = raw.getvalue().decode("utf-8")
    assert "✓ 1 ok" in text
    assert "→ fix it" in text


@pytest.mark.e2e
@pytest.mark.parametrize("encoding", ["cp1252", "ascii"])
def test_next_tag_encodes(
    encoding: str,
    make_git_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cover the next-tag panel, which has its own glyph."""
    project = make_git_project(
        '[project]\nname = "d"\n[tool.calver-scm]\nmode = "month"\n', tag="v2026.4.0"
    )
    out, stream, raw = strict_console(encoding, TERMINALS["tty-16"])
    monkeypatch.setattr(cli_rich, "console", lambda: out)
    assert main(["--format", "rich", "next-tag", "-r", str(project)]) == 0
    stream.flush()
    raw.getvalue().decode(encoding)


@pytest.mark.e2e
@pytest.mark.parametrize("encoding", ["cp1252", "cp437", "ascii"])
def test_doctor_exits_zero_on_a_legacy_code_page(
    encoding: str, make_git_project: Callable[..., Path]
) -> None:
    """Run the real entry point with stdout on a code page, as on Windows."""
    project = make_git_project(
        '[project]\nname = "d"\ndynamic = ["version"]\n'
        '[tool.setuptools_scm]\nversion_scheme = "calver-scm"\n'
        'local_scheme = "no-local-version"\n',
        tag="v2026.4.2",
    )
    script = "import sys; from calver_scm.cli import main; sys.exit(main(sys.argv[1:]))"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            "--format",
            "rich",
            "doctor",
            "-r",
            str(project),
        ],
        env={**os.environ, "PYTHONIOENCODING": encoding},
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert b"UnicodeEncodeError" not in result.stderr

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from calver_scm.cli_rich import (
    render_explanation,
    render_next_tag,
    render_report,
    render_validation,
    render_version,
)

if TYPE_CHECKING:
    from collections.abc import Callable

pytestmark = pytest.mark.unit


def explanation_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "version": "2026.4.3.dev3+g1a2b3c4.d20260415",
        "public_version": "2026.4.3.dev3",
        "local_segment": "g1a2b3c4.d20260415",
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
        "env_overrides": {"CALVER_SCM_NO_DEV": "true"},
    }
    payload.update(overrides)
    return payload


def test_version_panel_shows_the_whole_version(
    capsys: pytest.CaptureFixture[str], flat: Callable[[str], str]
) -> None:
    """Keep the local segment visible, even though it is styled apart."""
    render_version({"version": "2026.4.3.dev3+g1a2b3c4"})
    assert "2026.4.3.dev3+g1a2b3c4" in flat(capsys.readouterr().out)


def test_explanation_shows_the_derivation_flow(
    capsys: pytest.CaptureFixture[str], flat: Callable[[str], str]
) -> None:
    """Trace the tag, commits, dirty state, reason, public version and local part."""
    render_explanation(explanation_payload())
    out = flat(capsys.readouterr().out)
    assert "2026.4.2 +3 commits dirty → patch incremented → 2026.4.3.dev3" in out
    assert "+ g1a2b3c4.d20260415" in out
    assert "Patch incremented" in out
    assert "so the patch moves on by one." in out
    assert "Environment overrides" in out
    assert "CALVER_SCM_NO_DEV true" in out
    assert "No CALVER_SCM_* overrides" not in out


def test_explanation_handles_missing_tag_values_and_a_single_commit(
    capsys: pytest.CaptureFixture[str], flat: Callable[[str], str]
) -> None:
    """Say 'none' for absent values, singularise one commit, and omit empty parts."""
    render_explanation(
        explanation_payload(
            reason="no_tag_fallback",
            local_segment=None,
            scm={"tag": None, "distance": 1, "dirty": False},
            calculation={"tag_base": None, "tag_patch": None},
            env_overrides={},
        )
    )
    out = flat(capsys.readouterr().out)
    assert "no tag +1 commit → no tag, fallback → 2026.4.3.dev3" in out
    assert "+1 commits" not in out
    assert "tag base none" in out
    assert " + g" not in out


def test_explanation_stacks_its_panels_on_a_narrow_terminal(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fall back to one full-width panel per section below 78 columns."""
    monkeypatch.setenv("COLUMNS", "60")
    render_explanation(explanation_payload())
    out = capsys.readouterr().out
    assert max(len(line) for line in out.splitlines()) <= 60
    for title in ("SCM", "Calculation", "Configuration"):
        assert f"─ {title} ─" in out
    side_by_side = [
        line for line in out.splitlines() if "SCM" in line and "Calc" in line
    ]
    assert side_by_side == []


def test_validation_panels(
    capsys: pytest.CaptureFixture[str], flat: Callable[[str], str]
) -> None:
    """Show a tick when valid and each issue with its code when not."""
    render_validation({"valid": True, "input": "2026.4.2", "errors": []})
    assert "✓ 2026.4.2 is valid" in flat(capsys.readouterr().out)
    render_validation(
        {
            "valid": False,
            "input": "2026.13.1",
            "errors": [{"code": "invalid_month", "message": "Month must be 1 to 12."}],
        }
    )
    out = flat(capsys.readouterr().out)
    assert "✗ 2026.13.1" in out
    assert "invalid_month Month must be 1 to 12." in out


def test_next_tag_panel_with_and_without_a_latest_release(
    capsys: pytest.CaptureFixture[str], flat: Callable[[str], str]
) -> None:
    """Mention the latest release only when there is one."""
    render_next_tag(
        {"tag": "v2026.4.3", "reason": "next_patch", "latest_tag": "v2026.4.2"}
    )
    out = flat(capsys.readouterr().out)
    assert "Next tag v2026.4.3" in out
    assert "Latest release v2026.4.2" in out
    render_next_tag({"tag": "v2026.4.0", "reason": "new_period", "latest_tag": None})
    assert "Latest release" not in flat(capsys.readouterr().out)


def test_report_table_summarises_by_severity(
    capsys: pytest.CaptureFixture[str], flat: Callable[[str], str]
) -> None:
    """Group each check's detail and fix under it and count the severities."""
    render_report(
        {
            "status": "error",
            "checks": [
                {
                    "code": "a",
                    "severity": "ok",
                    "summary": "fine",
                    "detail": None,
                    "remediation": None,
                },
                {
                    "code": "b",
                    "severity": "error",
                    "summary": "broken",
                    "detail": "why",
                    "remediation": "do this",
                },
            ],
        }
    )
    out = flat(capsys.readouterr().out)
    assert "a fine" in out
    assert "b broken" in out
    assert "why" in out
    assert "→ do this" in out
    assert "status: error" in out
    assert "✓ 1 ok" in out
    assert "✗ 1 error" in out

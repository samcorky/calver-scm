from __future__ import annotations

import pytest

from calver_scm.cli_output import OutputFormat, resolve_format

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("requested", "is_tty", "expected"),
    [
        (OutputFormat.AUTO, True, OutputFormat.RICH),
        (OutputFormat.AUTO, False, OutputFormat.PLAIN),
        (OutputFormat.PLAIN, True, OutputFormat.PLAIN),
        (OutputFormat.RICH, False, OutputFormat.RICH),
        (OutputFormat.JSON, True, OutputFormat.JSON),
        (OutputFormat.JSON, False, OutputFormat.JSON),
    ],
)
def test_resolve_format(
    requested: OutputFormat, is_tty: bool, expected: OutputFormat
) -> None:
    """Only auto depends on the terminal; explicit choices always win."""
    assert resolve_format(requested, is_tty=is_tty) is expected


def test_every_resolution_reason_has_a_summary() -> None:
    """Keep the human summaries in step with the engine's reasons."""
    from calver_scm.cli_output import REASON_SUMMARIES
    from calver_scm.models import ResolutionReason

    assert set(REASON_SUMMARIES) == {reason.value for reason in ResolutionReason}

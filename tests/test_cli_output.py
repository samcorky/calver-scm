from __future__ import annotations

import pytest

from calver_scm.cli_output import OutputFormat, resolve_format
from calver_scm.models import ResolutionReason
from calver_scm.release import NextTagReason

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


@pytest.mark.parametrize(
    "reason",
    [*ResolutionReason, *NextTagReason],
    ids=lambda reason: f"{type(reason).__name__}.{reason.name}",
)
def test_every_reason_has_a_label_and_a_sentence(
    reason: ResolutionReason | NextTagReason,
) -> None:
    """Give every reason human wording; a new member without text fails here."""
    assert reason.label
    assert reason.description.endswith(".")


def test_reason_labels_are_distinct_within_each_enum() -> None:
    """Keep the labels distinguishable in the explain flow line."""
    for labels in (
        [reason.label for reason in ResolutionReason],
        [reason.label for reason in NextTagReason],
    ):
        assert len(set(labels)) == len(labels)

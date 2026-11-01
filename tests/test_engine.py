from __future__ import annotations

import datetime as dt

import pytest

from calver_scm.config import CalverConfig
from calver_scm.engine import resolve_version
from calver_scm.models import ResolutionReason, ScmContext

pytestmark = pytest.mark.unit

APR = dt.date(2026, 4, 15)
MAY = dt.date(2026, 5, 1)


@pytest.mark.parametrize(
    ("scm", "config", "today", "version", "reason"),
    [
        (
            ScmContext(None, 12, False),
            CalverConfig(),
            APR,
            "2026.4.0.dev12",
            ResolutionReason.NO_TAG_FALLBACK,
        ),
        (
            ScmContext("garbage", 5, False),
            CalverConfig(),
            APR,
            "2026.4.0.dev5",
            ResolutionReason.INCOMPATIBLE_TAG_FALLBACK,
        ),
        (
            ScmContext("2026.4.2.5.6", 0, False),
            CalverConfig(),
            APR,
            "2026.4.0.dev0",
            ResolutionReason.INCOMPATIBLE_TAG_FALLBACK,
        ),
        (
            ScmContext("2026.4.2", 0, False),
            CalverConfig(),
            MAY,
            "2026.4.2",
            ResolutionReason.EXACT_TAG,
        ),
        (
            ScmContext("2026.4.2", 3, False),
            CalverConfig(),
            APR,
            "2026.4.3.dev3",
            ResolutionReason.PATCH_INCREMENTED,
        ),
        (
            ScmContext("2026.4.2", 0, True),
            CalverConfig(),
            APR,
            "2026.4.3.dev0",
            ResolutionReason.PATCH_INCREMENTED,
        ),
        (
            ScmContext("2026.4.2", 3, False),
            CalverConfig(),
            MAY,
            "2026.5.0.dev3",
            ResolutionReason.PATCH_RESET,
        ),
        (
            ScmContext("2026.4.2", 3, False),
            CalverConfig(patch=False),
            APR,
            "2026.4.0.dev3",
            ResolutionReason.PATCH_RESET,
        ),
    ],
)
def test_resolve_version_reports_the_branch_taken(
    scm: ScmContext,
    config: CalverConfig,
    today: dt.date,
    version: str,
    reason: ResolutionReason,
) -> None:
    """Return the public version together with the branch that produced it."""
    resolution = resolve_version(scm, config, today=today)
    assert resolution.public_version == version
    assert resolution.reason is reason
    assert resolution.scm is scm
    assert resolution.calculation_date == today


def test_resolve_version_is_deterministic() -> None:
    """Equal inputs give equal results."""
    scm = ScmContext("2026.4.2", 3, False)
    config = CalverConfig()
    assert resolve_version(scm, config, today=APR) == resolve_version(
        scm, config, today=APR
    )

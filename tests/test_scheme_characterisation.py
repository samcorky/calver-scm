"""Golden table pinning current `calver_scm` output for every decision branch.

Captured before the engine extraction so the refactor can be checked for
behavioural drift. Each row is (config, tag, distance, dirty, today, expected).
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

import pytest

from calver_scm.scheme import calver_scm

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


pytestmark = pytest.mark.e2e

APR = dt.date(2026, 4, 15)
MAY = dt.date(2026, 5, 1)

MONTH = 'mode = "month"'
UNSTABLE = 'mode = "month"\nstable = false'
FALLBACK_DATE = 'mode = "month"\nfallback = "date"'

GOLDEN = [
    # no tag -> fallback
    pytest.param(MONTH, None, 12, False, APR, "2026.4.0.dev12", id="no-tag-dev"),
    pytest.param(FALLBACK_DATE, None, 4, False, APR, "2026.4.0", id="no-tag-date"),
    pytest.param(
        UNSTABLE, None, 4, False, APR, "0.2026.4.0.dev4", id="no-tag-unstable"
    ),
    # unparsable tag -> fallback
    pytest.param(MONTH, "garbage", 5, False, APR, "2026.4.0.dev5", id="unparsable"),
    # parseable tag without usable release components -> fallback, even if exact
    pytest.param(
        MONTH,
        "v2026.04.2.5.6",
        0,
        False,
        APR,
        "2026.4.0.dev0",
        id="no-components-exact",
    ),
    pytest.param(
        MONTH,
        "v2026.04.2.5.6",
        3,
        False,
        APR,
        "2026.4.0.dev3",
        id="no-components-ahead",
    ),
    # exact clean tag -> normalised tag, even for a historical period
    pytest.param(MONTH, "v2026.04.2", 0, False, APR, "2026.4.2", id="exact"),
    pytest.param(MONTH, "v2025.01.1", 0, False, APR, "2025.1.1", id="exact-historical"),
    pytest.param(
        UNSTABLE, "v0.2026.04.2", 0, False, APR, "0.2026.4.2", id="exact-unstable"
    ),
    # dirty at an exact tag takes the dev path
    pytest.param(
        MONTH, "v2026.04.2", 0, True, APR, "2026.4.3.dev0", id="dirty-exact-same"
    ),
    pytest.param(
        MONTH, "v2026.04.2", 0, True, MAY, "2026.5.0.dev0", id="dirty-exact-rollover"
    ),
    # ahead of tag: same period increments patch, new period resets it
    pytest.param(
        MONTH, "v2026.04.2", 3, False, APR, "2026.4.3.dev3", id="ahead-same-period"
    ),
    pytest.param(
        MONTH, "v2026.04.2", 3, False, MAY, "2026.5.0.dev3", id="ahead-new-period"
    ),
    pytest.param(
        UNSTABLE, "v0.2026.04.2", 2, False, APR, "0.2026.4.3.dev2", id="ahead-unstable"
    ),
    # patch=false keeps patch at zero even in the same period
    pytest.param(
        f"{MONTH}\npatch = false",
        "v2026.04.2",
        3,
        False,
        APR,
        "2026.4.0.dev3",
        id="patch-false",
    ),
    # no_dev drops the public dev suffix on every dev-producing path
    pytest.param(
        f"{MONTH}\nno_dev = true",
        "v2026.04.2",
        3,
        False,
        APR,
        "2026.4.3",
        id="no-dev-ahead",
    ),
    pytest.param(
        f"{MONTH}\nno_dev = true", None, 12, False, APR, "2026.4.0", id="no-dev-no-tag"
    ),
    # PEP 440 suffixes survive on an exact tag
    pytest.param(
        MONTH,
        "v2026.04.2rc1.post2.dev3+abc",
        0,
        False,
        APR,
        "2026.4.2rc1.post2.dev3+abc",
        id="exact-pep440-suffixes",
    ),
]


@pytest.mark.parametrize(
    ("toml", "tag", "distance", "dirty", "today", "expected"), GOLDEN
)
def test_golden_output(
    write_pyproject: Callable[[str], Path],
    make_scm_version: Callable[..., Any],
    set_today: Callable[[dt.date], None],
    toml: str,
    tag: str | None,
    distance: int,
    dirty: bool,
    today: dt.date,
    expected: str,
) -> None:
    """Pin the public version for each decision branch of the scheme."""
    root = write_pyproject(toml)
    set_today(today)
    version = make_scm_version(root=root, tag=tag, distance=distance, dirty=dirty)
    assert calver_scm(version) == expected

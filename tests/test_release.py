from __future__ import annotations

import datetime as dt

import pytest

from calver_scm.config import CalverConfig, CalverMode
from calver_scm.release import NextTagError, NextTagReason, plan_next_tag

pytestmark = pytest.mark.unit

APR = dt.date(2026, 4, 15)
MONTH = CalverConfig()


@pytest.mark.parametrize(
    ("tags", "config", "tag", "reason", "latest"),
    [
        ([], MONTH, "v2026.4.0", NextTagReason.NEW_PERIOD, None),
        (
            ["v2026.3.7", "v2025.4.2"],
            MONTH,
            "v2026.4.0",
            NextTagReason.NEW_PERIOD,
            None,
        ),
        (
            ["v2026.4.0", "v2026.4.2"],
            MONTH,
            "v2026.4.3",
            NextTagReason.NEXT_PATCH,
            "v2026.4.2",
        ),
        (
            ["v2026.4.0", "v2026.4.5"],
            MONTH,
            "v2026.4.6",
            NextTagReason.NEXT_PATCH,
            "v2026.4.5",
        ),
        (
            ["v2026.4.1rc1", "v2026.4.1.dev3"],
            MONTH,
            "v2026.4.0",
            NextTagReason.NEW_PERIOD,
            None,
        ),
        (
            ["v2026.4.1.post1"],
            MONTH,
            "v2026.4.2",
            NextTagReason.NEXT_PATCH,
            "v2026.4.1.post1",
        ),
        (["v2026.04.3"], MONTH, "v2026.4.4", NextTagReason.NEXT_PATCH, "v2026.04.3"),
        (["2026.4.1"], MONTH, "v2026.4.2", NextTagReason.NEXT_PATCH, "2026.4.1"),
        (["v2026.4"], MONTH, "v2026.4.1", NextTagReason.NEXT_PATCH, "v2026.4"),
        (
            ["junk", "v2026.4.2.5.6", "other-v2026.4.9"],
            MONTH,
            "v2026.4.0",
            NextTagReason.NEW_PERIOD,
            None,
        ),
        (
            ["release-2026.4.3"],
            CalverConfig(tag_prefix="release-"),
            "release-2026.4.4",
            NextTagReason.NEXT_PATCH,
            "release-2026.4.3",
        ),
        (
            ["v0.2026.4.1"],
            CalverConfig(stable=False),
            "v0.2026.4.2",
            NextTagReason.NEXT_PATCH,
            "v0.2026.4.1",
        ),
        (
            ["v2026.16.1"],
            CalverConfig(mode=CalverMode.WEEK),
            "v2026.16.2",
            NextTagReason.NEXT_PATCH,
            "v2026.16.1",
        ),
        (
            ["v2026.4.15.0", "v2026.4.14.5"],
            CalverConfig(mode=CalverMode.DAY),
            "v2026.4.15.1",
            NextTagReason.NEXT_PATCH,
            "v2026.4.15.0",
        ),
        (
            ["v2026.3.4"],
            CalverConfig(patch=False),
            "v2026.4.0",
            NextTagReason.NEW_PERIOD,
            None,
        ),
    ],
    ids=[
        "no-tags",
        "other-periods-only",
        "next-patch",
        "gap-in-patches",
        "prereleases-occupy-nothing",
        "post-release-occupies-its-patch",
        "zero-padded-legacy-tag",
        "unprefixed-legacy-tag",
        "tag-without-patch",
        "unusable-tags-ignored",
        "custom-prefix",
        "unstable",
        "week-mode",
        "day-mode",
        "patch-false-new-period",
    ],
)
def test_plan_next_tag(
    tags: list[str],
    config: CalverConfig,
    tag: str,
    reason: NextTagReason,
    latest: str | None,
) -> None:
    """Propose the next free number in the current period."""
    plan = plan_next_tag(tags, config, today=APR)
    assert plan.tag == tag
    assert plan.reason is reason
    assert plan.latest_tag == latest
    assert plan.tag == f"{config.tag_prefix}{plan.version}"


def test_patch_false_refuses_a_second_release_in_the_period() -> None:
    """Fail rather than silently reuse the period's only release number."""
    with pytest.raises(NextTagError) as excinfo:
        plan_next_tag(["v2026.4.0"], CalverConfig(patch=False), today=APR)
    assert excinfo.value.code == "period_already_released"
    assert "v2026.4.0 already exists for 2026.4" in excinfo.value.message


def test_planning_does_not_depend_on_tag_order() -> None:
    """Choose the highest patch whatever order the tags arrive in."""
    forward = plan_next_tag(["v2026.4.1", "v2026.4.9", "v2026.4.3"], MONTH, today=APR)
    reverse = plan_next_tag(["v2026.4.3", "v2026.4.9", "v2026.4.1"], MONTH, today=APR)
    assert forward == reverse
    assert forward.tag == "v2026.4.10"

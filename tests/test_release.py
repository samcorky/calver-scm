from __future__ import annotations

import datetime as dt

import pytest

from calver_scm.config import CalverConfig, CalverMode
from calver_scm.release import (
    NextTagError,
    NextTagReason,
    PreReleaseChannel,
    plan_next_tag,
)

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


@pytest.mark.parametrize(
    ("tags", "config", "channel", "tag", "reason", "latest"),
    [
        ([], MONTH, "rc", "v2026.4.0rc1", NextTagReason.NEW_PRERELEASE, None),
        (
            ["v2026.4.2"],
            MONTH,
            "rc",
            "v2026.4.3rc1",
            NextTagReason.NEW_PRERELEASE,
            None,
        ),
        (
            ["v2026.4.2", "v2026.4.3rc1", "v2026.4.3rc2"],
            MONTH,
            "rc",
            "v2026.4.3rc3",
            NextTagReason.NEXT_PRERELEASE,
            "v2026.4.3rc2",
        ),
        # Channels are counted separately, so a lower channel restarts at 1.
        (
            ["v2026.4.3rc1", "v2026.4.3a2"],
            MONTH,
            "b",
            "v2026.4.0b1",
            NextTagReason.NEW_PRERELEASE,
            None,
        ),
        # Only the next final patch's candidates count; dev releases occupy nothing.
        (
            ["v2026.4.0", "v2026.4.0rc4", "v2026.4.1rc2.dev1", "v2026.3.9rc7"],
            MONTH,
            "rc",
            "v2026.4.1rc1",
            NextTagReason.NEW_PRERELEASE,
            None,
        ),
        (
            ["v2026.4.0rc2.post1", "junk"],
            MONTH,
            "rc",
            "v2026.4.0rc3",
            NextTagReason.NEXT_PRERELEASE,
            "v2026.4.0rc2.post1",
        ),
    ],
)
def test_plan_next_tag_pre(
    tags: list[str],
    config: CalverConfig,
    channel: str,
    tag: str,
    reason: NextTagReason,
    latest: str | None,
) -> None:
    """Number a pre-release per period, next final patch and channel."""
    plan = plan_next_tag(tags, config, today=APR, pre=PreReleaseChannel(channel))
    assert (plan.tag, plan.reason, plan.latest_tag) == (tag, reason, latest)
    assert plan.is_prerelease
    assert plan.channel is PreReleaseChannel(channel)


def test_plan_next_tag_pre_honours_the_stability_prefix_and_tag_prefix() -> None:
    """Apply the same prefixes as a final tag."""
    config = CalverConfig(stable=False, tag_prefix="rel-")
    plan = plan_next_tag(
        ["rel-0.2026.4.0rc1"], config, today=APR, pre=PreReleaseChannel.RC
    )
    assert plan.tag == "rel-0.2026.4.0rc2"
    assert plan.version == "0.2026.4.0rc2"


def test_plan_next_tag_pre_refuses_a_released_period_without_patches() -> None:
    """Raise the same error as a final tag."""
    with pytest.raises(NextTagError) as error:
        plan_next_tag(
            ["v2026.4"],
            CalverConfig(patch=False),
            today=APR,
            pre=PreReleaseChannel.RC,
        )
    assert error.value.code == "period_already_released"


def test_plan_next_tag_final_is_not_a_prerelease() -> None:
    """Leave the pre-release fields empty on a final proposal."""
    plan = plan_next_tag([], MONTH, today=APR)
    assert (plan.is_prerelease, plan.channel) == (False, None)


@pytest.mark.parametrize(
    ("tags", "tag", "latest"),
    [
        (["v2026.4.2", "v2026.4.3rc1"], "v2026.4.3", "v2026.4.3rc1"),
        # Highest in PEP 440 order wins across channels, ignoring dev releases.
        (
            ["v2026.4.3a5", "v2026.4.3rc2", "v2026.4.3b9", "v2026.4.3rc3.dev1"],
            "v2026.4.0",
            None,
        ),
        (
            ["v2026.4.0a5", "v2026.4.0rc2", "v2026.4.0b9", "v2026.4.0rc3.dev1"],
            "v2026.4.0",
            "v2026.4.0rc2",
        ),
    ],
)
def test_plan_next_tag_promote(tags: list[str], tag: str, latest: str | None) -> None:
    """Finalise the latest pre-release of the next final patch."""
    if latest is None:
        with pytest.raises(NextTagError) as error:
            plan_next_tag(tags, MONTH, today=APR, promote=True)
        assert error.value.code == "no_prerelease"
        return
    plan = plan_next_tag(tags, MONTH, today=APR, promote=True)
    assert (plan.tag, plan.reason, plan.latest_tag) == (
        tag,
        NextTagReason.PROMOTION,
        latest,
    )
    assert not plan.is_prerelease


def test_plan_next_tag_promote_refuses_a_released_period_without_patches() -> None:
    """Share the final tag's refusal."""
    with pytest.raises(NextTagError) as error:
        plan_next_tag(
            ["v2026.4", "v2026.4rc1"],
            CalverConfig(patch=False),
            today=APR,
            promote=True,
        )
    assert error.value.code == "period_already_released"


def test_plan_next_tag_rejects_pre_with_promote() -> None:
    """Treat the two modes as mutually exclusive."""
    with pytest.raises(ValueError, match="mutually exclusive"):
        plan_next_tag([], MONTH, today=APR, pre=PreReleaseChannel.RC, promote=True)


@pytest.mark.parametrize(
    ("tags", "config", "tag", "reason", "latest"),
    [
        (
            ["v2026.4.0", "v2026.4.2"],
            MONTH,
            "v2026.4.2.post1",
            NextTagReason.NEW_POSTRELEASE,
            "v2026.4.2",
        ),
        (
            ["v2026.4.2", "v2026.4.2.post1", "v2026.4.2.post3", "v2026.4.1.post9"],
            MONTH,
            "v2026.4.2.post4",
            NextTagReason.NEXT_POSTRELEASE,
            "v2026.4.2.post3",
        ),
        # Pre-releases and dev releases are not releases to post against.
        (
            ["v2026.4.1", "v2026.4.2rc1", "v2026.4.2rc1.post1", "v2026.4.1.post2.dev1"],
            MONTH,
            "v2026.4.1.post1",
            NextTagReason.NEW_POSTRELEASE,
            "v2026.4.1",
        ),
        # patch = false still allows a post-release of the period's one release.
        (
            ["v2026.4"],
            CalverConfig(patch=False),
            "v2026.4.0.post1",
            NextTagReason.NEW_POSTRELEASE,
            "v2026.4",
        ),
    ],
)
def test_plan_next_tag_post(
    tags: list[str],
    config: CalverConfig,
    tag: str,
    reason: NextTagReason,
    latest: str,
) -> None:
    """Add a post-release to the latest release of the period."""
    plan = plan_next_tag(tags, config, today=APR, post=True)
    assert (plan.tag, plan.reason, plan.latest_tag) == (tag, reason, latest)
    assert not plan.is_prerelease


def test_plan_next_tag_post_honours_the_prefixes() -> None:
    """Apply the stability and tag prefixes like any other proposal."""
    config = CalverConfig(stable=False, tag_prefix="rel-")
    plan = plan_next_tag(["rel-0.2026.4.1"], config, today=APR, post=True)
    assert (plan.tag, plan.version) == ("rel-0.2026.4.1.post1", "0.2026.4.1.post1")


@pytest.mark.parametrize("tags", [[], ["v2026.3.4", "v2026.4.1rc1"]])
def test_plan_next_tag_post_needs_a_release_in_the_period(tags: list[str]) -> None:
    """Fail rather than invent a release to post against."""
    with pytest.raises(NextTagError) as error:
        plan_next_tag(tags, MONTH, today=APR, post=True)
    assert error.value.code == "no_release"

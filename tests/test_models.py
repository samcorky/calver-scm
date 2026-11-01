from __future__ import annotations

import dataclasses
import datetime as dt

import pytest

from calver_scm.models import ResolutionReason, ScmContext, VersionResolution

pytestmark = pytest.mark.unit


def test_scm_context_is_frozen_and_slotted() -> None:
    """Reject attribute mutation and per-instance dicts."""
    scm = ScmContext(tag="2026.4.2", distance=3, dirty=False)
    with pytest.raises(dataclasses.FrozenInstanceError):
        scm.distance = 4  # type: ignore[misc]
    assert not hasattr(scm, "__dict__")


def test_version_resolution_is_frozen_and_hashable() -> None:
    """Keep results immutable and usable as values."""
    scm = ScmContext(tag=None, distance=1, dirty=False)
    resolution = VersionResolution(
        public_version="2026.4.0.dev1",
        reason=ResolutionReason.NO_TAG_FALLBACK,
        scm=scm,
        calculation_date=dt.date(2026, 4, 15),
        base="2026.4",
        tag_base=None,
        tag_patch=None,
        patch=0,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        resolution.public_version = "x"  # type: ignore[misc]
    assert hash(resolution) == hash(dataclasses.replace(resolution))


def test_resolution_reason_values_are_stable() -> None:
    """Pin the machine-readable reason strings."""
    assert {reason.value for reason in ResolutionReason} == {
        "no_tag_fallback",
        "incompatible_tag_fallback",
        "exact_tag",
        "patch_incremented",
        "patch_reset",
    }

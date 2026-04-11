from __future__ import annotations

import pytest

from calver_scm.config import CalverConfig, CalverMode

# noinspection PyProtectedMember
from calver_scm.parser import _parse_tag, _release_components

pytestmark = pytest.mark.unit


def test_parse_tag_strips_prefix_and_parses_version() -> None:
    """Parse prefixed tags into CalverVersion objects."""
    cfg = CalverConfig(tag_prefix="release-")
    parsed = _parse_tag("release-2026.04.2", cfg)
    assert parsed is not None
    assert str(parsed) == "2026.4.2"


def test_parse_tag_returns_none_for_invalid_versions() -> None:
    """Return None instead of raising when tag text is not a valid version."""
    cfg = CalverConfig()
    assert _parse_tag("vnot-a-version", cfg) is None


def test_release_components_for_month_with_patch() -> None:
    """Extract month date parts and patch when patch is present."""
    cfg = CalverConfig(mode=CalverMode.MONTH)
    parsed = _parse_tag("v2026.04.3", cfg)
    assert parsed is not None
    assert _release_components(parsed, cfg) == ((2026, 4), 3)


def test_release_components_for_month_without_patch_defaults_zero() -> None:
    """Treat date-only releases as patch zero."""
    cfg = CalverConfig(mode=CalverMode.MONTH)
    parsed = _parse_tag("v2026.04", cfg)
    assert parsed is not None
    assert _release_components(parsed, cfg) == ((2026, 4), 0)


def test_release_components_for_day_with_patch() -> None:
    """Extract day date parts with trailing patch value."""
    cfg = CalverConfig(mode=CalverMode.DAY)
    parsed = _parse_tag("v2026.04.15.4", cfg)
    assert parsed is not None
    assert _release_components(parsed, cfg) == ((2026, 4, 15), 4)


def test_release_components_returns_none_when_release_shape_is_incompatible() -> None:
    """Reject parsed versions that do not match configured scheme arity."""
    cfg = CalverConfig(mode=CalverMode.DAY)
    parsed = _parse_tag("v2026.04", cfg)
    assert parsed is not None
    assert _release_components(parsed, cfg) is None

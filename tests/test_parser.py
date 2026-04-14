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


def test_parse_tag_rejects_unstable_prefix_when_stable_true() -> None:
    """Reject tags that accidentally keep the unstable `0.` prefix in stable mode."""
    cfg = CalverConfig(mode=CalverMode.MONTH, stable=True)
    assert _parse_tag("v0.2026.04", cfg) is None


def test_parse_tag_rejects_clear_unstable_prefix_for_short_year_scheme() -> None:
    """Reject unambiguous unstable prefixes even when the scheme starts with `YY`."""
    cfg = CalverConfig(scheme="YY.0M", stable=True)
    assert _parse_tag("v0.26.04.3", cfg) is None


def test_parse_tag_accepts_ambiguous_short_year_zero_value_in_stable_mode() -> None:
    """Preserve valid stable tags whose short year component is genuinely zero."""
    cfg = CalverConfig(scheme="YY.0M", stable=True)
    parsed = _parse_tag("v0.04.3", cfg)
    assert parsed is not None
    assert _release_components(parsed, cfg) == ((0, 4), 3)


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


def test_release_components_accepts_unstable_prefixed_tag_when_stable_false() -> None:
    """Strip leading 0 release segment before extracting date and patch."""
    cfg = CalverConfig(mode=CalverMode.MONTH, stable=False)
    parsed = _parse_tag("v0.2026.04.3", cfg)
    assert parsed is not None
    assert _release_components(parsed, cfg) == ((2026, 4), 3)


def test_release_components_accepts_unstable_mode_with_legacy_unprefixed_tag() -> None:
    """Keep migration smooth by still parsing legacy tags without the 0 prefix."""
    cfg = CalverConfig(mode=CalverMode.MONTH, stable=False)
    parsed = _parse_tag("v2026.04.3", cfg)
    assert parsed is not None
    assert _release_components(parsed, cfg) == ((2026, 4), 3)

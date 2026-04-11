from __future__ import annotations

import datetime as dt
from typing import cast

import pytest

from calver_scm.config import CalverConfig, CalverMode, FallbackMode

# noinspection PyProtectedMember
from calver_scm.utils import (
    _base,
    _date_parts,
    _fallback_version,
    _format_date_parts,
    _is_padded_token,
    _is_same_period,
    _today_in_timezone,
    _token_value,
)


@pytest.mark.parametrize(
    ("token", "date", "expected"),
    [
        ("YYYY", dt.date(2026, 4, 15), 2026),
        ("YY", dt.date(2026, 4, 15), 26),
        ("0Y", dt.date(2026, 4, 15), 26),
        ("MM", dt.date(2026, 4, 15), 4),
        ("0M", dt.date(2026, 4, 15), 4),
        ("DD", dt.date(2026, 4, 15), 15),
        ("0D", dt.date(2026, 4, 15), 15),
        ("WW", dt.date(2026, 4, 15), 16),
        ("0W", dt.date(2026, 4, 15), 16),
    ],
)
def test_token_value_maps_supported_tokens(
    token: str,
    date: dt.date,
    expected: int,
) -> None:
    """Map each supported token to its expected date component."""
    assert _token_value(token, date) == expected


def test_token_value_rejects_unknown_token() -> None:
    """Raise when attempting to map an unsupported token."""
    with pytest.raises(ValueError, match="Unsupported scheme token"):
        _token_value("BAD", dt.date(2026, 4, 15))


@pytest.mark.parametrize(
    ("token", "expected"),
    [("0Y", True), ("0M", True), ("0W", True), ("0D", True), ("MM", False)],
)
def test_is_padded_token_identifies_padding_rules(token: str, expected: bool) -> None:
    """Identify which tokens require zero-padding in output."""
    assert _is_padded_token(token) is expected


def test_date_parts_and_base_for_day_scheme() -> None:
    """Build date parts and formatted base strings from configured tokens."""
    cfg = CalverConfig(mode=CalverMode.DAY)
    today = dt.date(2026, 4, 5)
    assert _date_parts(today, cfg) == (2026, 4, 5)
    assert _base(today, cfg) == "2026.04.05"


def test_format_date_parts_honors_padded_and_non_padded_tokens() -> None:
    """Render parts with per-token padding semantics."""
    cfg = CalverConfig(scheme="YY.MM.0D")
    assert _format_date_parts((26, 4, 5), cfg) == "26.4.05"


def test_is_same_period_uses_configured_scheme_tokens() -> None:
    """Compare period boundaries based on resolved scheme tokens."""
    cfg = CalverConfig(mode=CalverMode.MONTH)
    today = dt.date(2026, 4, 15)
    assert _is_same_period(today, (2026, 4), cfg) is True
    assert _is_same_period(today, (2026, 5), cfg) is False


@pytest.mark.parametrize(
    ("fallback", "expected"),
    [
        (FallbackMode.DEV, "2026.04.0.dev5"),
        (FallbackMode.DATE, "2026.04.0"),
    ],
)
def test_fallback_version_renders_expected_modes(
    fallback: FallbackMode,
    expected: str,
) -> None:
    """Render fallback output for both supported fallback modes."""
    assert _fallback_version(base="2026.04", distance=5, fallback=fallback) == expected


class _RecorderDateTime(dt.datetime):
    """Test double for tracking timezone arguments passed to now()."""

    last_tz: dt.tzinfo | None = None

    @classmethod
    def now(cls, tz: dt.tzinfo | None = None) -> _RecorderDateTime:
        """Return a stable datetime and remember the supplied timezone."""
        cls.last_tz = tz
        # noinspection PyArgumentEqualDefault
        baseline = dt.datetime(2026, 4, 15, 12, 0, tzinfo=dt.timezone.utc)
        value = baseline if tz is None else baseline.astimezone(tz)
        return cast("_RecorderDateTime", value)


@pytest.mark.parametrize("timezone", ["local", "utc"])
def test_today_in_timezone_supports_local_and_utc(
    monkeypatch: pytest.MonkeyPatch,
    timezone: str,
) -> None:
    """Return today's date for local and UTC timezone modes."""
    monkeypatch.setattr("calver_scm.utils.datetime.datetime", _RecorderDateTime)
    today = _today_in_timezone(timezone)
    assert today == dt.date(2026, 4, 15)

    if timezone == "local":
        assert _RecorderDateTime.last_tz is None
    else:
        assert _RecorderDateTime.last_tz is dt.timezone.utc


def test_today_in_timezone_supports_iana_zone_with_stubbed_zoneinfo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pass the stripped IANA timezone key into ZoneInfo construction."""
    captured: dict[str, str] = {}

    def fake_zoneinfo(name: str) -> dt.tzinfo:
        captured["name"] = name
        return dt.timezone.utc

    monkeypatch.setattr("calver_scm.utils.datetime.datetime", _RecorderDateTime)
    monkeypatch.setattr("calver_scm.utils.ZoneInfo", fake_zoneinfo)

    today = _today_in_timezone("  Europe/London  ")
    assert today == dt.date(2026, 4, 15)
    assert captured["name"] == "Europe/London"

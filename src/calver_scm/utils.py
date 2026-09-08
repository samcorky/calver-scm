from __future__ import annotations

import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from calver_scm.config import CalverConfig, FallbackMode


def _is_same_period(
    today: datetime.date,
    tag_date_parts: tuple[int, ...],
    cfg: CalverConfig,
) -> bool:
    """Check if today is in the same CalVer period as the tag."""
    return _date_parts(today, cfg) == tag_date_parts


def _date_parts(today: datetime.date, cfg: CalverConfig) -> tuple[int, ...]:
    """Return date parts for today based on configured scheme tokens."""
    return tuple(_token_value(token, today) for token in cfg.scheme_tokens)


def _format_date_parts(parts: tuple[int, ...], _cfg: CalverConfig | None = None) -> str:
    """Render date parts."""
    return ".".join(str(part) for part in parts)


def _token_value(token: str, today: datetime.date) -> int:
    """Map a configured scheme token to its numeric date value."""
    match token:
        case "YYYY":
            return today.year
        case "YY":
            return today.year - 2000
        case "MM":
            return today.month
        case "DD":
            return today.day
        case "WW":
            return today.isocalendar().week
        case _:
            raise ValueError(f"Unsupported scheme token: {token!r}")


def _base(today: datetime.date, cfg: CalverConfig) -> str:
    """Return the base version string for today."""
    return _format_date_parts(_date_parts(today, cfg), cfg)


def _fallback_version(*, base: str, distance: int, fallback: FallbackMode) -> str:
    """Build fallback output when a tag is missing or incompatible."""
    if fallback == "date":
        return f"{base}.0"
    return f"{base}.0.dev{distance}"


def _apply_stability_prefix(version: str, cfg: CalverConfig) -> str:
    """Prefix output with `0.` when project stability is explicitly disabled."""
    if cfg.stable:
        return version
    return f"0.{version}"


def _today_in_timezone(timezone: str) -> datetime.date:
    """Return today's date in configured timezone semantics."""
    normalized = timezone.strip().lower()
    if normalized == "local":
        return datetime.datetime.now().astimezone().date()
    if normalized == "utc":
        return datetime.datetime.now(datetime.timezone.utc).date()
    return datetime.datetime.now(ZoneInfo(timezone.strip())).date()

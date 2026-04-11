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


def _format_date_parts(parts: tuple[int, ...], cfg: CalverConfig) -> str:
    """Render date parts according to token zero-padding semantics."""
    rendered: list[str] = []
    for token, value in zip(cfg.scheme_tokens, parts, strict=True):
        if _is_padded_token(token):
            rendered.append(f"{value:02d}")
        else:
            rendered.append(str(value))
    return ".".join(rendered)


def _token_value(token: str, today: datetime.date) -> int:
    """Map a configured scheme token to its numeric date value."""
    match token:
        case "YYYY":
            return today.year
        case "YY" | "0Y":
            return today.year - 2000
        case "MM" | "0M":
            return today.month
        case "DD" | "0D":
            return today.day
        case "WW" | "0W":
            return today.isocalendar().week
        case _:
            raise ValueError(f"Unsupported scheme token: {token!r}")


def _is_padded_token(token: str) -> bool:
    """Return whether a scheme token must be zero-padded in output."""
    return token in ("0Y", "0M", "0W", "0D")


def _base(today: datetime.date, cfg: CalverConfig) -> str:
    """Return the base version string for today."""
    return _format_date_parts(_date_parts(today, cfg), cfg)


def _fallback_version(*, base: str, distance: int, fallback: FallbackMode) -> str:
    """Build fallback output when a tag is missing or incompatible."""
    if fallback == "date":
        return f"{base}.0"
    return f"{base}.0.dev{distance}"


def _today_in_timezone(timezone: str) -> datetime.date:
    """Return today's date in configured timezone semantics."""
    normalized = timezone.strip().lower()
    if normalized == "local":
        return datetime.datetime.now().astimezone().date()
    if normalized == "utc":
        return datetime.datetime.now(datetime.timezone.utc).date()
    return datetime.datetime.now(ZoneInfo(timezone.strip())).date()

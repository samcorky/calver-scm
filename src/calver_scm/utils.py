import datetime

from calver_scm.config import CalverConfig


def _is_same_period(
        today: datetime.date,
        tag_year: int,
        tag_month: int,
        tag_day: int,
        cfg: CalverConfig,
) -> bool:
    """Check if today is in the same CalVer period as the tag."""
    same = today.year == tag_year and today.month == tag_month
    if cfg.mode == "day":
        return same and today.day == tag_day
    return same


def _base(today: datetime.date, cfg: CalverConfig) -> str:
    """Return the base version string for today."""
    if cfg.mode == "day":
        return f"{today.year}.{today.month:02d}.{today.day:02d}"
    return f"{today.year}.{today.month:02d}"

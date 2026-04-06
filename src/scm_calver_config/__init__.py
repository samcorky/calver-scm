# src/scm_calver_config/__init__.py

"""SCM CalVer Config — a configurable CalVer scheme for setuptools-scm."""

from __future__ import annotations

import datetime
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from setuptools_scm.version import ScmVersion

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]


@dataclass(frozen=True, slots=True)
class CalverConfig:
    """Configuration for the CalVer versioning scheme."""

    mode: Literal["month", "day"] = "month"
    patch: bool = True
    fallback: Literal["dev", "date"] = "dev"
    tag_prefix: str = "v"

    def __post_init__(self) -> None:
        if self.mode not in ("month", "day"):
            raise ValueError(f"Invalid mode: {self.mode!r}")
        if not isinstance(self.patch, bool):
            raise ValueError(f"Invalid patch value: {self.patch!r}")
        if self.fallback not in ("dev", "date"):
            raise ValueError(f"Invalid fallback: {self.fallback!r}")
        if not isinstance(self.tag_prefix, str):
            raise ValueError(f"Invalid tag_prefix: {self.tag_prefix!r}")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CalverConfig:
        mode = data.get("mode", "month")
        patch = data.get("patch", True)
        fallback = data.get("fallback", "dev")
        tag_prefix = data.get("tag_prefix", "v")

        return cls(
            mode=mode,
            patch=patch,
            fallback=fallback,
            tag_prefix=tag_prefix,
        )

    @classmethod
    def overlay_env(cls, base: CalverConfig) -> CalverConfig:
        """Override config fields with environment variables, if present."""
        data: dict[str, Any] = {
            "mode": base.mode,
            "patch": base.patch,
            "fallback": base.fallback,
            "tag_prefix": base.tag_prefix,
        }

        if "SCM_CALVER_MODE" in os.environ:
            data["mode"] = os.environ["SCM_CALVER_MODE"]
        if "SCM_CALVER_PATCH" in os.environ:
            value = os.environ["SCM_CALVER_PATCH"].strip().lower()
            if value in ("1", "true", "yes", "on"):
                data["patch"] = True
            elif value in ("0", "false", "no", "off"):
                data["patch"] = False
            else:
                raise ValueError(
                    f"Invalid SCM_CALVER_PATCH value: "
                    f"{os.environ['SCM_CALVER_PATCH']!r}"
                )
        if "SCM_CALVER_FALLBACK" in os.environ:
            data["fallback"] = os.environ["SCM_CALVER_FALLBACK"]
        if "SCM_CALVER_TAG_PREFIX" in os.environ:
            data["tag_prefix"] = os.environ["SCM_CALVER_TAG_PREFIX"]

        return cls.from_dict(data)


@lru_cache(maxsize=1)
def _load_calver_config(root: Path) -> CalverConfig:
    """Load config from pyproject.toml, then override with environment variables."""
    pyproject = root / "pyproject.toml"
    data: dict[str, Any] = {}

    if pyproject.exists():
        try:
            with pyproject.open("rb") as f:
                toml_data = tomllib.load(f)
            data = toml_data.get("tool", {}).get("calver_scm", {})
        except tomllib.TOMLDecodeError as e:
            raise RuntimeError(f"Invalid pyproject.toml: {e}") from e

    try:
        cfg = CalverConfig.from_dict(data)
        return CalverConfig.overlay_env(cfg)
    except ValueError as e:
        raise RuntimeError(f"Invalid config: {e}") from e


def _parse_tag(
    tag: str,
    cfg: CalverConfig,
) -> tuple[int, int, int, int] | None:
    """Parse a tag into (year, month, day, patch) — day is 0 in month mode."""
    stripped = tag.removeprefix(cfg.tag_prefix)
    parts = stripped.split(".")

    try:
        if cfg.mode == "day":
            tag_year = int(parts[0])
            tag_month = int(parts[1])
            tag_day = int(parts[2])
            tag_patch = int(parts[3]) if len(parts) > 3 else 0
            return tag_year, tag_month, tag_day, tag_patch
        else:
            tag_year = int(parts[0])
            tag_month = int(parts[1])
            tag_patch = int(parts[2]) if len(parts) > 2 else 0
            return tag_year, tag_month, 0, tag_patch
    except (IndexError, ValueError):
        return None


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


def calver_scm(version: ScmVersion) -> str:
    """Return a CalVer version string derived from SCM state."""
    root = Path(getattr(version.config, "root", None) or ".").resolve()
    cfg = _load_calver_config(root)
    today = datetime.date.today()
    base = _base(today, cfg)

    if version.tag is None:
        if cfg.fallback == "date":
            return f"{base}.0"
        return f"{base}.0.dev{version.distance}"

    parsed = _parse_tag(str(version.tag), cfg)

    if parsed is None:
        if cfg.fallback == "date":
            return f"{base}.0"
        return f"{base}.0.dev{version.distance}"

    tag_year, tag_month, tag_day, tag_patch = parsed

    if version.distance == 0 and not version.dirty:
        if cfg.mode == "day":
            return f"{tag_year}.{tag_month:02d}.{tag_day:02d}.{tag_patch}"
        return f"{tag_year}.{tag_month:02d}.{tag_patch}"

    same_period = _is_same_period(today, tag_year, tag_month, tag_day, cfg)
    patch = (tag_patch + 1) if same_period and cfg.patch else 0

    return f"{base}.{patch}.dev{version.distance}"

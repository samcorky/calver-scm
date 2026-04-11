from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

TRUE_ENV_VALUES = frozenset(("1", "true", "yes", "on"))
FALSE_ENV_VALUES = frozenset(("0", "false", "no", "off"))


class _StrEnum(str, Enum):
    """Python 3.10-compatible string enum base class."""


class CalverMode(_StrEnum):
    """Built-in mode presets for deriving default scheme tokens."""

    YEAR = "year"
    MONTH = "month"
    WEEK = "week"
    DAY = "day"

    @classmethod
    def from_raw(cls, value: str | CalverMode) -> CalverMode:
        """Coerce raw mode input into a validated enum value."""
        if isinstance(value, cls):
            return value
        try:
            return cls(value)
        except ValueError as e:
            raise ValueError(f"Invalid mode: {value!r}") from e


class FallbackMode(_StrEnum):
    """Fallback behaviour when no compatible tag can be parsed."""

    DEV = "dev"
    DATE = "date"

    @classmethod
    def from_raw(cls, value: str | FallbackMode) -> FallbackMode:
        """Coerce raw fallback input into a validated enum value."""
        if isinstance(value, cls):
            return value
        try:
            return cls(value)
        except ValueError as e:
            raise ValueError(f"Invalid fallback: {value!r}") from e


if TYPE_CHECKING:
    from pathlib import Path

if sys.version_info >= (3, 11):  # pragma: no cover
    # noinspection PyCompatibility
    import tomllib
else:  # pragma: no cover
    # noinspection SpellCheckingInspection
    import tomli as tomllib


@dataclass(frozen=True, slots=True)
class CalverConfig:
    """Configuration for the CalVer versioning scheme."""

    mode: CalverMode = CalverMode.MONTH
    scheme: str | None = None
    patch: bool = True
    fallback: FallbackMode = FallbackMode.DEV
    tag_prefix: str = "v"
    timezone: str = "UTC"

    _ALLOWED_SCHEME_TOKENS = frozenset(
        {
            "YYYY",
            "YY",
            "0Y",
            "MM",
            "0M",
            "WW",
            "0W",
            "DD",
            "0D",
        }
    )

    def __post_init__(self) -> None:
        """Validate field values after dataclass initialization."""
        object.__setattr__(self, "mode", CalverMode.from_raw(self.mode))
        object.__setattr__(self, "fallback", FallbackMode.from_raw(self.fallback))
        if self.scheme is not None:
            if not isinstance(self.scheme, str):
                raise ValueError(f"Invalid scheme: {self.scheme!r}")
            self._validate_scheme_tokens(self.scheme_tokens)
        if not isinstance(self.patch, bool):
            raise ValueError(f"Invalid patch value: {self.patch!r}")
        if not isinstance(self.tag_prefix, str):
            raise ValueError(f"Invalid tag_prefix: {self.tag_prefix!r}")
        if not isinstance(self.timezone, str):
            raise ValueError(f"Invalid timezone: {self.timezone!r}")
        timezone = self.timezone.strip()
        if not timezone:
            raise ValueError(f"Invalid timezone: {self.timezone!r}")
        if timezone.lower() not in ("local", "utc"):
            try:
                ZoneInfo(timezone)
            except ZoneInfoNotFoundError as e:
                raise ValueError(f"Invalid timezone: {self.timezone!r}") from e

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CalverConfig:
        """Build a config object from raw mapping values."""
        mode = data.get("mode", CalverMode.MONTH)
        scheme = data.get("scheme")
        patch = data.get("patch", True)
        fallback = data.get("fallback", FallbackMode.DEV)
        tag_prefix = data.get("tag_prefix", "v")
        timezone = data.get("timezone", "UTC")

        return cls(
            mode=mode,
            scheme=scheme,
            patch=patch,
            fallback=fallback,
            tag_prefix=tag_prefix,
            timezone=timezone,
        )

    @property
    def scheme_tokens(self) -> tuple[str, ...]:
        """Return resolved date tokens for version base generation."""
        if self.scheme:
            return tuple(token.strip() for token in self.scheme.split("."))
        if self.mode == CalverMode.YEAR:
            return ("YYYY",)
        if self.mode == CalverMode.WEEK:
            return "YYYY", "0W"
        if self.mode == CalverMode.DAY:
            return "YYYY", "0M", "0D"
        return "YYYY", "0M"

    @classmethod
    def _validate_scheme_tokens(cls, tokens: tuple[str, ...]) -> None:
        """Validate that token sequence is supported and internally consistent."""
        if any(token not in cls._ALLOWED_SCHEME_TOKENS for token in tokens):
            raise ValueError("Invalid scheme")

        has_week = any(token in ("WW", "0W") for token in tokens)
        has_month_or_day = any(token in ("MM", "0M", "DD", "0D") for token in tokens)
        if has_week and has_month_or_day:
            raise ValueError(
                "Invalid scheme: week tokens cannot be combined with month/day tokens"
            )

        if not any(token in ("YYYY", "YY", "0Y") for token in tokens):
            raise ValueError("Invalid scheme: scheme must include a year token")

    @classmethod
    def overlay_env(cls, base: CalverConfig) -> CalverConfig:
        """Override config fields with environment variables, if present."""
        data: dict[str, Any] = {
            "mode": base.mode,
            "scheme": base.scheme,
            "patch": base.patch,
            "fallback": base.fallback,
            "tag_prefix": base.tag_prefix,
            "timezone": base.timezone,
        }

        if "CALVER_SCM_MODE" in os.environ:
            data["mode"] = os.environ["CALVER_SCM_MODE"]
        if "CALVER_SCM_SCHEME" in os.environ:
            data["scheme"] = os.environ["CALVER_SCM_SCHEME"]
        if "CALVER_SCM_PATCH" in os.environ:
            value = os.environ["CALVER_SCM_PATCH"].strip().lower()
            if value in TRUE_ENV_VALUES:
                data["patch"] = True
            elif value in FALSE_ENV_VALUES:
                data["patch"] = False
            else:
                raise ValueError(
                    f"Invalid CALVER_SCM_PATCH value: "
                    f"{os.environ['CALVER_SCM_PATCH']!r}"
                )
        if "CALVER_SCM_FALLBACK" in os.environ:
            data["fallback"] = os.environ["CALVER_SCM_FALLBACK"]
        if "CALVER_SCM_TAG_PREFIX" in os.environ:
            data["tag_prefix"] = os.environ["CALVER_SCM_TAG_PREFIX"]
        if "CALVER_SCM_TIMEZONE" in os.environ:
            data["timezone"] = os.environ["CALVER_SCM_TIMEZONE"]

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

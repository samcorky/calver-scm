from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from types import MappingProxyType
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

if TYPE_CHECKING:
    from pathlib import Path

if sys.version_info >= (3, 11):  # pragma: no cover
    # noinspection PyCompatibility
    import tomllib
else:  # pragma: no cover
    # noinspection SpellCheckingInspection
    import tomli as tomllib


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


# CalVer token group constants (global, immutable)
YEAR_TOKENS = frozenset({"YYYY", "YY"})
MONTH_TOKENS = frozenset({"MM"})
WEEK_TOKENS = frozenset({"WW"})
DAY_TOKENS = frozenset({"DD"})
ALL_TOKENS = YEAR_TOKENS | MONTH_TOKENS | WEEK_TOKENS | DAY_TOKENS
# Granularity mapping: 0=year, 1=month/week, 2=day
TOKEN_GRANULARITY = MappingProxyType(
    {
        **dict.fromkeys(YEAR_TOKENS, 0),
        **dict.fromkeys(MONTH_TOKENS, 1),
        **dict.fromkeys(WEEK_TOKENS, 1),
        **dict.fromkeys(DAY_TOKENS, 2),
    }
)


@dataclass(frozen=True, slots=True)
class CalverConfig:
    """Configuration for the CalVer versioning scheme."""

    mode: CalverMode = CalverMode.MONTH
    scheme: str | None = None
    patch: bool = True
    stable: bool = True
    fallback: FallbackMode = FallbackMode.DEV
    tag_prefix: str = "v"
    timezone: str = "UTC"

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
        if not isinstance(self.stable, bool):
            raise ValueError(f"Invalid stable value: {self.stable!r}")
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
        stable = data.get("stable", True)
        fallback = data.get("fallback", FallbackMode.DEV)
        tag_prefix = data.get("tag_prefix", "v")
        timezone = data.get("timezone", "UTC")

        return cls(
            mode=mode,
            scheme=scheme,
            patch=patch,
            stable=stable,
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
            return "YYYY", "WW"
        if self.mode == CalverMode.DAY:
            return "YYYY", "MM", "DD"
        return "YYYY", "MM"

    @classmethod
    def _validate_scheme_tokens(cls, tokens: tuple[str, ...]) -> None:
        """Validates scheme tokens.

        Checks that a token sequence is supported, internally consistent,
        and ordered by descending calendar granularity.

        Year tokens must come first, followed by month/week, then day tokens.
        Only one token per granularity is allowed.
        """
        # Validate all tokens are known
        unknown = set(tokens) - ALL_TOKENS
        if unknown:
            raise ValueError(f"Invalid scheme: unknown token(s) {unknown}")

        # Use set logic for week/month/day mixing
        token_set = set(tokens)
        has_week = bool(token_set & WEEK_TOKENS)
        has_month = bool(token_set & MONTH_TOKENS)
        has_day = bool(token_set & DAY_TOKENS)
        if has_week and (has_month or has_day):
            raise ValueError(
                "Invalid scheme: week tokens cannot be combined with month/day tokens"
            )

        # Validate year presence
        if not (token_set & YEAR_TOKENS):
            raise ValueError("Invalid scheme: scheme must include a year token")

        # Validate order and uniqueness per granularity
        last_level = -1
        seen_levels = set()
        for token in tokens:
            level = TOKEN_GRANULARITY[token]
            if level < last_level:
                raise ValueError(
                    f"Invalid scheme: token '{token}' appears before a "
                    "higher-granularity token. "
                    "Tokens must be ordered: year → month/week → day."
                )
            if level in seen_levels:
                raise ValueError(
                    f"Invalid scheme: more than one token for granularity "
                    f"level {level} ('{token}'). "
                    "Only one token per granularity (year, month/week, day) "
                    "is allowed."
                )
            seen_levels.add(level)
            last_level = level

    @classmethod
    def overlay_env(cls, base: CalverConfig) -> CalverConfig:
        """Override config fields with environment variables, if present."""
        data: dict[str, Any] = {
            "mode": base.mode,
            "scheme": base.scheme,
            "patch": base.patch,
            "stable": base.stable,
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
        if "CALVER_SCM_STABLE" in os.environ:
            value = os.environ["CALVER_SCM_STABLE"].strip().lower()
            if value in TRUE_ENV_VALUES:
                data["stable"] = True
            elif value in FALSE_ENV_VALUES:
                data["stable"] = False
            else:
                raise ValueError(
                    f"Invalid CALVER_SCM_STABLE value: "
                    f"{os.environ['CALVER_SCM_STABLE']!r}"
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
            data = toml_data.get("tool", {}).get("calver-scm", {})
        except tomllib.TOMLDecodeError as e:
            raise RuntimeError(f"Invalid pyproject.toml: {e}") from e

    try:
        cfg = CalverConfig.from_dict(data)
        return CalverConfig.overlay_env(cfg)
    except ValueError as e:
        raise RuntimeError(f"Invalid config: {e}") from e

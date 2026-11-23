from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from types import MappingProxyType
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

CONFIG_FILE_NAME = "calver-scm.toml"
PYPROJECT_FILE_NAME = "pyproject.toml"
CALVER_FIELDS = (
    "mode",
    "scheme",
    "patch",
    "stable",
    "no_dev",
    "fallback",
    "tag_prefix",
    "timezone",
)

# The only CALVER_SCM_* variables that are settings; any other is not read.
SETTING_ENV_VARS = frozenset(f"CALVER_SCM_{field.upper()}" for field in CALVER_FIELDS)


TRUE_ENV_VALUES = frozenset(("1", "true", "yes", "on"))
FALSE_ENV_VALUES = frozenset(("0", "false", "no", "off"))


class CalverMode(StrEnum):
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


class FallbackMode(StrEnum):
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
    no_dev: bool = False
    fallback: FallbackMode = FallbackMode.DEV
    tag_prefix: str = "v"
    timezone: str = "UTC"

    def __post_init__(self) -> None:
        """Validate field values after dataclass initialisation."""
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
        if not isinstance(self.no_dev, bool):
            raise ValueError(f"Invalid no_dev value: {self.no_dev!r}")
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
        no_dev = data.get("no_dev", False)
        fallback = data.get("fallback", FallbackMode.DEV)
        tag_prefix = data.get("tag_prefix", "v")
        timezone = data.get("timezone", "UTC")

        return cls(
            mode=mode,
            scheme=scheme,
            patch=patch,
            stable=stable,
            no_dev=no_dev,
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
            "no_dev": base.no_dev,
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
        if "CALVER_SCM_NO_DEV" in os.environ:
            value = os.environ["CALVER_SCM_NO_DEV"].strip().lower()
            if value in TRUE_ENV_VALUES:
                data["no_dev"] = True
            elif value in FALSE_ENV_VALUES:
                data["no_dev"] = False
            else:
                raise ValueError(
                    f"Invalid CALVER_SCM_NO_DEV value: "
                    f"{os.environ['CALVER_SCM_NO_DEV']!r}"
                )
        if "CALVER_SCM_FALLBACK" in os.environ:
            data["fallback"] = os.environ["CALVER_SCM_FALLBACK"]
        if "CALVER_SCM_TAG_PREFIX" in os.environ:
            data["tag_prefix"] = os.environ["CALVER_SCM_TAG_PREFIX"]
        if "CALVER_SCM_TIMEZONE" in os.environ:
            data["timezone"] = os.environ["CALVER_SCM_TIMEZONE"]

        return cls.from_dict(data)


def _read_toml(path: Path, label: str) -> dict[str, Any] | None:
    """Parse a TOML file, returning `None` if it does not exist."""
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return None
    except tomllib.TOMLDecodeError as e:
        raise RuntimeError(f"Invalid {label}: {e}") from e


def read_settings_file(root: Path) -> dict[str, Any] | None:
    """Return the parsed `calver-scm.toml` table, or `None` if there is none."""
    return _read_toml(root / CONFIG_FILE_NAME, CONFIG_FILE_NAME)


def _pyproject_settings(root: Path) -> dict[str, Any]:
    """Return the `[tool.calver-scm]` table, empty if there is none."""
    data = _read_toml(root / PYPROJECT_FILE_NAME, PYPROJECT_FILE_NAME) or {}
    table: dict[str, Any] = data.get("tool", {}).get("calver-scm", {})
    return table


@cache
def load_calver_config_with_sources(
    root: Path,
) -> tuple[CalverConfig, Mapping[str, str]]:
    """Load settings and record where each one came from.

    Layers, lowest to highest precedence: the defaults, `[tool.calver-scm]` in
    `pyproject.toml`, `calver-scm.toml`, then `CALVER_SCM_*` variables.
    """
    pyproject = _pyproject_settings(root)
    settings = read_settings_file(root) or {}

    sources: dict[str, str] = {}
    for field in CALVER_FIELDS:
        if field in settings:
            sources[field] = CONFIG_FILE_NAME
        elif field in pyproject:
            sources[field] = PYPROJECT_FILE_NAME
        else:
            sources[field] = "default"
        env_name = f"CALVER_SCM_{field.upper()}"
        if env_name in os.environ:
            sources[field] = f"env {env_name}"

    try:
        cfg = CalverConfig.overlay_env(
            CalverConfig.from_dict({**pyproject, **settings})
        )
    except ValueError as e:
        raise RuntimeError(f"Invalid config: {e}") from e
    return cfg, MappingProxyType(sources)


def _load_calver_config(root: Path) -> CalverConfig:
    """Load the layered configuration, without its sources."""
    return load_calver_config_with_sources(root)[0]


@dataclass(frozen=True, slots=True)
class SettingsFiles:
    """Which files supply settings, and which keys they disagree on."""

    files: tuple[str, ...]
    conflicts: tuple[str, ...]


def describe_settings_files(root: Path) -> SettingsFiles:
    """Name the files that supply settings and the keys set differently in both."""
    pyproject = _pyproject_settings(root)
    settings = read_settings_file(root)

    files: list[str] = []
    if pyproject:
        files.append(PYPROJECT_FILE_NAME)
    if settings is not None:
        files.append(CONFIG_FILE_NAME)

    conflicts = tuple(
        sorted(
            key
            for key in CALVER_FIELDS
            if settings is not None
            and key in pyproject
            and key in settings
            and pyproject[key] != settings[key]
        )
    )
    return SettingsFiles(tuple(files), conflicts)

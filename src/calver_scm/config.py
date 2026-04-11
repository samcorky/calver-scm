from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Literal

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

    mode: Literal["month", "day"] = "month"
    patch: bool = True
    fallback: Literal["dev", "date"] = "dev"
    tag_prefix: str = "v"

    def __post_init__(self) -> None:
        """Validate field values after dataclass initialization."""
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
        """Build a config object from raw mapping values."""
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

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

# noinspection PyProtectedMember
from calver_scm.config import (
    CalverConfig,
    CalverMode,
    FallbackMode,
    _load_calver_config,
)

if TYPE_CHECKING:
    from pathlib import Path


pytestmark = pytest.mark.unit


def test_enum_from_raw_accepts_instances_and_strings() -> None:
    """Coerce enum values from either already-typed or raw string input."""
    assert CalverMode.from_raw(CalverMode.MONTH) is CalverMode.MONTH
    assert CalverMode.from_raw("day") is CalverMode.DAY
    assert FallbackMode.from_raw(FallbackMode.DEV) is FallbackMode.DEV
    assert FallbackMode.from_raw("date") is FallbackMode.DATE


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (CalverMode.YEAR, ("YYYY",)),
        (CalverMode.MONTH, ("YYYY", "0M")),
        (CalverMode.WEEK, ("YYYY", "0W")),
        (CalverMode.DAY, ("YYYY", "0M", "0D")),
    ],
)
def test_scheme_tokens_default_from_mode(
    mode: CalverMode,
    expected: tuple[str, ...],
) -> None:
    """Resolve default scheme token sets from each built-in mode."""
    assert CalverConfig(mode=mode).scheme_tokens == expected


def test_scheme_tokens_from_explicit_scheme() -> None:
    """Split explicit scheme strings into token tuples."""
    cfg = CalverConfig(scheme="YYYY.0M.0D")
    assert cfg.scheme_tokens == ("YYYY", "0M", "0D")


@pytest.mark.parametrize(
    "data",
    [
        {"mode": "invalid"},
        {"fallback": "invalid"},
        {"scheme": 123},
        {"scheme": "YYYY.BAD"},
        {"scheme": "0M.0D"},
        {"scheme": "YYYY.0W.0D"},
        {"patch": "true"},
        {"tag_prefix": 1},
        {"timezone": 1},
        {"timezone": "   "},
        {"timezone": "No/SuchZone"},
    ],
)
def test_invalid_config_values_raise_value_error(data: dict[str, Any]) -> None:
    """Reject unsupported raw configuration inputs."""
    with pytest.raises(ValueError):
        CalverConfig.from_dict(data)


def test_from_dict_applies_defaults() -> None:
    """Build configs from sparse dictionaries using expected defaults."""
    cfg = CalverConfig.from_dict({"mode": "year"})
    assert cfg.mode is CalverMode.YEAR
    assert cfg.scheme is None
    assert cfg.patch is True
    assert cfg.fallback is FallbackMode.DEV
    assert cfg.tag_prefix == "v"
    assert cfg.timezone == "UTC"


def test_overlay_env_overrides_values(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prefer CALVER_SCM_* environment values over base config fields."""
    base = CalverConfig(
        mode=CalverMode.MONTH,
        patch=True,
        fallback=FallbackMode.DEV,
        tag_prefix="v",
    )
    monkeypatch.setenv("CALVER_SCM_MODE", "day")
    monkeypatch.setenv("CALVER_SCM_SCHEME", "YYYY.0M.0D")
    monkeypatch.setenv("CALVER_SCM_PATCH", "off")
    monkeypatch.setenv("CALVER_SCM_FALLBACK", "date")
    monkeypatch.setenv("CALVER_SCM_TAG_PREFIX", "release-")
    monkeypatch.setenv("CALVER_SCM_TIMEZONE", "UTC")

    cfg = CalverConfig.overlay_env(base)
    assert cfg.mode is CalverMode.DAY
    assert cfg.scheme == "YYYY.0M.0D"
    assert cfg.patch is False
    assert cfg.fallback is FallbackMode.DATE
    assert cfg.tag_prefix == "release-"
    assert cfg.timezone == "UTC"


def test_overlay_env_rejects_invalid_patch_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raise a helpful error when CALVER_SCM_PATCH cannot be parsed as bool."""
    monkeypatch.setenv("CALVER_SCM_PATCH", "maybe")
    with pytest.raises(ValueError, match="Invalid CALVER_SCM_PATCH value"):
        CalverConfig.overlay_env(CalverConfig())


def test_overlay_env_accepts_truthy_patch_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Treat truthy env values as enabled patch auto-increment."""
    monkeypatch.setenv("CALVER_SCM_PATCH", "yes")
    cfg = CalverConfig.overlay_env(CalverConfig(patch=False))
    assert cfg.patch is True


def test_overlay_env_ignores_legacy_scm_calver_variable_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ignore deprecated SCM_CALVER_* env vars during migration to CALVER_SCM_*."""
    base = CalverConfig(mode=CalverMode.MONTH)
    monkeypatch.setenv("SCM_CALVER_MODE", "day")

    cfg = CalverConfig.overlay_env(base)
    assert cfg.mode is CalverMode.MONTH


def test_load_calver_config_reads_pyproject_and_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Load project config from pyproject and then apply env overrides."""
    (tmp_path / "pyproject.toml").write_text(
        "\n".join(
            [
                "[tool.calver_scm]",
                'mode = "month"',
                'fallback = "dev"',
                'tag_prefix = "v"',
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CALVER_SCM_MODE", "week")

    cfg = _load_calver_config(tmp_path)
    assert cfg.mode is CalverMode.WEEK
    assert cfg.fallback is FallbackMode.DEV
    assert cfg.tag_prefix == "v"


def test_load_calver_config_defaults_when_file_missing(tmp_path: Path) -> None:
    """Return default config values when no pyproject exists."""
    cfg = _load_calver_config(tmp_path)
    assert cfg == CalverConfig()


def test_load_calver_config_raises_for_invalid_toml(tmp_path: Path) -> None:
    """Wrap TOML decode failures in a runtime error message."""
    (tmp_path / "pyproject.toml").write_text("[tool.calver_scm\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match=r"Invalid pyproject\.toml"):
        _load_calver_config(tmp_path)


def test_load_calver_config_raises_for_invalid_config(tmp_path: Path) -> None:
    """Wrap config validation failures in a runtime error message."""
    (tmp_path / "pyproject.toml").write_text(
        "\n".join(["[tool.calver_scm]", 'mode = "bad"']),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="Invalid config"):
        _load_calver_config(tmp_path)

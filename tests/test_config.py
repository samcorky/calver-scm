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
        (CalverMode.MONTH, ("YYYY", "MM")),
        (CalverMode.WEEK, ("YYYY", "WW")),
        (CalverMode.DAY, ("YYYY", "MM", "DD")),
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
    cfg = CalverConfig(scheme="YYYY.MM.DD")
    assert cfg.scheme_tokens == ("YYYY", "MM", "DD")


@pytest.mark.parametrize(
    "data",
    [
        {"mode": "invalid"},
        {"fallback": "invalid"},
        {"scheme": 123},
        {"scheme": "YYYY.BAD"},
        {"scheme": "MM.DD"},
        {"scheme": "YYYY.WW.DD"},
        {"patch": "true"},
        {"stable": "false"},
        {"no_dev": "true"},
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
    assert cfg.stable is True
    assert cfg.no_dev is False
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
    monkeypatch.setenv("CALVER_SCM_SCHEME", "YYYY.MM.DD")
    monkeypatch.setenv("CALVER_SCM_PATCH", "off")
    monkeypatch.setenv("CALVER_SCM_STABLE", "no")
    monkeypatch.setenv("CALVER_SCM_NO_DEV", "yes")
    monkeypatch.setenv("CALVER_SCM_FALLBACK", "date")
    monkeypatch.setenv("CALVER_SCM_TAG_PREFIX", "release-")
    monkeypatch.setenv("CALVER_SCM_TIMEZONE", "UTC")

    cfg = CalverConfig.overlay_env(base)
    assert cfg.mode is CalverMode.DAY
    assert cfg.scheme == "YYYY.MM.DD"
    assert cfg.patch is False
    assert cfg.stable is False
    assert cfg.no_dev is True
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


def test_overlay_env_rejects_invalid_stable_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raise a helpful error when CALVER_SCM_STABLE cannot be parsed as bool."""
    monkeypatch.setenv("CALVER_SCM_STABLE", "maybe")
    with pytest.raises(ValueError, match="Invalid CALVER_SCM_STABLE value"):
        CalverConfig.overlay_env(CalverConfig())


def test_overlay_env_accepts_truthy_stable_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Treat truthy env values as stable output enabled."""
    monkeypatch.setenv("CALVER_SCM_STABLE", "on")
    cfg = CalverConfig.overlay_env(CalverConfig(stable=False))
    assert cfg.stable is True


def test_overlay_env_rejects_invalid_no_dev_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raise a helpful error when CALVER_SCM_NO_DEV cannot be parsed as bool."""
    monkeypatch.setenv("CALVER_SCM_NO_DEV", "maybe")
    with pytest.raises(ValueError, match="Invalid CALVER_SCM_NO_DEV value"):
        CalverConfig.overlay_env(CalverConfig())


def test_overlay_env_accepts_falsy_no_dev_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Treat falsy env values as no_dev disabled."""
    monkeypatch.setenv("CALVER_SCM_NO_DEV", "off")
    cfg = CalverConfig.overlay_env(CalverConfig(no_dev=True))
    assert cfg.no_dev is False


def test_load_calver_config_reads_pyproject_and_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Load project config from pyproject and then apply env overrides."""
    (tmp_path / "pyproject.toml").write_text(
        "\n".join(
            [
                "[tool.calver-scm]",
                'mode = "month"',
                "stable = false",
                'fallback = "dev"',
                'tag_prefix = "v"',
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CALVER_SCM_MODE", "week")
    monkeypatch.setenv("CALVER_SCM_STABLE", "yes")

    cfg = _load_calver_config(tmp_path)
    assert cfg.mode is CalverMode.WEEK
    assert cfg.stable is True
    assert cfg.fallback is FallbackMode.DEV
    assert cfg.tag_prefix == "v"


def test_load_calver_config_defaults_when_file_missing(tmp_path: Path) -> None:
    """Return default config values when no pyproject exists."""
    cfg = _load_calver_config(tmp_path)
    assert cfg == CalverConfig()


def test_load_calver_config_raises_for_invalid_toml(tmp_path: Path) -> None:
    """Wrap TOML decode failures in a runtime error message."""
    (tmp_path / "pyproject.toml").write_text("[tool.calver-scm\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match=r"Invalid pyproject\.toml"):
        _load_calver_config(tmp_path)


def test_load_calver_config_raises_for_invalid_config(tmp_path: Path) -> None:
    """Wrap config validation failures in a runtime error message."""
    (tmp_path / "pyproject.toml").write_text(
        "\n".join(["[tool.calver-scm]", 'mode = "bad"']),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="Invalid config"):
        _load_calver_config(tmp_path)


@pytest.mark.parametrize(
    ("scheme", "expected"),
    [
        ("DD.YYYY", "Tokens must be ordered: year"),  # day before year
        (
            "MM.YYYY.DD",
            "Tokens must be ordered: year",
        ),  # month before year, day after year
        ("YYYY.DD.MM", "Tokens must be ordered: year"),  # day before month
        ("DD.MM.YYYY", "Tokens must be ordered: year"),  # day before month before year
        ("WW.YYYY", "Tokens must be ordered: year"),  # week before year
        (
            "DD.YYYY.WW",
            "week tokens cannot be combined with month/day tokens",
        ),  # week/month-day mix
    ],
)
def test_scheme_token_order_enforced(scheme: str, expected: str) -> None:
    """
    Reject schemes with tokens out of descending granularity order or with
    invalid combinations.
    """
    with pytest.raises(ValueError, match=expected):
        CalverConfig(scheme=scheme)


@pytest.mark.parametrize(
    "scheme",
    [
        "YYYY",
        "YYYY.MM",
        "YYYY.MM.DD",
        "YYYY.WW",
        "YY.MM.DD",
        "YY.WW",
        "YY.MM",
    ],
)
def test_scheme_token_order_valid(scheme: str) -> None:
    """
    Accept schemes with tokens in correct descending granularity order.
    """
    cfg = CalverConfig(scheme=scheme)
    assert cfg.scheme_tokens == tuple(scheme.split("."))


@pytest.mark.parametrize(
    ("scheme", "expected"),
    [
        ("YYYY.YY", "Only one token per granularity"),  # duplicate year
        ("YYYY.MM.MM", "Only one token per granularity"),  # duplicate month
        ("YYYY.WW.WW", "Only one token per granularity"),  # duplicate week
        ("YYYY.MM.DD.DD", "Only one token per granularity"),  # duplicate day
    ],
)
def test_scheme_token_duplicate_granularity_rejected(
    scheme: str, expected: str
) -> None:
    """
    Reject schemes with more than one token per granularity (year, month/week, day).
    """
    with pytest.raises(ValueError, match=expected):
        CalverConfig(scheme=scheme)


@pytest.mark.parametrize(
    "scheme",
    [
        "0Y",
        "0Y.MM",
        "YYYY.0M",
        "YYYY.0W",
        "YYYY.MM.0D",
    ],
)
def test_scheme_rejects_zero_padded_tokens(scheme: str) -> None:
    """Reject zero-padded tokens as invalid schemes."""
    with pytest.raises(ValueError, match="unknown token"):
        CalverConfig(scheme=scheme)

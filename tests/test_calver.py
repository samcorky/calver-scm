"""Tests for calver_scm."""

from __future__ import annotations

import datetime
import re
from typing import TYPE_CHECKING, Literal

# noinspection PyProtectedMember
from calver_scm.config import CalverConfig, _load_calver_config

# noinspection PyProtectedMember
from calver_scm.parser import _parse_tag, _release_components

# noinspection PyProtectedMember
from calver_scm.utils import _base, _is_same_period

if TYPE_CHECKING:
    from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# noinspection PyProtectedMember
from calver_scm import calver_scm

TODAY = datetime.date(2026, 4, 15)
JANUARY = datetime.date(2026, 1, 5)


def make_version(
    tag: str | None = None,
    distance: int = 0,
    dirty: bool = False,
    root: str = ".",
) -> MagicMock:
    """Create a mock ScmVersion."""
    version = MagicMock()
    version.tag = tag
    version.distance = distance
    version.dirty = dirty
    version.config.root = root
    return version


# noinspection PyShadowingNames
def make_config(
    mode: Literal["month", "day"] = "month",
    patch: bool = True,
    fallback: Literal["dev", "date"] = "dev",
    tag_prefix: str = "v",
) -> CalverConfig:
    """Create a CalverConfig with optional overrides."""
    return CalverConfig(
        mode=mode,
        patch=patch,
        fallback=fallback,
        tag_prefix=tag_prefix,
    )


@pytest.fixture
def freeze_april() -> object:
    """Freeze date to 2026-04-15."""
    with patch("calver_scm.scheme.datetime") as mock_dt:
        mock_dt.date.today.return_value = TODAY
        mock_dt.date.side_effect = lambda *a, **kw: datetime.date(*a, **kw)
        yield mock_dt


@pytest.fixture
def freeze_january() -> object:
    """Freeze date to 2026-01-05."""
    with patch("calver_scm.scheme.datetime") as mock_dt:
        mock_dt.date.today.return_value = JANUARY
        mock_dt.date.side_effect = lambda *a, **kw: datetime.date(*a, **kw)
        yield mock_dt


@pytest.fixture(autouse=True)
def clear_config_cache() -> object:
    """Clear lru_cache between tests."""
    _load_calver_config.cache_clear()
    yield
    _load_calver_config.cache_clear()


class TestCalverConfig:
    """CalverConfig model validation."""

    def test_defaults(self) -> None:
        cfg = CalverConfig()
        assert cfg.mode == "month"
        assert cfg.patch is True
        assert cfg.fallback == "dev"
        assert cfg.tag_prefix == "v"

    def test_custom_values(self) -> None:
        cfg = CalverConfig(mode="day", patch=False, fallback="date", tag_prefix="")
        assert cfg.mode == "day"
        assert cfg.patch is False
        assert cfg.fallback == "date"
        assert cfg.tag_prefix == ""

    def test_invalid_mode(self) -> None:
        with pytest.raises(ValueError):
            CalverConfig(mode="year")  # type: ignore[arg-type]

    def test_invalid_fallback(self) -> None:
        with pytest.raises(ValueError):
            CalverConfig(fallback="none")  # type: ignore[arg-type]

    def test_invalid_patch_type(self) -> None:
        with pytest.raises(ValueError, match="Invalid patch value"):
            CalverConfig(patch="yes")  # type: ignore[arg-type]

    def test_invalid_tag_prefix_type(self) -> None:
        with pytest.raises(ValueError, match="Invalid tag_prefix"):
            CalverConfig(tag_prefix=123)  # type: ignore[arg-type]


class TestLoadCalverConfig:
    """Config loading from pyproject.toml and environment."""

    def test_loads_from_pyproject(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_bytes(b"""
[tool.calver_scm]
mode = "day"
patch = false
""")
        cfg = _load_calver_config(tmp_path)
        assert cfg.mode == "day"
        assert cfg.patch is False

    def test_missing_pyproject_returns_defaults(self, tmp_path: Path) -> None:
        cfg = _load_calver_config(tmp_path)
        assert cfg == CalverConfig()

    def test_missing_section_returns_defaults(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_bytes(b"[tool.ruff]\nfix = true\n")
        cfg = _load_calver_config(tmp_path)
        assert cfg == CalverConfig()

    def test_env_overrides_toml(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_bytes(b"""
[tool.calver_scm]
mode = "month"
patch = false
fallback = "date"
tag_prefix = "v"
""")
        monkeypatch.setenv("SCM_CALVER_MODE", "day")
        monkeypatch.setenv("SCM_CALVER_PATCH", "true")
        monkeypatch.setenv("SCM_CALVER_FALLBACK", "dev")
        monkeypatch.setenv("SCM_CALVER_TAG_PREFIX", "release-")

        cfg = _load_calver_config(tmp_path)

        assert cfg.mode == "day"
        assert cfg.patch is True
        assert cfg.fallback == "dev"
        assert cfg.tag_prefix == "release-"

    def test_env_used_when_toml_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SCM_CALVER_MODE", "day")
        monkeypatch.setenv("SCM_CALVER_PATCH", "false")
        monkeypatch.setenv("SCM_CALVER_FALLBACK", "date")
        monkeypatch.setenv("SCM_CALVER_TAG_PREFIX", "x")

        cfg = _load_calver_config(tmp_path)

        assert cfg == CalverConfig(
            mode="day", patch=False, fallback="date", tag_prefix="x"
        )

    def test_env_partial_override_keeps_toml_values(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_bytes(b"""
[tool.calver_scm]
mode = "month"
patch = false
fallback = "date"
tag_prefix = "v"
""")
        monkeypatch.setenv("SCM_CALVER_PATCH", "true")

        cfg = _load_calver_config(tmp_path)

        assert cfg.mode == "month"
        assert cfg.patch is True
        assert cfg.fallback == "date"
        assert cfg.tag_prefix == "v"

    def test_invalid_toml_raises(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_bytes(b"not valid toml ][")
        with pytest.raises(RuntimeError, match=re.escape("Invalid pyproject.toml")):
            _load_calver_config(tmp_path)

    def test_invalid_config_raises(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_bytes(b'[tool.calver_scm]\nmode = "invalid"\n')
        with pytest.raises(
            RuntimeError, match=re.escape("Invalid config: Invalid mode: 'invalid'")
        ):
            _load_calver_config(tmp_path)

    def test_invalid_patch_env_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SCM_CALVER_PATCH", "maybe")
        with pytest.raises(RuntimeError, match="Invalid config"):
            _load_calver_config(tmp_path)


# noinspection PyArgumentEqualDefault
class TestParseTag:
    """Tag parsing into components."""

    def test_month_mode_with_patch(self) -> None:
        cfg = make_config()
        parsed = _parse_tag("v2026.04.1", cfg)
        assert parsed is not None
        assert _release_components(parsed, cfg) == (2026, 4, 0, 1)

    def test_month_mode_without_patch(self) -> None:
        cfg = make_config()
        parsed = _parse_tag("v2026.04", cfg)
        assert parsed is not None
        assert _release_components(parsed, cfg) == (2026, 4, 0, 0)

    def test_day_mode_with_patch(self) -> None:
        cfg = make_config(mode="day")
        parsed = _parse_tag("v2026.04.15.2", cfg)
        assert parsed is not None
        assert _release_components(parsed, cfg) == (2026, 4, 15, 2)

    def test_day_mode_without_patch(self) -> None:
        cfg = make_config(mode="day")
        parsed = _parse_tag("v2026.04.15", cfg)
        assert parsed is not None
        assert _release_components(parsed, cfg) == (2026, 4, 15, 0)

    def test_month_scheme_tag_in_day_mode(self) -> None:
        cfg = make_config(mode="day")
        parsed = _parse_tag("v2026.04.1", cfg)
        assert parsed is not None
        assert _release_components(parsed, cfg) == (2026, 4, 1, 0)

    def test_day_scheme_tag_in_month_mode(self) -> None:
        cfg = make_config(mode="month")
        parsed = _parse_tag("v2026.04.15.2", cfg)
        assert parsed is not None
        assert _release_components(parsed, cfg) is None

    def test_no_prefix(self) -> None:
        cfg = make_config(tag_prefix="")
        parsed = _parse_tag("2026.04.0", cfg)
        assert parsed is not None
        assert _release_components(parsed, cfg) == (2026, 4, 0, 0)

    def test_malformed_returns_none(self) -> None:
        cfg = make_config()
        assert _parse_tag("not-a-version", cfg) is None

    def test_non_numeric_returns_none(self) -> None:
        cfg = make_config()
        assert _parse_tag("vabc.def.ghi", cfg) is None

    def test_day_mode_two_part_release_returns_none(self) -> None:
        cfg = make_config(mode="day")
        parsed = _parse_tag("v2026.04", cfg)
        assert parsed is not None
        assert _release_components(parsed, cfg) is None


# noinspection PyArgumentEqualDefault
class TestIsSamePeriod:
    """Period comparison logic."""

    def test_same_month(self) -> None:
        cfg = make_config(mode="month")
        assert _is_same_period(TODAY, 2026, 4, 0, cfg) is True

    def test_different_month(self) -> None:
        cfg = make_config(mode="month")
        assert _is_same_period(TODAY, 2026, 3, 0, cfg) is False

    def test_different_year(self) -> None:
        cfg = make_config(mode="month")
        assert _is_same_period(TODAY, 2025, 4, 0, cfg) is False

    def test_same_day(self) -> None:
        cfg = make_config(mode="day")
        assert _is_same_period(TODAY, 2026, 4, 15, cfg) is True

    def test_different_day(self) -> None:
        cfg = make_config(mode="day")
        assert _is_same_period(TODAY, 2026, 4, 14, cfg) is False


# noinspection PyArgumentEqualDefault
class TestBase:
    """Base version string generation."""

    def test_month_mode(self) -> None:
        assert _base(TODAY, make_config(mode="month")) == "2026.04"

    def test_day_mode(self) -> None:
        assert _base(TODAY, make_config(mode="day")) == "2026.04.15"

    def test_single_digit_month_padded(self) -> None:
        assert _base(JANUARY, make_config(mode="month")) == "2026.01"

    def test_single_digit_day_padded(self) -> None:
        assert _base(JANUARY, make_config(mode="day")) == "2026.01.05"


class TestCalverScm:
    """End-to-end version generation."""

    class TestNoTag:
        """Behaviour when no tag exists."""

        def test_dev_fallback(self, freeze_april: object) -> None:
            result = calver_scm(make_version(distance=5))
            assert result == "2026.04.0.dev5"

        def test_date_fallback(self, freeze_april: object, tmp_path: Path) -> None:
            (tmp_path / "pyproject.toml").write_bytes(
                b'[tool.calver_scm]\nfallback = "date"\n'
            )
            result = calver_scm(make_version(distance=5, root=str(tmp_path)))
            assert result == "2026.04.0"

        def test_zero_distance(self, freeze_april: object) -> None:
            result = calver_scm(make_version())
            assert result == "2026.04.0.dev0"

    class TestCleanTag:
        """Behaviour on a clean-tagged commit."""

        def test_exact_version_returned(self, freeze_april: object) -> None:
            result = calver_scm(make_version(tag="v2026.04.0"))
            assert result == "2026.04.0"

        def test_patch_one_returned(self, freeze_april: object) -> None:
            result = calver_scm(make_version(tag="v2026.04.1"))
            assert result == "2026.04.1"

        def test_dirty_not_clean(self, freeze_april: object) -> None:
            result = calver_scm(make_version(tag="v2026.04.0", dirty=True))
            assert result != "2026.04.0"

        def test_nonzero_distance_not_clean(self, freeze_april: object) -> None:
            result = calver_scm(make_version(tag="v2026.04.0", distance=1))
            assert result != "2026.04.0"

    class TestSameMonth:
        """Behaviour when commits exist after tag in the same month."""

        def test_patch_incremented(self, freeze_april: object) -> None:
            result = calver_scm(make_version(tag="v2026.04.0", distance=1))
            assert result == "2026.04.1.dev1"

        def test_higher_patch(self, freeze_april: object) -> None:
            result = calver_scm(make_version(tag="v2026.04.2", distance=3))
            assert result == "2026.04.3.dev3"

        def test_patch_disabled(self, freeze_april: object, tmp_path: Path) -> None:
            (tmp_path / "pyproject.toml").write_bytes(
                b"[tool.calver_scm]\npatch = false\n"
            )
            result = calver_scm(
                make_version(tag="v2026.04.2", distance=3, root=str(tmp_path))
            )
            assert result == "2026.04.0.dev3"

    class TestNewMonth:
        """Behaviour when month changes."""

        def test_patch_resets(self, freeze_april: object) -> None:
            result = calver_scm(make_version(tag="v2026.03.2", distance=5))
            assert result == "2026.04.0.dev5"

        def test_new_year(self, freeze_april: object) -> None:
            result = calver_scm(make_version(tag="v2025.12.0", distance=3))
            assert result == "2026.04.0.dev3"

    class TestDayMode:
        """Behaviour in day mode."""

        def test_clean_tag(self, freeze_april: object, tmp_path: Path) -> None:
            (tmp_path / "pyproject.toml").write_bytes(
                b'[tool.calver_scm]\nmode = "day"\n'
            )
            result = calver_scm(make_version(tag="v2026.04.15.0", root=str(tmp_path)))
            assert result == "2026.04.15.0"

        def test_same_day_increments(
            self, freeze_april: object, tmp_path: Path
        ) -> None:
            (tmp_path / "pyproject.toml").write_bytes(
                b'[tool.calver_scm]\nmode = "day"\n'
            )
            result = calver_scm(
                make_version(tag="v2026.04.15.0", distance=2, root=str(tmp_path))
            )
            assert result == "2026.04.15.1.dev2"

        def test_new_day_resets(self, freeze_april: object, tmp_path: Path) -> None:
            (tmp_path / "pyproject.toml").write_bytes(
                b'[tool.calver_scm]\nmode = "day"\n'
            )
            result = calver_scm(
                make_version(tag="v2026.04.14.0", distance=2, root=str(tmp_path))
            )
            assert result == "2026.04.15.0.dev2"

        def test_month_scheme_tag_still_works_after_switch(
            self, freeze_april: object, tmp_path: Path
        ) -> None:
            (tmp_path / "pyproject.toml").write_bytes(
                b'[tool.calver_scm]\nmode = "day"\n'
            )
            # noinspection PyArgumentEqualDefault
            result = calver_scm(
                make_version(tag="v2026.04.1", distance=0, root=str(tmp_path))
            )
            assert result == "2026.04.01.0"

    class TestMalformedTag:
        """Behaviour with unparseable tags."""

        def test_malformed_falls_back(self, freeze_april: object) -> None:
            result = calver_scm(make_version(tag="not-a-version", distance=3))
            assert result == "2026.04.0.dev3"

        def test_incomplete_tag_falls_back(self, freeze_april: object) -> None:
            result = calver_scm(make_version(tag="v2026", distance=2))
            assert result == "2026.04.0.dev2"

        def test_malformed_tag_date_fallback(
            self, freeze_april: object, tmp_path: Path
        ) -> None:
            (tmp_path / "pyproject.toml").write_bytes(
                b'[tool.calver_scm]\nfallback = "date"\n'
            )
            result = calver_scm(
                make_version(tag="not-a-version", distance=3, root=str(tmp_path))
            )
            assert result == "2026.04.0"

        def test_incompatible_tag_date_fallback(
            self, freeze_april: object, tmp_path: Path
        ) -> None:
            (tmp_path / "pyproject.toml").write_bytes(
                b'[tool.calver_scm]\nfallback = "date"\n'
            )
            # 4-part tag in month mode: _release_components returns None → date fallback
            result = calver_scm(
                make_version(tag="v2026.04.15.2", distance=1, root=str(tmp_path))
            )
            assert result == "2026.04.0"

    class TestMonthPadding:
        """Ensure the month is always zero-padded."""

        def test_single_digit_month(self, freeze_january: object) -> None:
            result = calver_scm(make_version(distance=1))
            assert result == "2026.01.0.dev1"

        def test_double_digit_month(self, freeze_april: object) -> None:
            result = calver_scm(make_version(distance=1))
            assert result == "2026.04.0.dev1"


class TestIntegration:
    """End-to-end integration tests."""

    @pytest.mark.parametrize(
        ("tag", "expected"),
        [
            ("v2026.04.1rc2", "2026.04.1rc2"),
            ("v2026.04.1a1", "2026.04.1a1"),
            ("v2026.04.1b3", "2026.04.1b3"),
            ("v2026.04.1.dev4", "2026.04.1.dev4"),
            ("v2026.04.1+abc.def", "2026.04.1+abc.def"),
            ("v2026.04.1rc2.post3.dev4+abc", "2026.04.1rc2.post3.dev4+abc"),
        ],
    )
    def test_clean_tag_preserves_pep440_segments(
        self,
        freeze_april: object,
        tag: str,
        expected: str,
    ) -> None:
        result = calver_scm(make_version(tag=tag))
        assert result == expected

    @pytest.mark.parametrize(
        ("tag", "expected"),
        [
            ("v2026.04.15.2rc1", "2026.04.15.2rc1"),
            ("v2026.04.15.2.dev2", "2026.04.15.2.dev2"),
            ("v2026.04.15.2+linux.1", "2026.04.15.2+linux.1"),
        ],
    )
    def test_day_mode_clean_tag_preserves_pep440_segments(
        self,
        freeze_april: object,
        tmp_path: Path,
        tag: str,
        expected: str,
    ) -> None:
        (tmp_path / "pyproject.toml").write_bytes(b'[tool.calver_scm]\nmode = "day"\n')
        result = calver_scm(make_version(tag=tag, root=str(tmp_path)))
        assert result == expected

    @pytest.mark.parametrize(
        ("tag", "expected"),
        [
            ("v2026.04.1alpha2", "2026.04.1a2"),
            ("v2026.04.1preview4", "2026.04.1rc4"),
            ("v2026.04.1-r5", "2026.04.1.post5"),
            ("v2026.04.1dev", "2026.04.1.dev0"),
        ],
    )
    def test_clean_tag_normalizes_pep440_aliases(
        self,
        freeze_april: object,
        tag: str,
        expected: str,
    ) -> None:
        assert calver_scm(make_version(tag=tag)) == expected

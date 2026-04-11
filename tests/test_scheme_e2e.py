from __future__ import annotations

import datetime as dt
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from calver_scm.config import CalverConfig, CalverMode
from calver_scm.scheme import calver_scm

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.mark.parametrize(
    ("tag", "distance", "dirty", "today", "expected"),
    [
        (
            "v2026.04.2rc1.post2.dev3+abc",
            0,
            False,
            dt.date(2026, 4, 15),
            "2026.04.2rc1.post2.dev3+abc",
        ),
        ("v2026.04.2", 3, False, dt.date(2026, 4, 15), "2026.04.3.dev3"),
        ("v2026.04.2", 3, False, dt.date(2026, 5, 1), "2026.05.0.dev3"),
        ("v2026.04.2", 0, True, dt.date(2026, 4, 15), "2026.04.3.dev0"),
    ],
)
def test_calver_scm_month_mode_flows(
    write_pyproject: Callable[[str], Path],
    make_scm_version: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    tag: str,
    distance: int,
    dirty: bool,
    today: dt.date,
    expected: str,
) -> None:
    """Generate month-mode versions for clean tags, dev builds, and rollover."""
    root = write_pyproject('mode = "month"')
    monkeypatch.setattr("calver_scm.scheme._today_in_timezone", lambda _tz: today)
    version = make_scm_version(root=root, tag=tag, distance=distance, dirty=dirty)
    assert calver_scm(version) == expected


def test_calver_scm_respects_patch_false(
    write_pyproject: Callable[[str], Path],
    make_scm_version: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep patch at zero for dev builds when patch auto-increment is disabled."""
    root = write_pyproject("\n".join(['mode = "month"', "patch = false"]))
    monkeypatch.setattr(
        "calver_scm.scheme._today_in_timezone",
        lambda _tz: dt.date(2026, 4, 15),
    )
    version = make_scm_version(root=root, tag="v2026.04.2", distance=3)
    assert calver_scm(version) == "2026.04.0.dev3"


def test_calver_scm_fallback_when_no_tag_in_dev_mode(
    write_pyproject: Callable[[str], Path],
    make_scm_version: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Emit dev fallback when repository has no compatible tag yet."""
    root = write_pyproject("\n".join(['mode = "month"', 'fallback = "dev"']))
    monkeypatch.setattr(
        "calver_scm.scheme._today_in_timezone",
        lambda _tz: dt.date(2026, 4, 15),
    )
    version = make_scm_version(root=root, tag=None, distance=12)
    assert calver_scm(version) == "2026.04.0.dev12"


def test_calver_scm_fallback_when_no_tag_in_date_mode(
    write_pyproject: Callable[[str], Path],
    make_scm_version: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Emit date-only fallback when configured fallback mode is date."""
    root = write_pyproject("\n".join(['mode = "month"', 'fallback = "date"']))
    monkeypatch.setattr(
        "calver_scm.scheme._today_in_timezone",
        lambda _tz: dt.date(2026, 4, 15),
    )
    version = make_scm_version(root=root, tag=None, distance=12)
    assert calver_scm(version) == "2026.04.0"


def test_calver_scm_fallback_for_unparseable_or_incompatible_tag(
    write_pyproject: Callable[[str], Path],
    make_scm_version: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fall back when tags are invalid or do not match configured date arity."""
    root = write_pyproject('mode = "day"')
    monkeypatch.setattr(
        "calver_scm.scheme._today_in_timezone",
        lambda _tz: dt.date(2026, 4, 15),
    )

    invalid_tag = make_scm_version(root=root, tag="vnot-a-version", distance=4)
    incompatible_tag = make_scm_version(root=root, tag="v2026.04", distance=4)

    assert calver_scm(invalid_tag) == "2026.04.15.0.dev4"
    assert calver_scm(incompatible_tag) == "2026.04.15.0.dev4"


def test_calver_scm_honors_custom_tag_prefix(
    write_pyproject: Callable[[str], Path],
    make_scm_version: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Parse tags using configured custom prefixes."""
    root = write_pyproject("\n".join(['mode = "month"', 'tag_prefix = "release-"']))
    monkeypatch.setattr(
        "calver_scm.scheme._today_in_timezone",
        lambda _tz: dt.date(2026, 4, 15),
    )
    version = make_scm_version(root=root, tag="release-2026.04.2", distance=0)
    assert calver_scm(version) == "2026.04.2"


def test_semver_tag_in_history_rolls_forward_to_calver_dev_version(
    write_pyproject: Callable[[str], Path],
    make_scm_version: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Generate a CalVer dev version when the latest tag still uses SemVer."""
    root = write_pyproject('mode = "month"')
    monkeypatch.setattr(
        "calver_scm.scheme._today_in_timezone",
        lambda _tz: dt.date(2026, 4, 15),
    )
    version = make_scm_version(root=root, tag="v1.2.3", distance=7)
    assert calver_scm(version) == "2026.04.0.dev7"


def test_semver_prerelease_tag_in_history_rolls_forward_to_calver_dev_version(
    write_pyproject: Callable[[str], Path],
    make_scm_version: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Handle SemVer pre-release tags during migration,
    without blocking CalVer output.
    """
    root = write_pyproject('mode = "month"')
    monkeypatch.setattr(
        "calver_scm.scheme._today_in_timezone",
        lambda _tz: dt.date(2026, 4, 15),
    )
    version = make_scm_version(root=root, tag="v1.2.3rc1", distance=2)
    assert calver_scm(version) == "2026.04.0.dev2"


def test_clean_checkout_on_semver_tag_preserves_normalized_semver_release(
    write_pyproject: Callable[[str], Path],
    make_scm_version: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Document current clean-tag behaviour when the discovered tag is SemVer."""
    root = write_pyproject('mode = "month"')
    monkeypatch.setattr(
        "calver_scm.scheme._today_in_timezone",
        lambda _tz: dt.date(2026, 4, 15),
    )
    version = make_scm_version(root=root, tag="v1.2.3", distance=0, dirty=False)
    assert calver_scm(version) == "1.02.3"


def test_calver_scm_uses_current_directory_when_root_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolve config root from the current directory when version root is absent."""
    captured: dict[str, Path] = {}

    def fake_load(root: Path) -> CalverConfig:
        captured["root"] = root
        return CalverConfig(mode=CalverMode.MONTH)

    monkeypatch.setattr("calver_scm.scheme._load_calver_config", fake_load)
    monkeypatch.setattr(
        "calver_scm.scheme._today_in_timezone", lambda _tz: dt.date(2026, 4, 15)
    )

    version: Any = SimpleNamespace(
        config=SimpleNamespace(), tag=None, distance=2, dirty=False
    )
    assert calver_scm(version) == "2026.04.0.dev2"
    assert captured["root"] == Path(".").resolve()

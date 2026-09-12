from __future__ import annotations

import datetime as dt
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from calver_scm.config import CalverConfig, CalverMode, _load_calver_config
from calver_scm.scheme import calver_scm

if TYPE_CHECKING:
    from collections.abc import Callable


pytestmark = pytest.mark.e2e


@pytest.mark.parametrize(
    ("tag", "distance", "dirty", "today", "expected"),
    [
        (
            "v2026.04.2rc1.post2.dev3+abc",
            0,
            False,
            dt.date(2026, 4, 15),
            "2026.4.2rc1.post2.dev3+abc",
        ),
        ("v2026.04.2", 3, False, dt.date(2026, 4, 15), "2026.4.3.dev3"),
        ("v2026.04.2", 3, False, dt.date(2026, 5, 1), "2026.5.0.dev3"),
        ("v2026.04.2", 0, True, dt.date(2026, 4, 15), "2026.4.3.dev0"),
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
    assert calver_scm(version) == "2026.4.0.dev3"


@pytest.mark.parametrize(
    ("patch", "no_dev", "tag", "distance", "today", "expected"),
    [
        # patch=True, no_dev=False (default behavior)
        (True, False, "v2026.04.2", 3, dt.date(2026, 4, 15), "2026.4.3.dev3"),
        (True, False, "v2026.04.2", 3, dt.date(2026, 5, 1), "2026.5.0.dev3"),
        (True, False, None, 12, dt.date(2026, 4, 15), "2026.4.0.dev12"),
        # patch=True, no_dev=True (increment patch, suppress dev suffix)
        (True, True, "v2026.04.2", 3, dt.date(2026, 4, 15), "2026.4.3"),
        (True, True, "v2026.04.2", 3, dt.date(2026, 5, 1), "2026.5.0"),
        (True, True, None, 12, dt.date(2026, 4, 15), "2026.4.0"),
        # patch=False, no_dev=False (keep patch 0, include dev suffix)
        (False, False, "v2026.04.2", 3, dt.date(2026, 4, 15), "2026.4.0.dev3"),
        (False, False, "v2026.04.2", 3, dt.date(2026, 5, 1), "2026.5.0.dev3"),
        (False, False, None, 12, dt.date(2026, 4, 15), "2026.4.0.dev12"),
        # patch=False, no_dev=True (keep patch 0, suppress dev suffix)
        (False, True, "v2026.04.2", 3, dt.date(2026, 4, 15), "2026.4.0"),
        (False, True, "v2026.04.2", 3, dt.date(2026, 5, 1), "2026.5.0"),
        (False, True, None, 12, dt.date(2026, 4, 15), "2026.4.0"),
    ],
)
def test_calver_scm_patch_and_no_dev_combinations(
    write_pyproject: Callable[[str], Path],
    make_scm_version: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    patch: bool,
    no_dev: bool,
    tag: str | None,
    distance: int,
    today: dt.date,
    expected: str,
) -> None:
    """Verify version outputs across all patch and no_dev configuration combinations."""
    patch_str = "true" if patch else "false"
    no_dev_str = "true" if no_dev else "false"
    root = write_pyproject(
        "\n".join(['mode = "month"', f"patch = {patch_str}", f"no_dev = {no_dev_str}"])
    )
    monkeypatch.setattr("calver_scm.scheme._today_in_timezone", lambda _tz: today)
    version = make_scm_version(root=root, tag=tag, distance=distance)
    assert calver_scm(version) == expected


@pytest.mark.parametrize(
    ("tag", "distance", "dirty", "today", "expected"),
    [
        ("v2026.04.2", 3, False, dt.date(2026, 4, 15), "2026.4.3"),
        ("v2026.04.2", 3, False, dt.date(2026, 5, 1), "2026.5.0"),
        ("v2026.04.2", 0, True, dt.date(2026, 4, 15), "2026.4.3"),
    ],
)
def test_calver_scm_respects_no_dev(
    write_pyproject: Callable[[str], Path],
    make_scm_version: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    tag: str,
    distance: int,
    dirty: bool,
    today: dt.date,
    expected: str,
) -> None:
    """Suppress dev suffix on non-exact versions when no_dev is enabled."""
    root = write_pyproject("\n".join(['mode = "month"', "no_dev = true"]))
    monkeypatch.setattr("calver_scm.scheme._today_in_timezone", lambda _tz: today)
    version = make_scm_version(root=root, tag=tag, distance=distance, dirty=dirty)
    assert calver_scm(version) == expected


def test_calver_scm_respects_no_dev_env_override(
    write_pyproject: Callable[[str], Path],
    make_scm_version: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Suppress dev suffix when CALVER_SCM_NO_DEV environment variable is set."""
    root = write_pyproject('mode = "month"')
    monkeypatch.setenv("CALVER_SCM_NO_DEV", "true")
    monkeypatch.setattr(
        "calver_scm.scheme._today_in_timezone",
        lambda _tz: dt.date(2026, 4, 15),
    )
    version = make_scm_version(root=root, tag="v2026.04.2", distance=3)
    assert calver_scm(version) == "2026.4.3"


def test_calver_scm_fallback_when_no_tag_in_no_dev_mode(
    write_pyproject: Callable[[str], Path],
    make_scm_version: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Emit clean fallback version without dev suffix when no_dev is enabled."""
    root = write_pyproject("\n".join(['mode = "month"', "no_dev = true"]))
    monkeypatch.setattr(
        "calver_scm.scheme._today_in_timezone",
        lambda _tz: dt.date(2026, 4, 15),
    )
    version = make_scm_version(root=root, tag=None, distance=12)
    assert calver_scm(version) == "2026.4.0"


def test_calver_scm_respects_no_dev_with_unstable_mode(
    write_pyproject: Callable[[str], Path],
    make_scm_version: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Apply unstable prefix and suppress dev suffix for unstable no_dev builds."""
    root = write_pyproject(
        "\n".join(['mode = "month"', "stable = false", "no_dev = true"])
    )
    monkeypatch.setattr(
        "calver_scm.scheme._today_in_timezone",
        lambda _tz: dt.date(2026, 4, 15),
    )
    version = make_scm_version(root=root, tag="v2026.04.2", distance=3)
    assert calver_scm(version) == "0.2026.4.3"

    fallback_version = make_scm_version(root=root, tag=None, distance=12)
    assert calver_scm(fallback_version) == "0.2026.4.0"


@pytest.mark.parametrize(
    ("tag", "distance", "dirty", "expected"),
    [
        ("v2026.04.2", 0, False, "0.2026.4.2"),
        ("v2026.04.2rc1.post2.dev3+abc", 0, False, "0.2026.4.2rc1.post2.dev3+abc"),
        ("v2026.04.2", 3, False, "0.2026.4.3.dev3"),
        ("v2026.04.2", 0, True, "0.2026.4.3.dev0"),
    ],
)
def test_calver_scm_prepends_zero_prefix_when_stable_false(
    write_pyproject: Callable[[str], Path],
    make_scm_version: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    tag: str,
    distance: int,
    dirty: bool,
    expected: str,
) -> None:
    """Prefix all generated outputs with `0.` when project stability is disabled."""
    root = write_pyproject("\n".join(['mode = "month"', "stable = false"]))
    monkeypatch.setattr(
        "calver_scm.scheme._today_in_timezone",
        lambda _tz: dt.date(2026, 4, 15),
    )
    version = make_scm_version(root=root, tag=tag, distance=distance, dirty=dirty)
    assert calver_scm(version) == expected


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
    assert calver_scm(version) == "2026.4.0.dev12"


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
    assert calver_scm(version) == "2026.4.0"


@pytest.mark.parametrize(
    ("fallback", "expected"),
    [
        ("dev", "0.2026.4.0.dev12"),
        ("date", "0.2026.4.0"),
    ],
)
def test_calver_scm_prepends_zero_prefix_for_unstable_fallback_modes(
    write_pyproject: Callable[[str], Path],
    make_scm_version: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    fallback: str,
    expected: str,
) -> None:
    """Apply unstable prefix to fallback outputs regardless of fallback mode."""
    root = write_pyproject(
        "\n".join(['mode = "month"', "stable = false", f'fallback = "{fallback}"'])
    )
    monkeypatch.setattr(
        "calver_scm.scheme._today_in_timezone",
        lambda _tz: dt.date(2026, 4, 15),
    )
    version = make_scm_version(root=root, tag=None, distance=12)
    assert calver_scm(version) == expected


def test_calver_scm_fallback_for_unparsable_or_incompatible_tag(
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

    assert calver_scm(invalid_tag) == "2026.4.15.0.dev4"
    assert calver_scm(incompatible_tag) == "2026.4.15.0.dev4"


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
    assert calver_scm(version) == "2026.4.2"


def test_clean_checkout_preserves_local_tag_segment(
    write_pyproject: Callable[[str], Path],
    make_scm_version: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preserve tag local metadata on clean checkouts, including normalisation."""
    root = write_pyproject('mode = "month"')
    monkeypatch.setattr(
        "calver_scm.scheme._today_in_timezone",
        lambda _tz: dt.date(2026, 4, 15),
    )
    version = make_scm_version(
        root=root,
        tag="v2026.04.2+linux.x86_64",
        distance=0,
        dirty=False,
    )
    assert calver_scm(version) == "2026.4.2+linux.x86.64"


@pytest.mark.parametrize(
    ("tag", "distance", "dirty", "today", "expected"),
    [
        ("v1.2.3", 7, False, dt.date(2026, 4, 15), "2026.4.0.dev7"),
        ("v1.2.3", 0, True, dt.date(2026, 4, 15), "2026.4.0.dev0"),
        ("v1.2.3", 3, True, dt.date(2026, 4, 15), "2026.4.0.dev3"),
        ("v1.2.3rc1", 2, False, dt.date(2026, 4, 15), "2026.4.0.dev2"),
        ("v1.0", 4, False, dt.date(2026, 4, 15), "2026.4.0.dev4"),
        ("v0.1.0", 5, False, dt.date(2026, 4, 15), "2026.4.0.dev5"),
        ("1.2.3", 6, False, dt.date(2026, 4, 15), "2026.4.0.dev6"),
        ("v2025.12.1", 5, False, dt.date(2026, 4, 15), "2026.4.0.dev5"),
        ("v2025.12.1", 0, True, dt.date(2026, 4, 15), "2026.4.0.dev0"),
        ("v2025.12.1", 3, True, dt.date(2026, 4, 15), "2026.4.0.dev3"),
        ("v2025.12.31.2", 4, False, dt.date(2026, 4, 15), "2026.4.0.dev4"),
    ],
)
def test_old_formatted_tag_in_history_rolls_forward_to_calver_dev_version(
    write_pyproject: Callable[[str], Path],
    make_scm_version: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    tag: str,
    distance: int,
    dirty: bool,
    today: dt.date,
    expected: str,
) -> None:
    """Roll forward to CalVer dev version when latest history tag is older format."""
    root = write_pyproject('mode = "month"')
    monkeypatch.setattr("calver_scm.scheme._today_in_timezone", lambda _tz: today)
    version = make_scm_version(root=root, tag=tag, distance=distance, dirty=dirty)
    assert calver_scm(version) == expected


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("v1.2.3", "1.2.3"),
        ("v1.0", "1.0.0"),
        ("v2025.12.1", "2025.12.1"),
        ("v2025.12", "2025.12.0"),
    ],
)
def test_clean_checkout_on_old_formatted_tag_preserves_normalized_release(
    write_pyproject: Callable[[str], Path],
    make_scm_version: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    tag: str,
    expected: str,
) -> None:
    """Document clean-tag behaviour when the discovered tag uses an older format."""
    root = write_pyproject('mode = "month"')
    monkeypatch.setattr(
        "calver_scm.scheme._today_in_timezone",
        lambda _tz: dt.date(2026, 4, 15),
    )
    version = make_scm_version(root=root, tag=tag, distance=0, dirty=False)
    assert calver_scm(version) == expected


def test_calver_scm_uses_project_root_from_absolute_root_and_project_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Use the package-local config when setuptools-scm uses the shared root."""
    repo_root = tmp_path / "repo"
    pkg_root = repo_root / "packages" / "foo"
    pkg_root.mkdir(parents=True)

    (pkg_root / "pyproject.toml").write_text(
        "\n".join(
            [
                "[tool.calver-scm]",
                'mode = "day"',
                'tag_prefix = "foo-v"',
            ]
        ),
        encoding="utf-8",
    )

    captured: dict[str, Path] = {}

    def fake_load(root: Path) -> CalverConfig:
        captured["root"] = root
        return _load_calver_config(root)

    monkeypatch.setattr("calver_scm.scheme._load_calver_config", fake_load)
    monkeypatch.setattr(
        "calver_scm.scheme._today_in_timezone", lambda _tz: dt.date(2026, 4, 15)
    )

    version: Any = SimpleNamespace(
        config=SimpleNamespace(
            absolute_root=str(repo_root),
            project_path=Path("packages/foo"),
            root="../..",
        ),
        tag=None,
        distance=2,
        dirty=False,
    )
    assert calver_scm(version) == "2026.4.15.0.dev2"
    assert captured["root"] == pkg_root.resolve()


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
    assert calver_scm(version) == "2026.4.0.dev2"
    assert captured["root"] == Path(".").resolve()

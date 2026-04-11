from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

# noinspection PyProtectedMember
from calver_scm.config import _load_calver_config

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from pathlib import Path


_SCOPE_MARKERS = ("unit", "e2e")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Fail collection when tests are missing or mixing scope markers."""
    missing_scope: list[str] = []
    multiple_scope: list[str] = []

    for item in items:
        matched = [name for name in _SCOPE_MARKERS if item.get_closest_marker(name)]
        if not matched:
            missing_scope.append(item.nodeid)
        elif len(matched) > 1:
            multiple_scope.append(item.nodeid)

    if not missing_scope and not multiple_scope:
        return

    errors: list[str] = []
    if missing_scope:
        errors.append(
            "Tests missing scope marker (choose one: unit, e2e):\n- "
            + "\n- ".join(missing_scope)
        )
    if multiple_scope:
        errors.append(
            "Tests with multiple scope markers (choose exactly one):\n- "
            + "\n- ".join(multiple_scope)
        )

    raise pytest.UsageError("\n\n".join(errors))


@pytest.fixture(autouse=True)
def clear_config_cache() -> Generator[None, None, None]:
    """Clear cached config reads between tests for deterministic behaviour."""
    _load_calver_config.cache_clear()
    yield
    _load_calver_config.cache_clear()


@pytest.fixture
def make_scm_version() -> Callable[..., Any]:
    """Build lightweight setuptools-scm-like version objects for tests."""

    def _make(
        *,
        root: Path,
        tag: str | None,
        distance: int,
        dirty: bool = False,
    ) -> Any:
        return SimpleNamespace(
            config=SimpleNamespace(root=root),
            tag=tag,
            distance=distance,
            dirty=dirty,
        )

    return _make


@pytest.fixture
def write_pyproject(tmp_path: Path) -> Callable[[str], Path]:
    """Write a pyproject.toml and return the temp project root path."""

    def _write(tool_calver_block: str) -> Path:
        content = "\n".join(
            [
                "[project]",
                'name = "demo"',
                'version = "0.0.0"',
                "",
                "[tool.calver_scm]",
                tool_calver_block.strip(),
                "",
            ]
        )
        (tmp_path / "pyproject.toml").write_text(content, encoding="utf-8")
        return tmp_path

    return _write

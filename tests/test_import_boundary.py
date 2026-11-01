from __future__ import annotations

import subprocess
import sys

import pytest

pytestmark = pytest.mark.unit

PURE_MODULES = [
    "models",
    "engine",
    "parser",
    "utils",
    "calver_version",
    "config",
    "validation",
    "release",
]


@pytest.mark.parametrize("module", PURE_MODULES)
def test_pure_modules_do_not_import_setuptools_scm(module: str) -> None:
    """Keep the domain engine and its helpers free of setuptools-scm."""
    code = f"import sys, calver_scm.{module}; sys.exit('setuptools_scm' in sys.modules)"
    result = subprocess.run(
        [sys.executable, "-I", "-c", code], check=False, capture_output=True
    )
    assert result.returncode == 0, result.stderr.decode()

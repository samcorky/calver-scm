from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

EXIT_OK = 0
EXIT_USAGE_ERROR = 2

MISSING_EXTRA_MESSAGE = (
    "The calver-scm command line requires the 'cli' extra.\n"
    "Install it with: pip install 'calver-scm[cli]'"
)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the calver-scm command line and return its exit code.

    The console script is installed even without the `cli` extra, so Cyclopts is
    imported here rather than at module level.
    """
    try:
        import cyclopts

        from calver_scm.cli_app import app
    except ImportError:
        print(MISSING_EXTRA_MESSAGE, file=sys.stderr)
        return EXIT_USAGE_ERROR

    try:
        result = app.meta(
            None if argv is None else list(argv),
            result_action="return_value",
        )
    except cyclopts.CycloptsError:
        return EXIT_USAGE_ERROR
    return EXIT_OK if result is None else int(result)

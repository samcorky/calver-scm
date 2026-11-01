from __future__ import annotations

import sys
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Annotated

import cyclopts

from calver_scm.cli_output import Output, OutputFormat, resolve_format
from calver_scm.cli_support import ResolutionError, resolve_build_version
from calver_scm.config import _load_calver_config
from calver_scm.validation import validate_version

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_RESOLUTION_ERROR = 2

app = cyclopts.App(
    name="calver-scm",
    help="Inspect and validate CalVer versions for setuptools-scm projects.",
    version=package_version("calver-scm"),
    exit_on_error=False,
    print_error=True,
)

# Injected by the launcher; never parsed from the command line.
OutputParameter = Annotated[Output, cyclopts.Parameter(parse=False)]


@app.meta.default
def launcher(
    *tokens: Annotated[str, cyclopts.Parameter(show=False, allow_leading_hyphen=True)],
    output_format: Annotated[
        OutputFormat, cyclopts.Parameter(name="--format")
    ] = OutputFormat.AUTO,
    as_json: Annotated[bool, cyclopts.Parameter(name="--json", negative="")] = False,
) -> int:
    """Resolve the output format, then run the requested command.

    Parameters
    ----------
    output_format
        auto (default) is rich on a terminal and plain otherwise; plain is one
        value per line for scripts; json is machine-readable.
    as_json
        Shorthand for --format json.
    """
    requested = OutputFormat.JSON if as_json else output_format
    output = Output(resolve_format(requested, is_tty=sys.stdout.isatty()))
    command, bound, ignored = app.parse_args(tokens)
    extra = dict.fromkeys(ignored, output)
    return int(command(*bound.args, **bound.kwargs, **extra))


@app.command
def version(
    *,
    root: Annotated[Path, cyclopts.Parameter(name="--root")] = Path(),
    output: OutputParameter,
) -> int:
    """Print the version the project's build would produce.

    Parameters
    ----------
    root
        Project directory containing pyproject.toml.
    """
    try:
        resolved = resolve_build_version(root)
    except ResolutionError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_RESOLUTION_ERROR
    output.version(resolved)
    return EXIT_OK


@app.command
def validate(
    candidate: str,
    *,
    tag: Annotated[bool, cyclopts.Parameter(name="--tag", negative="")] = False,
    root: Annotated[Path, cyclopts.Parameter(name="--root")] = Path(),
    output: OutputParameter,
) -> int:
    """Check a version or Git tag against the project's CalVer configuration.

    Needs no Git checkout. The verdict is written to stdout; the exit code is 0
    when valid and 1 when not.

    Parameters
    ----------
    candidate
        The version, or the full Git tag when --tag is given.
    tag
        Treat the input as a Git tag that includes the configured tag prefix.
    root
        Project directory whose pyproject.toml holds [tool.calver-scm].
    """
    try:
        config = _load_calver_config(root.resolve())
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_RESOLUTION_ERROR
    result = validate_version(candidate, config, is_tag=tag)
    output.validation(result)
    return EXIT_OK if result.valid else EXIT_INVALID

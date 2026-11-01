from __future__ import annotations

import sys
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Annotated

import cyclopts

from calver_scm.cli_output import Output, OutputFormat, resolve_format
from calver_scm.cli_support import (
    ResolutionError,
    explain_build_version,
    is_shallow_repository,
    list_local_tags,
    resolve_build_version,
)
from calver_scm.config import _load_calver_config
from calver_scm.diagnostics import Severity, diagnose
from calver_scm.release import NextTagError, plan_next_tag
from calver_scm.utils import _today_in_timezone
from calver_scm.validation import validate_version

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_RESOLUTION_ERROR = 2
EXIT_TAG_UNAVAILABLE = 3

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


@app.command
def explain(
    *,
    root: Annotated[Path, cyclopts.Parameter(name="--root")] = Path(),
    output: OutputParameter,
) -> int:
    """Show how the build version was derived.

    Reports the SCM facts setuptools-scm supplied, the date and configuration
    in effect, which branch of the CalVer algorithm ran, and the local segment
    added afterwards by setuptools-scm. Absolute paths are never printed.

    Parameters
    ----------
    root
        Project directory containing pyproject.toml.
    """
    try:
        explanation = explain_build_version(root)
    except ResolutionError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_RESOLUTION_ERROR
    output.explanation(explanation)
    return EXIT_OK


@app.command
def doctor(
    *,
    root: Annotated[Path, cyclopts.Parameter(name="--root")] = Path(),
    output: OutputParameter,
) -> int:
    """Diagnose problems that stop or distort version resolution.

    Every check runs even if another fails. Warnings never cause a failing exit
    code; errors do.

    Parameters
    ----------
    root
        Project directory containing pyproject.toml.
    """
    report = diagnose(root)
    output.report(report)
    return EXIT_INVALID if report.status is Severity.ERROR else EXIT_OK


@app.command
def next_tag(
    *,
    root: Annotated[Path, cyclopts.Parameter(name="--root")] = Path(),
    output: OutputParameter,
) -> int:
    """Propose the next release tag. Read-only: nothing is created or pushed.

    Considers every local tag, not only those reachable from HEAD, so a number
    already used on another branch is never reused. Exits 3 when no safe tag can
    be proposed: a shallow clone, or `patch = false` with the period already
    released. Tags on the remote that have not been fetched cannot be seen.

    Parameters
    ----------
    root
        Project directory containing pyproject.toml.
    """
    try:
        config = _load_calver_config(root.resolve())
        if is_shallow_repository(root):
            raise NextTagError(
                "shallow_checkout",
                "this is a shallow clone, so existing tags cannot be trusted; "
                "run 'git fetch --unshallow --tags'",
            )
        plan = plan_next_tag(
            list_local_tags(root), config, today=_today_in_timezone(config.timezone)
        )
    except (RuntimeError, ResolutionError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_RESOLUTION_ERROR
    except NextTagError as e:
        print(f"error: {e.message} [{e.code}]", file=sys.stderr)
        return EXIT_TAG_UNAVAILABLE
    output.next_tag(plan)
    return EXIT_OK

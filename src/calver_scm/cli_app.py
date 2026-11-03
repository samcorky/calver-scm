from __future__ import annotations

import datetime  # noqa: TC003 - Cyclopts needs it at runtime
import sys
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Annotated

import cyclopts

from calver_scm.cli_output import Output, OutputFormat, resolve_format
from calver_scm.cli_support import (
    ResolutionError,
    commits_since,
    explain_build_version,
    is_shallow_repository,
    list_local_tags,
    resolve_build_version,
)
from calver_scm.config import _load_calver_config
from calver_scm.diagnostics import Severity, diagnose
from calver_scm.models import ResolutionReason
from calver_scm.release import (
    NextTagError,
    NextTagReason,
    PreReleaseChannel,
    plan_next_tag,
)
from calver_scm.utils import _today_in_timezone
from calver_scm.validation import validate_version

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_RESOLUTION_ERROR = 2
EXIT_TAG_UNAVAILABLE = 3


def _reasons(enum: type[ResolutionReason] | type[NextTagReason]) -> str:
    """List an enum's reasons with their wording, as a Markdown table."""
    rows = "\n".join(f"| `{r.value}` | **{r.label}.** {r.description} |" for r in enum)
    return f"| Reason | Meaning |\n|---|---|\n{rows}"


ROOT_EPILOGUE = """\
**Examples**

```
calver-scm version                    # the version your build would produce
calver-scm explain                    # how that version was derived
calver-scm doctor                     # check the setup for problems
calver-scm next-tag                   # the next release tag (read-only)
calver-scm validate v2026.4.2 --tag   # check a tag against your scheme
calver-scm --json version             # machine-readable output
```

**Exit codes**

| Code | Meaning |
|---|---|
| `0` | Success. |
| `1` | `validate`: the input is invalid. `doctor`: errors were found. |
| `2` | Bad usage, invalid configuration, or the version could not be resolved. |
| `3` | `next-tag`: no safe tag can be proposed. |

Run `calver-scm COMMAND --help` for details on one command."""

app = cyclopts.App(
    name="calver-scm",
    help="Inspect, explain and validate CalVer versions for setuptools-scm projects.",
    help_epilogue=ROOT_EPILOGUE,
    help_format="markdown",
    version=package_version("calver-scm"),
    exit_on_error=False,
    print_error=True,
)

RootOption = Annotated[Path, cyclopts.Parameter(name=("--root", "-r"))]

# Injected by the launcher; never parsed from the command line.
OutputParameter = Annotated[Output, cyclopts.Parameter(parse=False)]


@app.meta.default
def launcher(
    *tokens: Annotated[str, cyclopts.Parameter(show=False, allow_leading_hyphen=True)],
    output_format: Annotated[
        OutputFormat, cyclopts.Parameter(name=("--format", "-f"), group="Output")
    ] = OutputFormat.AUTO,
    as_json: Annotated[
        bool,
        cyclopts.Parameter(
            name=("--json", "-j"),
            negative="",
            group="Output",
            show_default=False,
        ),
    ] = False,
) -> int:
    """Resolve the output format, then run the requested command.

    Parameters
    ----------
    output_format
        How to print the result: auto (rich on a terminal, otherwise plain),
        rich, plain (stable, for scripts) or json.
    as_json
        Same as `--format json`.
    """
    requested = OutputFormat.JSON if as_json else output_format
    output = Output(resolve_format(requested, is_tty=sys.stdout.isatty()))
    command, bound, ignored = app.parse_args(tokens)
    extra = dict.fromkeys(ignored, output)
    result = command(*bound.args, **bound.kwargs, **extra)
    # The built-in help page, shown when no command is given, returns None.
    return EXIT_OK if result is None else int(result)


@app.command(
    help_epilogue="""\
**Examples**

```
calver-scm version
calver-scm version --root ./backend
VERSION=$(calver-scm version)   # plain output is just the version
calver-scm --json version
```"""
)
def version(
    *,
    root: RootOption = Path(),
    output: OutputParameter,
) -> int:
    """Print the full version the project's build would produce.

    Reads the setuptools-scm or Hatch-VCS settings from `pyproject.toml` and asks
    setuptools-scm, so the result includes your `local_scheme` and any
    `CALVER_SCM_*` overrides.

    Parameters
    ----------
    root
        Project directory containing `pyproject.toml`.
    """
    try:
        resolved = resolve_build_version(root)
    except ResolutionError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_RESOLUTION_ERROR
    output.version(resolved)
    return EXIT_OK


@app.command(
    help_epilogue="""\
**Examples**

```
calver-scm validate 2026.4.2
calver-scm validate v2026.4.2 --tag   # also requires the configured tag prefix
calver-scm --json validate 2026.13.1
```

**Exit codes:** `0` valid, `1` invalid, `2` the project configuration is unusable."""
)
def validate(
    version: str,
    /,
    *,
    tag: Annotated[
        bool, cyclopts.Parameter(name=("--tag", "-t"), negative="", show_default=False)
    ] = False,
    root: RootOption = Path(),
    output: OutputParameter,
) -> int:
    """Check a version or Git tag against the project's CalVer configuration.

    Checks PEP 440 syntax, then the scheme: the number of date components,
    calendar ranges and the stable setting. Pre-release, post-release, dev and
    local suffixes are accepted. Needs no Git checkout.

    Parameters
    ----------
    version
        The version to check, or the full Git tag when `--tag` is given.
    tag
        Treat the input as a Git tag that includes the configured tag prefix.
    root
        Project directory whose `pyproject.toml` holds `[tool.calver-scm]`.
    """
    try:
        config = _load_calver_config(root.resolve())
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_RESOLUTION_ERROR
    result = validate_version(version, config, is_tag=tag)
    output.validation(result)
    return EXIT_OK if result.valid else EXIT_INVALID


@app.command(
    help_epilogue=f"""\
**Examples**

```
calver-scm explain
calver-scm --json explain
```

**Reasons**

{_reasons(ResolutionReason)}"""
)
def explain(
    *,
    root: RootOption = Path(),
    output: OutputParameter,
) -> int:
    """Show how the build version was derived.

    Reports the tag, commit distance and dirty flag that setuptools-scm
    supplied, the date and configuration in effect, which branch of the
    algorithm ran, and the local segment setuptools-scm added afterwards.
    Absolute paths are never printed.

    Parameters
    ----------
    root
        Project directory containing `pyproject.toml`.
    """
    try:
        explanation = explain_build_version(root)
    except ResolutionError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_RESOLUTION_ERROR
    output.explanation(explanation)
    return EXIT_OK


@app.command(
    help_epilogue="""\
**Examples**

```
calver-scm doctor
calver-scm --json doctor
```

**Severities:** `ok`; `info` (for your awareness); `warning` (may give a surprising
version); `error` (resolution is broken).

**Exit codes:** `0` no errors (warnings are allowed), `1` errors were found."""
)
def doctor(
    *,
    root: RootOption = Path(),
    output: OutputParameter,
) -> int:
    """Diagnose problems that stop or distort version resolution.

    Checks the build configuration, the CalVer settings and environment
    overrides, that Git is available and the version resolves, and warns about
    shallow clones, a missing compatible tag and `no_dev` with a local segment.
    Every check runs even if another fails.

    Parameters
    ----------
    root
        Project directory containing `pyproject.toml`.
    """
    report = diagnose(root)
    output.report(report)
    return EXIT_INVALID if report.status is Severity.ERROR else EXIT_OK


@app.command(
    help_epilogue=f"""\
**Examples**

```
calver-scm next-tag
git tag "$(calver-scm next-tag)"   # plain output is just the tag
calver-scm next-tag --pre rc       # the next release candidate, e.g. v2026.4.3rc1
calver-scm next-tag --promote      # finalise the candidate: v2026.4.3rc2 -> v2026.4.3
calver-scm next-tag --post         # post-release of the latest: v2026.4.2.post1
calver-scm --json next-tag
```

**Reasons**

{_reasons(NextTagReason)}

**Exit codes:** `0` a tag was proposed, `2` unusable configuration or not a Git
repository, `3` no safe tag (a shallow clone, `patch = false` and the period is
already released, or `--promote` with no pre-release to promote or one that is not an
ancestor of HEAD, or `--post` with no release in the period)."""
)
def next_tag(
    *,
    date: Annotated[
        datetime.date | None, cyclopts.Parameter(name=("--date", "-d"))
    ] = None,
    pre: Annotated[PreReleaseChannel | None, cyclopts.Parameter(name="--pre")] = None,
    promote: Annotated[
        bool, cyclopts.Parameter(name="--promote", negative="", show_default=False)
    ] = False,
    post: Annotated[
        bool, cyclopts.Parameter(name="--post", negative="", show_default=False)
    ] = False,
    root: RootOption = Path(),
    output: OutputParameter,
) -> int:
    """Propose the next release tag. Read-only: nothing is created or pushed.

    Considers every local tag, not only those reachable from HEAD, so a number
    already used on another branch is never reused. Pre-releases occupy no
    final number. Tags that exist only on the remote and have not been
    fetched cannot be seen: run `git fetch --tags` first.

    Parameters
    ----------
    date
        Plan for this calendar date (YYYY-MM-DD) instead of today. The
        configured timezone does not apply to it.
    pre
        Propose the next pre-release (a, b or rc) of the release that would
        otherwise be proposed, such as v2026.4.3rc1 then v2026.4.3rc2. Numbers
        are counted separately for each channel.
    promote
        Propose the final tag for the latest pre-release of the release that
        would otherwise be proposed, such as v2026.4.3 for v2026.4.3rc2. Fails
        if there is no pre-release, or it is not an ancestor of HEAD, and
        warns if HEAD has moved on since it.
    post
        Propose the next post-release of the latest release in the period, such
        as v2026.4.2.post1. Unlike a final tag it works with `patch = false`,
        and fails only if the period has no release.

    `--pre`, `--promote` and `--post` cannot be combined.
    root
        Project directory containing `pyproject.toml`.
    """
    if sum((pre is not None, promote, post)) > 1:
        print("error: --pre, --promote and --post cannot be combined", file=sys.stderr)
        return EXIT_RESOLUTION_ERROR
    try:
        config = _load_calver_config(root.resolve())
        if is_shallow_repository(root):
            raise NextTagError(
                "shallow_checkout",
                "this is a shallow clone, so existing tags cannot be trusted; "
                "run 'git fetch --unshallow --tags'",
            )
        plan = plan_next_tag(
            list_local_tags(root),
            config,
            today=date or _today_in_timezone(config.timezone),
            pre=pre,
            promote=promote,
            post=post,
        )
        if promote and plan.latest_tag is not None:
            _check_promotion(root, plan.latest_tag)
    except (RuntimeError, ResolutionError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_RESOLUTION_ERROR
    except NextTagError as e:
        print(f"error: {e.message} [{e.code}]", file=sys.stderr)
        return EXIT_TAG_UNAVAILABLE
    output.next_tag(plan)
    return EXIT_OK


def _check_promotion(root: Path, prerelease: str) -> None:
    """Refuse a pre-release HEAD does not contain; warn if HEAD has moved on."""
    ahead = commits_since(root, prerelease)
    if ahead is None:
        raise NextTagError(
            "prerelease_not_ancestor",
            f"{prerelease} is not an ancestor of HEAD, so the final tag would not "
            "contain what was tested",
        )
    if ahead:
        print(
            f"warning: HEAD is {ahead} commit{'s' if ahead != 1 else ''} ahead of "
            f"{prerelease}, which is the release candidate being promoted",
            file=sys.stderr,
        )

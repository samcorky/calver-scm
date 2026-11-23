from __future__ import annotations

import datetime  # noqa: TC003 - Cyclopts needs it at runtime
import os
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
    list_head_tags,
    list_local_tags,
    resolve_build_version,
)
from calver_scm.config import CalverConfig, _load_calver_config
from calver_scm.diagnostics import Severity, diagnose
from calver_scm.models import ResolutionReason
from calver_scm.release import (
    NextTagError,
    NextTagReason,
    PreReleaseChannel,
    classify_tags,
    plan_next_tag,
)
from calver_scm.utils import _today_in_timezone
from calver_scm.validation import (
    ValidationResult,
    is_other_stability,
    newest_in_scopes,
    validate_against_repo,
    validate_version,
    version_order_key,
)

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_RESOLUTION_ERROR = 2
EXIT_TAG_UNAVAILABLE = 3


def _kinds() -> str:
    """List the tag kinds with what each means for numbering, as a Markdown table."""
    return (
        "| Kind | Meaning |\n|---|---|\n"
        "| `final` | A release. It occupies its patch number. |\n"
        "| `postrelease` | A post-release. It occupies its number too. |\n"
        "| `prerelease` | A pre-release (`a`, `b`, `rc`). Not counted for finals. |\n"
        "| `dev` | A dev release. Not counted. |\n"
        "| `ignored` | Does not fit the scheme; the reason is shown. |"
    )


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
calver-scm tags                       # how each local tag is read
calver-scm validate v2026.4.2 --tag   # check a tag against your scheme
calver-scm parse v2026.4.2 --tag      # split a tag into its parts
calver-scm compare 2026.4.2 2026.4.3  # which is older: less, equal or greater
calver-scm sort 2026.4.10 2026.4.2    # put versions in order
calver-scm --json version             # machine-readable output
```

**Exit codes**

| Code | Meaning |
|---|---|
| `0` | Success. |
| `1` | `validate`, `parse`, `compare`, `sort`: an input is invalid. `doctor`: errors. |
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
    summary: Annotated[
        bool,
        cyclopts.Parameter(negative="", group="Output", show_default=False),
    ] = False,
) -> int:
    """Resolve the output format, then run the requested command.

    Parameters
    ----------
    output_format
        How to print the result: auto (rich on a terminal, otherwise plain),
        rich, plain (stable, for scripts), json, or github (append the result
        to `$GITHUB_OUTPUT` for `version`, `next-tag`, `validate` and `parse`).
    as_json
        Same as `--format json`.
    summary
        Also append a Markdown report of the result to `$GITHUB_STEP_SUMMARY`,
        which GitHub Actions shows on the run page. Works with every command and
        every format.
    """
    requested = OutputFormat.JSON if as_json else output_format
    resolved = resolve_format(requested, is_tty=sys.stdout.isatty())
    command, bound, ignored = app.parse_args(tokens)
    github_output = None
    if resolved is OutputFormat.GITHUB:
        if command in _NO_GITHUB_OUTPUT:
            print(
                f"error: --format github is not supported by "
                f"{command.__name__.replace('_', '-')}; use it with version, "
                "next-tag, validate, parse or compare, or add --summary for a "
                "job summary",
                file=sys.stderr,
            )
            return EXIT_RESOLUTION_ERROR
        if not os.environ.get("GITHUB_OUTPUT"):
            print(
                "error: --format github needs the GITHUB_OUTPUT environment variable, "
                "which GitHub Actions sets for each step",
                file=sys.stderr,
            )
            return EXIT_RESOLUTION_ERROR
        github_output = Path(os.environ["GITHUB_OUTPUT"])
    step_summary = None
    if summary:
        if not os.environ.get("GITHUB_STEP_SUMMARY"):
            print(
                "error: --summary needs the GITHUB_STEP_SUMMARY environment "
                "variable, which GitHub Actions sets for each step",
                file=sys.stderr,
            )
            return EXIT_RESOLUTION_ERROR
        step_summary = Path(os.environ["GITHUB_STEP_SUMMARY"])
    output = Output(resolved, github_output, step_summary)
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

    Reads the setuptools-scm or Hatch-VCS settings from `pyproject.toml`, or the
    settings in `calver-scm.toml` if there are none, and asks setuptools-scm, so
    the result includes your `local_scheme` and any `CALVER_SCM_*` overrides.

    Parameters
    ----------
    root
        Project directory containing `pyproject.toml` or `calver-scm.toml`.
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
calver-scm validate "$GITHUB_REF_NAME" --tag --against-repo   # also check the repo
calver-scm --json validate 2026.13.1
```

**Exit codes:** `0` valid, `1` invalid, `2` bad usage or the project configuration
is unusable, `3` `--against-repo` on a shallow clone."""
)
def validate(
    version: str,
    /,
    *,
    tag: Annotated[
        bool, cyclopts.Parameter(name=("--tag", "-t"), negative="", show_default=False)
    ] = False,
    against_repo: Annotated[
        bool,
        cyclopts.Parameter(name="--against-repo", negative="", show_default=False),
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
    against_repo
        Also compare the tag with the local tags, as next-tag reads them: it
        must not exist yet, be in a past period, skip a patch number or be lower
        than an existing release. A tag pointing at HEAD is the one being built,
        so it does not count as existing. Needs `--tag` and a full clone.
    root
        Project directory whose `pyproject.toml` or `calver-scm.toml` holds the
        settings.
    """
    if against_repo and not tag:
        print("error: --against-repo needs --tag", file=sys.stderr)
        return EXIT_RESOLUTION_ERROR
    try:
        config = _load_calver_config(root.resolve())
        result = validate_version(version, config, is_tag=tag)
        if against_repo and result.valid:
            _require_full_history(root)
            result = validate_against_repo(
                result,
                config,
                list_local_tags(root),
                head_tags=list_head_tags(root),
                today=_today_in_timezone(config.timezone),
            )
    except (RuntimeError, ResolutionError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_RESOLUTION_ERROR
    except NextTagError as e:
        print(f"error: {e.message} [{e.code}]", file=sys.stderr)
        return EXIT_TAG_UNAVAILABLE
    output.validation(result)
    return EXIT_OK if result.valid else EXIT_INVALID


def _validate_each(
    values: list[str], root: Path, *, tag: bool
) -> tuple[CalverConfig, list[ValidationResult]]:
    """Validate every input against the project's scheme; no I/O beyond the settings."""
    config = _load_calver_config(root.resolve())
    return config, [validate_version(value, config, is_tag=tag) for value in values]


def _skipped_note(count: int, *, stable: bool) -> str:
    """Say what `sort --skip-other-stability` left out, and why."""
    noun = "version" if count == 1 else "versions"
    prefix = "a leading" if stable else "no"
    return (
        f"note: skipped {count} {noun} with {prefix} '0.' prefix, which does not "
        f"fit stable = {str(stable).lower()}"
    )


_ORDER_EPILOGUE = """\
Versions are ordered as PEP 440 orders them, so `2026.4.3.dev1` < `2026.4.3rc1` <
`2026.4.3` < `2026.4.3.post1`, and `2026.4.9` < `2026.4.10`. Each input is checked
against the project's scheme first, as `validate` does, and the first invalid one
prints its findings and exits `1`."""


@app.command(
    help_epilogue=f"""\
**Examples**

```
calver-scm compare 2026.4.2 2026.4.3        # less
calver-scm compare v2026.4.10 v2026.4.9 -t  # greater, for tags
calver-scm --json compare 2026.4.3rc1 2026.4.3
```

{_ORDER_EPILOGUE}

**Exit codes:** `0` compared, `1` an input is invalid, `2` bad usage or the project
configuration is unusable."""
)
def compare(
    a: str,
    b: str,
    /,
    *,
    tag: Annotated[
        bool, cyclopts.Parameter(name=("--tag", "-t"), negative="", show_default=False)
    ] = False,
    root: RootOption = Path(),
    output: OutputParameter,
) -> int:
    """Say whether one version is older than, equal to or newer than another.

    Prints `less` when A is older than B, `equal`, or `greater`.

    Parameters
    ----------
    a
        The first version, or Git tag when `--tag` is given.
    b
        The second version, or Git tag when `--tag` is given.
    tag
        Treat both inputs as Git tags that include the configured tag prefix.
    root
        Project directory whose `pyproject.toml` or `calver-scm.toml` holds the
        settings.
    """
    try:
        _, results = _validate_each([a, b], root, tag=tag)
    except (RuntimeError, ResolutionError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_RESOLUTION_ERROR
    invalid = next((r for r in results if not r.valid), None)
    if invalid is not None:
        output.validation(invalid)
        return EXIT_INVALID
    first, second = (version_order_key(r) for r in results)
    order = "less" if first < second else "greater" if first > second else "equal"
    output.compared(a, b, order)
    return EXIT_OK


@app.command(
    help_epilogue=f"""\
**Examples**

```
calver-scm sort 2026.4.10 2026.4.2 2026.4.3rc1
git tag | calver-scm sort --tag --reverse | head -1   # the newest tag
git tag | calver-scm sort --tag -R --skip-other-stability | head -1
calver-scm --json sort 2026.4.3 2026.4.2
```

With no versions on the command line they are read from standard input, one per
line, and blank lines are skipped. Each is printed as it was written, so tags keep
their prefix.

After a project changes `stable`, its older tags carry (or lack) the `0.` prefix the
new setting rejects. `--skip-other-stability` leaves those out, as `tags` and
`next-tag` do, and says how many on stderr. Anything else invalid still fails.
Older tags always order below newer stable ones, so skipping them never changes
which tag is newest.

{_ORDER_EPILOGUE}

**Exit codes:** `0` sorted, `1` an input is invalid, `2` bad usage, no versions
given or the project configuration is unusable."""
)
def sort(
    *versions: str,
    tag: Annotated[
        bool, cyclopts.Parameter(name=("--tag", "-t"), negative="", show_default=False)
    ] = False,
    reverse: Annotated[
        bool,
        cyclopts.Parameter(name=("--reverse", "-R"), negative="", show_default=False),
    ] = False,
    skip_other_stability: Annotated[
        bool,
        cyclopts.Parameter(
            name="--skip-other-stability", negative="", show_default=False
        ),
    ] = False,
    root: RootOption = Path(),
    output: OutputParameter,
) -> int:
    """Put versions or Git tags in order, oldest first.

    Parameters
    ----------
    versions
        The versions or tags to sort. Read from standard input when none are given.
    tag
        Treat the inputs as Git tags that include the configured tag prefix.
    reverse
        Newest first.
    skip_other_stability
        Leave out versions whose only problem is a `0.` prefix that disagrees with
        the `stable` setting, such as the tags from before the project went stable.
    root
        Project directory whose `pyproject.toml` or `calver-scm.toml` holds the
        settings.
    """
    values = list(versions) or [
        line.strip() for line in sys.stdin.read().splitlines() if line.strip()
    ]
    if not values:
        print("error: no versions to sort", file=sys.stderr)
        return EXIT_RESOLUTION_ERROR
    try:
        config, results = _validate_each(values, root, tag=tag)
    except (RuntimeError, ResolutionError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_RESOLUTION_ERROR
    if skip_other_stability:
        skipped = [r for r in results if is_other_stability(r)]
        results = [r for r in results if not is_other_stability(r)]
        if skipped:
            print(_skipped_note(len(skipped), stable=config.stable), file=sys.stderr)
        if not results:
            print("error: no versions left to sort", file=sys.stderr)
            return EXIT_RESOLUTION_ERROR
    invalid = next((r for r in results if not r.valid), None)
    if invalid is not None:
        output.validation(invalid)
        return EXIT_INVALID
    ordered = sorted(results, key=version_order_key, reverse=reverse)
    output.sorted_versions([r.input for r in ordered])
    return EXIT_OK


@app.command(
    help_epilogue="""\
**Examples**

```
calver-scm parse v2026.4.2 --tag
calver-scm --json parse v0.2026.11.0.post1 --tag
calver-scm --format github parse "$GITHUB_REF_NAME" --tag
calver-scm --json parse "$GITHUB_REF_NAME" --tag --against-repo   # newest per scope
```

Plain output has one tab-separated line per part: kind, version, period, one
`date.<token>` line per date component, patch, pre, post, dev, stable and
tag_prefix. A part the version lacks is empty. With `--against-repo`, one
`newest.<scope>` line follows for each scope.

**Exit codes:** `0` parsed, `1` invalid, `2` bad usage or the project configuration
is unusable, `3` `--against-repo` on a shallow clone."""
)
def parse(
    version: str,
    /,
    *,
    tag: Annotated[
        bool, cyclopts.Parameter(name=("--tag", "-t"), negative="", show_default=False)
    ] = False,
    against_repo: Annotated[
        bool,
        cyclopts.Parameter(name="--against-repo", negative="", show_default=False),
    ] = False,
    root: RootOption = Path(),
    output: OutputParameter,
) -> int:
    """Split a version or Git tag into its parts under the project's scheme.

    Applies the same checks as `validate`, then reports what the version is made
    of, so a script need not re-parse a tag against the scheme. An invalid input
    prints the same findings as `validate` and exits 1. Needs no Git checkout.

    Parameters
    ----------
    version
        The version to read, or the full Git tag when `--tag` is given.
    tag
        Treat the input as a Git tag that includes the configured tag prefix.
    against_repo
        Also report, under `newest`, whether the tag is the newest release in
        its period, in each shorter date prefix and overall (`all`). Only
        finals and post-releases count, ordered by PEP 440, so a project can
        avoid moving a tag such as `latest` backwards. JSON and plain output
        only; GitHub output omits it. Needs `--tag` and a full clone.
    root
        Project directory whose `pyproject.toml` or `calver-scm.toml` holds the
        settings.
    """
    if against_repo and not tag:
        print("error: --against-repo needs --tag", file=sys.stderr)
        return EXIT_RESOLUTION_ERROR
    try:
        config = _load_calver_config(root.resolve())
        result = validate_version(version, config, is_tag=tag)
        if against_repo and result.valid:
            _require_full_history(root)
            result = newest_in_scopes(result, config, list_local_tags(root))
    except (RuntimeError, ResolutionError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_RESOLUTION_ERROR
    except NextTagError as e:
        print(f"error: {e.message} [{e.code}]", file=sys.stderr)
        return EXIT_TAG_UNAVAILABLE
    output.parsed(result)
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
        Project directory containing `pyproject.toml` or `calver-scm.toml`.
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
calver-scm doctor --strict             # fail the build on warnings too
```

**Severities:** `ok`; `info` (for your awareness); `warning` (may give a surprising
version); `error` (resolution is broken).

**Exit codes:** `0` no errors (warnings are allowed unless `--strict`), `1` errors
were found, or warnings with `--strict`."""
)
def doctor(
    *,
    root: RootOption = Path(),
    strict: Annotated[bool, cyclopts.Parameter(negative="")] = False,
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
        Project directory containing `pyproject.toml` or `calver-scm.toml`.
    strict
        Exit `1` on warnings as well as errors. The report is unchanged.
    """
    report = diagnose(root)
    output.report(report)
    failing = (Severity.WARNING, Severity.ERROR) if strict else (Severity.ERROR,)
    return EXIT_INVALID if report.status in failing else EXIT_OK


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
        Project directory containing `pyproject.toml` or `calver-scm.toml`.
    """
    if sum((pre is not None, promote, post)) > 1:
        print("error: --pre, --promote and --post cannot be combined", file=sys.stderr)
        return EXIT_RESOLUTION_ERROR
    try:
        config = _load_calver_config(root.resolve())
        _require_full_history(root)
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


def _require_full_history(root: Path) -> None:
    """Refuse a shallow clone, whose tag list cannot be trusted."""
    if is_shallow_repository(root):
        raise NextTagError(
            "shallow_checkout",
            "this is a shallow clone, so existing tags cannot be trusted; "
            "run 'git fetch --unshallow --tags'",
        )


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


@app.command(
    help_epilogue=f"""\
**Examples**

```
calver-scm tags
calver-scm --json tags
calver-scm tags | grep ignored   # tags next-tag does not count, and why
```

**Kinds**

{_kinds()}

Plain output has one tab-separated line per tag: tag, kind, period, patch and, for
an ignored tag, the reason."""
)
def tags(
    *,
    root: RootOption = Path(),
    output: OutputParameter,
) -> int:
    """List the local tags and how each one reads under the scheme.

    The companion to `next-tag`: it shows which tags are counted when numbering,
    and why the others are not. Read-only. Understood tags come first, oldest
    period first, then the ignored ones by name.

    Parameters
    ----------
    root
        Project directory containing `pyproject.toml` or `calver-scm.toml`.
    """
    try:
        config = _load_calver_config(root.resolve())
        local_tags = list_local_tags(root)
        if is_shallow_repository(root):
            print(
                "warning: this is a shallow clone, so some tags may be missing",
                file=sys.stderr,
            )
    except (RuntimeError, ResolutionError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_RESOLUTION_ERROR
    output.tags(classify_tags(local_tags, config))
    return EXIT_OK


# Commands whose results are not flat enough to become step outputs.
_NO_GITHUB_OUTPUT = (explain, doctor, tags, sort)

# Contributing to calver-scm

Thanks for your interest in improving `calver-scm`.

## Ways to contribute

- Report bugs and edge cases
- Propose and discuss enhancements
- Improve documentation and examples
- Submit pull requests

## Development setup

1. Fork and clone the repository.
2. Create a branch from `main` for your change.
3. Install development dependencies and git hooks:

```bash
uv sync --group dev   # includes the `cli` group (Cyclopts)
uv run poe init       # installs the git hooks
```

`poe init` installs a pre-commit hook (formatting and lint checks) and a pre-push
hook that runs only the fast `unit` tests (`poe test-fast`); CI runs everything. Hooks are run by [prek](https://github.com/j178/prek), a
drop-in replacement for `pre-commit` that reads the same `.pre-commit-config.yaml`.
`poe init` also replaces any shim left by an earlier `pre-commit install`.

The pre-push hook tests the checked-out tree, not every branch in a stack; CI
remains the per-branch check.

## Run checks locally

Before opening a pull request, run:

```bash
uv run prek run --all-files
uv run poe check
```

`poe check` runs what CI runs: `ruff format --check`, `ruff check`, `mypy` and
`pytest`. Run `uv run poe` to list every task. For quicker iteration while coding:

```bash
uv run poe fix          # ruff format and ruff check --fix
uv run poe test         # pytest only
uv run poe build-check  # build the wheel and sdist and test them
```

The [autofix.ci](https://autofix.ci) app also runs the hooks on every pull request
and commits any fixes they make (trailing whitespace, JSON formatting and so on)
to the branch, so run `git pull --rebase` before pushing again. Dependency and
hook updates come from Renovate.

## Architecture

Version calculation is separated from setuptools-scm so it can be tested and
reused without a repository, a clock or the filesystem.

| Module | Role |
| --- | --- |
| [`scheme.py`](src/calver_scm/scheme.py) | The `calver_scm(version)` entry point registered with setuptools-scm. A thin adapter: finds the project root, loads the config, reads today's date and converts `ScmVersion` into an `ScmContext`. |
| [`engine.py`](src/calver_scm/engine.py) | `resolve_version(scm, config, *, today)`: the pure algorithm. No I/O, no clock, no setuptools-scm. |
| [`models.py`](src/calver_scm/models.py) | Frozen dataclasses: `ScmContext` (input), `VersionResolution` (output) and `ResolutionReason` (which branch ran). |
| [`cli.py`](src/calver_scm/cli.py), [`cli_app.py`](src/calver_scm/cli_app.py), [`cli_support.py`](src/calver_scm/cli_support.py), [`cli_output.py`](src/calver_scm/cli_output.py) | The optional `calver-scm` command. `cli.py` is the console-script entry point and imports Cyclopts lazily, so it works (with an install hint) without the `cli` extra. `cli_app.py` defines the Cyclopts commands and is the only module importing Cyclopts. A meta-app launcher there parses the global `--format`/`--json` options and injects an `Output` into each command, so commands never format results themselves. `cli_output.py` holds `Output`: every result is one payload dictionary, printed as is for JSON and rendered from by the plain and rich views, so the formats cannot disagree. `cli_rich.py` holds the rich renderers (panels and tables) and is the only place that styles output; plain is a stable contract for scripts, so do not decorate it. `cli_support.py` reproduces the build backend's setuptools-scm settings from `pyproject.toml` (setuptools and Hatch-VCS) and calls the public `get_version`; `explain` wraps the scheme callback to capture the engine's result, so the explanation comes from the real calculation. |
| [`config.py`](src/calver_scm/config.py) | `CalverConfig`, config loading and `CALVER_SCM_*` overrides. Loading happens in the adapter, never in the engine. |
| [`release.py`](src/calver_scm/release.py) | `plan_next_tag(tags, config, *, today)`: pure next-release-tag planning behind `calver-scm next-tag`. It takes the tag list as input; listing tags and checking for a shallow clone happen in `cli_support.py`. |
| [`diagnostics.py`](src/calver_scm/diagnostics.py) | `diagnose(root)`: the independent checks behind `calver-scm doctor`, each returning a `Diagnostic`. |
| [`validation.py`](src/calver_scm/validation.py) | `validate_version(text, config, *, is_tag)`: pure PEP 440 and CalVer policy checks behind `calver-scm validate`. Reuses `CalverVersion`; no second parser. |
| [`parser.py`](src/calver_scm/parser.py), [`utils.py`](src/calver_scm/utils.py), [`calver_version.py`](src/calver_scm/calver_version.py) | Tag parsing, date and formatting helpers, and the PEP 440 `CalverVersion`. |

Things worth knowing when changing this code:

- `VersionResolution.public_version` is the version scheme output only.
  setuptools-scm applies the `local_scheme` afterwards, so the final build
  version can carry a suffix such as `+g1a2b3c4.d20260415`.
- With setuptools-scm 10, `ScmVersion.distance` is always an `int` and `tag` is
  already prefix-stripped and normalised. A repository with no tags reaches the
  scheme as tag `0.0`, so it takes the incompatible-tag fallback rather than the
  no-tag one.
- A parseable tag without usable release components falls back even when it is
  exact and clean. Dirty at distance 0 takes the dev path.
- Do not import `setuptools_scm` in the engine, models or parser. `scheme.py` may
  import it only under `TYPE_CHECKING`; only `cli_support.py` calls it at runtime.
  `tests/test_import_boundary.py` enforces this.
- Do not import Cyclopts outside `cli_app.py` and the lazy import in `cli.py`.
- A new `ResolutionReason` or `NextTagReason` needs a label and a description (the enum owns its wording), and a row in the README table. The `--help` text is generated from the enums, and a test fails if the README misses a reason. The same applies to a new `validate` error code (`IssueCode`) or `doctor` check (`CheckCode`).
- New commands take an injected `output: OutputParameter` and add a rendering
  method to `Output` covering rich, plain and JSON; do not `print` results directly.
  Errors go to stderr as plain text.
- `tests/test_cli_parity.py` compares `calver-scm version` with what real setuptools
  and Hatchling builds report. Keep it passing when changing `cli_support.py`.

## Coding guidelines

- Target Python 3.11+.
- Keep changes focused and easy to review.
- Add or update tests for behaviour changes.
- Keep types strict and avoid introducing unnecessary `Any`.
- Follow the existing style and naming conventions.

## Tests

- Place tests in [`tests/`](tests/).
- Keep unit tests fast and deterministic.
- Test the engine directly with `ScmContext`, `CalverConfig` and a fixed `today`;
  no patching is needed.
- For adapter and end-to-end tests, freeze the clock with the `set_today`
  fixture (backed by `time-machine`) instead of monkeypatching.
- [`tests/test_scheme_characterisation.py`](tests/test_scheme_characterisation.py)
  is a golden table of every decision branch. If it changes, output changed.
- Add end-to-end coverage for version parsing/scheme behaviour changes.
- Every test needs exactly one scope marker, `unit` (fast) or `e2e`. Tests in
  `tests/test_cli*.py` also get the `cli` marker automatically, so `pytest -m cli`
  and `pytest -m "not cli"` select them.
- Do not reduce coverage.

## Pull requests

- Use clear commit messages that describe intent.
- Include a short explanation of what changed and why.
- Link related issues where relevant.
- Ensure all checks are green before requesting review.

## Reporting bugs

When opening a bug report, include:

- Installed `calver-scm` version
- Python version and operating system
- Relevant [`pyproject.toml`](pyproject.toml) configuration
- Expected vs actual version output
- Minimal steps to reproduce

## Policies

By participating in this project, you agree to follow:

- [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)
- [`SECURITY.md`](SECURITY.md) for private vulnerability reporting

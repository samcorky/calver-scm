<div align="center">

# calver-scm

**Automatic, date-based versioning for Python projects, powered by your Git history.**

[![PyPI version][pypi-version-badge]][pypi-link]
[![PyPI downloads][pypi-downloads-badge]][pypi-link]
[![Python versions][python-badge]][pypi-link]
[![License: MIT][license-badge]][license-link]
[![Tests][tests-badge]][tests-link]
[![Coverage][coverage-badge]][coverage-link]
[![Lint][lint-badge]][lint-link]
[![Format][format-badge]][format-link]
[![Ruff][ruff-badge]][ruff-link]
[![uv][uv-badge]][uv-link]
[![mypy][mypy-badge]][mypy-link]

</div>

---

`calver-scm` is a [setuptools-scm](https://github.com/pypa/setuptools_scm) plugin that generates [CalVer](https://calver.org) version strings directly from your Git tags and commit history. No `__version__` files to maintain, no manual bumping; just tag and go.

Versions look like this:

```
2026.4.0          -> clean tag, April 2026, patch 0
2026.4.1.dev3     -> 3 commits after that tag, still April, patch incremented
2026.5.0.dev3     -> 3 commits after an old tag, month rolled over, patch reset
2026.4.15.0       -> day mode: clean tag on the 15th
2026.4.15.1.dev2  -> day mode: 2 commits after a tag on the same day
2026.4.0.dev12    -> no tag yet, 12 commits in
0.2026.4.0        -> same release line, but marked unstable/pre-1.0
```

---

## Contents

- [Installation](#installation)
- [How versions are generated](#how-versions-are-generated)
- [Pre-release, post-release, and local tags](#pre-release-post-release-and-local-tags)
- [Configuration](#configuration)
- [Environment variable overrides](#environment-variable-overrides)
- [Local scheme](#local-scheme)
- [Command line](#command-line)
- [Requirements](#requirements)
- [Contributing](#contributing)
- [Security](#security)

## Installation

```bash
pip install calver-scm
```

Then wire it into your `pyproject.toml`. Pick the setup that matches your build backend:

### Quickstart (hatch-vcs, recommended)

If you use Hatchling, this is the shortest working setup:

```toml
[build-system]
requires = ["hatchling", "hatch-vcs", "calver-scm"]
build-backend = "hatchling.build"

[project]
dynamic = ["version"]

[tool.hatch.version]
source = "vcs"

[tool.hatch.version.raw-options]
version_scheme = "calver-scm"
local_scheme   = "dirty-tag"
```

`dynamic = ["version"]` is required so Hatch knows the version is resolved from VCS at build time.

### With setuptools

```toml
[build-system]
requires = ["setuptools", "setuptools-scm", "calver-scm"]
build-backend = "setuptools.build_meta"

[project]
dynamic = ["version"]

[tool.setuptools_scm]
version_scheme = "calver-scm"
local_scheme   = "dirty-tag"
```

`dynamic = ["version"]` is required when using PEP 621 metadata in `pyproject.toml`.

### hatch-vcs extras (optional)

The quickstart config above is enough for most projects. If you want a runtime
`__version__` file, hatch-vcs can write one during builds:


```toml
[tool.hatch.build.hooks.vcs]
version-file = "src/your_package/_version.py"
```

Then in your `__init__.py`:

```python
from ._version import __version__
```

That's it. Your project will now version itself automatically on every build.

### CI note

This plugin derives versions from Git history and tags. In CI, make sure your
checkout includes tags and enough history to resolve the latest version tag.

---

## How versions are generated

The generated version shape is config-driven. In general, it looks like:

```
[0.]<DATE_BASE>.PATCH[.devN][+local]
```

- `<DATE_BASE>` comes from `mode`/`scheme` (for example `YYYY`, `YYYY.MM`,
  `YYYY.WW`, or `YYYY.MM.DD`).
- `0.` is included only when `stable = false`.
- `.devN` appears for non-tag builds (and in no-tag fallback when
  `fallback = "dev"`).
- `+local` (including `+dirty`) depends on your setuptools-scm `local_scheme`.

If `stable = false`, `calver-scm` prefixes the generated public version with
`0.` to indicate an explicitly unstable release line:

```
2026.4.0      -> stable output (default)
0.2026.4.0    -> unstable output
0.2026.4.1.dev3
```

| Situation                               | Example           |
|-----------------------------------------|-------------------|
| Clean tag, month mode                   | `2026.4.0`       |
| Commits after tag, same month           | `2026.4.1.dev3`  |
| Commits after tag, previous month's tag | `2026.5.0.dev3`  |
| Clean tag, day mode                     | `2026.4.15.0`    |
| Dirty working tree                      | `2026.4.0+dirty` |
| No tag yet                              | `2026.4.0.dev12` |

The **patch** segment increments automatically from your last tag within the current period, and resets to `0` whenever the month (or day, in day mode) rolls over.

The date segment is derived from the build/runtime date, not from commit timestamps.

## Pre-release, post-release, and local tags

If your Git tag carries any PEP 440 suffix, `calver-scm` preserves it in the
generated version and normalises it to its
[PEP 440](https://peps.python.org/pep-0440/) canonical form.

### Pre-release suffixes (`a`, `b`, `rc`)

Tag any of the recognised PEP 440 aliases and it is normalised automatically:

| Tag suffix                     | Canonical output |
|--------------------------------|------------------|
| `alpha` / `a`                  | `a`              |
| `beta` / `b`                   | `b`              |
| `preview` / `pre` / `c` / `rc` | `rc`             |

```
v2026.4.0a1     -> 2026.4.0a1
v2026.4.0beta2  -> 2026.4.0b2
v2026.4.0pre1   -> 2026.4.0rc1
v2026.4.0rc1    -> 2026.4.0rc1
```

### Post-release suffixes (`post`)

| Tag suffix             | Canonical output |
|------------------------|------------------|
| `-rN` / `revN`         | `postN`          |
| `post-N` / `postN`     | `postN`          |

```
v2026.4.0-r1     -> 2026.4.0.post1
v2026.4.0.rev2   -> 2026.4.0.post2
v2026.4.0.post-3 -> 2026.4.0.post3
v2026.4.0.post3  -> 2026.4.0.post3
```

### Dev suffixes (`dev`)

| Tag suffix       | Canonical output |
|------------------|------------------|
| `dev` (bare)     | `dev0`           |
| `dev-N` / `devN` | `devN`           |

```
v2026.4.0.dev    -> 2026.4.0.dev0
v2026.4.0.dev-4  -> 2026.4.0.dev4
v2026.4.0.dev4   -> 2026.4.0.dev4
```

### Local version segment (`+`)

A `+local` segment on a tag is preserved as-is. PEP 440 normalises
underscores to dots within local identifiers:

```
v2026.4.0+abc            -> 2026.4.0+abc
v2026.4.0+linux.x86_64   -> 2026.4.0+linux.x86.64
```

> **Note:** The `+local` segment on a *tag* is distinct from the `+dirty`
> suffix that setuptools-scm appends for uncommitted working-tree changes.
> See [Local scheme](#local-scheme) for how to control that behaviour.

### Combining suffixes

All segments can be combined and are each normalised independently:

```
v2026.4.0rc1.post2.dev3+local -> 2026.4.0rc1.post2.dev3+local
```

---

## Configuration

Add a `[tool.calver-scm]` section to `pyproject.toml` to customise behaviour. All fields are optional, and the defaults shown below are sensible for most projects.

```toml
[tool.calver-scm]
mode       = "month"   # "year" | "month" | "week" | "day"
scheme     = "YYYY.MM" # optional token scheme; defaults from mode
patch      = true      # auto-increment patch within a period
stable     = true      # emit normal tags, or prefix versions with 0. when false
no_dev     = false     # suppress .devN suffix on non-exact versions
fallback   = "dev"     # "dev" | "date" (when no tag exists)
tag_prefix = "v"       # prefix stripped when reading tags
timezone   = "UTC"     # "UTC" (default), "local", or IANA tz name
```

If `scheme` is omitted, `calver-scm` uses sensible defaults:

- `mode = "year"` -> `YYYY`
- `mode = "month"` -> `YYYY.MM`
- `mode = "week"` -> `YYYY.WW`
- `mode = "day"` -> `YYYY.MM.DD`

Supported `scheme` tokens follow CalVer terminology: `YYYY`, `YY`, `MM`,
`WW`, `DD`.

> Week tokens (`WW`) cannot be combined with month/day tokens.

### `mode`

Controls the time granularity of the version base.

- `"year"`: base is `YYYY` (e.g. `2026`)
- `"month"`: base is `YYYY.MM` (e.g. `2026.4`)
- `"week"`: base is `YYYY.WW` (e.g. `2026.16`)
- `"day"`: base is `YYYY.MM.DD` (e.g. `2026.4.15`)

```toml
# Year mode: annual cadence
[tool.calver-scm]
mode = "year"
# -> 2026.0, 2026.1.dev3 ...

# Month mode (default): good for most projects
[tool.calver-scm]
mode = "month"
# -> 2026.4.0, 2026.4.1.dev3, 2026.5.0.dev1 ...

# Week mode: weekly cadence
[tool.calver-scm]
mode = "week"
# -> 2026.16.0, 2026.16.1.dev2 ...

# Day mode: useful for projects that release frequently
[tool.calver-scm]
mode = "day"
# -> 2026.4.15.0, 2026.4.15.1.dev2, 2026.4.16.0.dev1 ...
```

### `scheme`

Defines the date portion explicitly using CalVer tokens.

```toml
# Explicitly match the default month style
[tool.calver-scm]
scheme = "YYYY.MM"

# Short year + month
[tool.calver-scm]
scheme = "YY.MM"
# -> 26.4.0, 26.4.1.dev3

# Year + ISO week (week schemes are month/day-exclusive)
[tool.calver-scm]
scheme = "YYYY.WW"
# -> 2026.16.0, 2026.16.1.dev2
```

### `patch`

When `true`, the patch number increments from the last tag within the same period. When `false`, patch is always `0` and only the `.devN` distance distinguishes pre-release builds.

```toml
# patch = true (default): each build within a period gets a unique patch number
[tool.calver-scm]
patch = true
# tag v2026.4.2, then 3 commits later -> 2026.4.3.dev3

# patch = false: patch stays 0, only devN changes
[tool.calver-scm]
patch = false
# tag v2026.4.2, then 3 commits later -> 2026.4.0.dev3
```

### `stable`

Controls whether generated public versions are emitted as stable releases or
explicitly marked as unstable with a leading `0.` prefix.

```toml
# stable = true (default): emit standard CalVer versions
[tool.calver-scm]
stable = true
# tag v2026.4.2, then 3 commits later -> 2026.4.3.dev3

# stable = false: prefix generated output with 0.
[tool.calver-scm]
stable = false
# tag v2026.4.2, then 3 commits later -> 0.2026.4.3.dev3
```

While `stable = false`, both `v0.2026.4.3` and legacy unprefixed tags like
`v2026.4.3` are accepted as parseable historical bases to ease migration.
When you switch to `stable = true`, tags that still carry the unstable `0.`
prefix are treated as incompatible and the version scheme falls back until you
create the first stable tag.

For a go-live cutover, the recommended flow is:

1. develop and pre-release with `stable = false`
2. flip to `stable = true` on the release commit
3. create the first stable tag, for example `v2026.4.0`

That keeps the unstable `0.` tag line distinct from the stable release line and
avoids silently reinterpreting old unstable tags as stable ones.

### `no_dev`

When `true`, suppresses the `.devN` suffix on generated versions, emitting a clean `{base}.{patch}` version even when commits exist after the latest tag or when falling back in an untagged repository.

```toml
# no_dev = false (default): normal development versions with distance suffix
[tool.calver-scm]
no_dev = false
# tag v2026.4.2, then 3 commits later -> 2026.4.3.dev3

# no_dev = true: suppress dev suffix for release workflows
[tool.calver-scm]
no_dev = true
# tag v2026.4.2, then 3 commits later -> 2026.4.3
```

This is especially useful in release CI workflows that compute the clean target release version, create the tag, and publish the release in one pass without requiring a separate bumping step.

> **Note:** `no_dev` only suppresses the public `.devN` version segment. Setuptools-scm's `local_scheme` (such as the default `node-and-date`) can still append a `+g...` local segment on untagged commits. Pair `no_dev = true` / `CALVER_SCM_NO_DEV=true` with a distance-insensitive local scheme like `dirty-tag` or `no-local-version` (or CI overrides like `no-local-version-strict`) to ensure a clean version string.

### `fallback`

Controls what happens when no tag exists yet in the repository.

- `"dev"`: emits `YYYY.MM.0.devN` where N is the total commit count *(default)*
- `"date"`: emits `YYYY.MM.0` with no dev segment, useful for initial releases

```toml
# fallback = "dev" (default): makes it clear this is a pre-release build
[tool.calver-scm]
fallback = "dev"
# 12 commits, no tag yet -> 2026.4.0.dev12

# fallback = "date": emits a clean version even before the first tag
[tool.calver-scm]
fallback = "date"
# 12 commits, no tag yet -> 2026.4.0
```

### `tag_prefix`

The string that must prefix a tag for it to be recognised as a CalVer tag. Set to `""` if your tags have no prefix.

```toml
# tag_prefix = "v" (default): tags like v2026.4.0
[tool.calver-scm]
tag_prefix = "v"

# No prefix: tags like 2026.4.0
[tool.calver-scm]
tag_prefix = ""

# Custom prefix: tags like release-2026.4.0
[tool.calver-scm]
tag_prefix = "release-"
```

### `timezone`

Controls which timezone is used to compute the date segment.

- `"UTC"`: default; deterministic across environments
- `"local"`: machine local timezone
- Any valid IANA timezone, e.g. `"Europe/London"`, `"America/New_York"`

```toml
# Default, recommended for CI/reproducibility
[tool.calver-scm]
timezone = "UTC"

# Use host local timezone
[tool.calver-scm]
timezone = "local"

# Explicit IANA timezone
[tool.calver-scm]
timezone = "Pacific/Auckland"
```

---

## Environment variable overrides

Every option can be overridden at build time without touching `pyproject.toml`, which is handy for CI pipelines.

| Variable                | Equivalent option           |
|-------------------------|-----------------------------|
| `CALVER_SCM_MODE`       | `mode`                      |
| `CALVER_SCM_SCHEME`     | `scheme`                    |
| `CALVER_SCM_PATCH`      | `patch` (`true` / `false`)  |
| `CALVER_SCM_STABLE`     | `stable` (`true` / `false`) |
| `CALVER_SCM_NO_DEV`     | `no_dev` (`true` / `false`) |
| `CALVER_SCM_FALLBACK`   | `fallback`                  |
| `CALVER_SCM_TAG_PREFIX` | `tag_prefix`                |
| `CALVER_SCM_TIMEZONE`   | `timezone`                  |

Environment variables take precedence over `pyproject.toml`.

---

## Local scheme

`calver-scm` controls the **public** version segment only. The `+dirty` suffix is handled separately by setuptools-scm's built-in local schemes. Pick whichever suits you:

```toml
[tool.setuptools_scm]
version_scheme = "calver-scm"
local_scheme   = "dirty-tag"         # +dirty on uncommitted changes (recommended)
# local_scheme = "no-local-version"  # suppress the local segment entirely
# local_scheme = "node-and-date"     # +g1a2b3c4.d20260415 (setuptools-scm default)
```

---

## Command line

An optional command line reports the version your project's build would produce, without building anything.

```bash
pip install 'calver-scm[cli]'
```

```bash
calver-scm version                  # 2026.4.3.dev3+g1a2b3c4
calver-scm version --root ./backend # a project in a subdirectory
calver-scm version --json           # {"version": "2026.4.3.dev3+g1a2b3c4"}
```

`version` reads the project's own `[tool.setuptools_scm]` or Hatch-VCS `[tool.hatch.version]` settings and asks setuptools-scm for the result, so it includes your `local_scheme` and honours `CALVER_SCM_*` overrides. It fails if the project does not use `version_scheme = "calver-scm"`.

```bash
calver-scm validate 2026.4.2                 # valid: 2026.4.2
calver-scm validate v2026.4.2 --tag          # check a Git tag, including its prefix
calver-scm validate "$GITHUB_REF_NAME" --tag --against-repo   # also check it against the repo
calver-scm validate 2026.13.1 --json         # {"valid": false, "input": ..., "errors": [...]}
```

`validate` checks that a version is valid PEP 440 and fits your configured scheme: the number of date components, calendar ranges (month 1-12, real days of the month, week 1-53), the `stable` setting's `0.` prefix and, with `--tag`, the `tag_prefix`. Pre-release, post-release, dev and local suffixes are accepted. It reads `[tool.calver-scm]` (and `CALVER_SCM_*` overrides) from `--root` but needs no Git checkout. Week 53 is accepted in any year because `YYYY.WW` takes its year from the calendar date, not the ISO week-year.

`--against-repo` (with `--tag`) also reads the local tags, as `next-tag` does, so `validate` can say whether the tag makes sense in this repository and not only whether it is well-formed. It judges the tag as a new release among the existing tags, on any branch, and every finding is an error (exit code `1`), because the point is a release CI gate. A tag pointing at HEAD is the one being built, so on a tag-push build it does not count as already existing. Post-releases are only checked for existence and period, since they legitimately follow an older release. Without the flag `validate` is unchanged and needs no checkout. With it, a shallow clone exits `3`, as for `next-tag`, because the tag list cannot be trusted. Rerunning a build for an old release tag fails the later-release checks, as the tag is judged as a new one.

### Explaining a version

```bash
calver-scm explain
```

Shows how the build version was derived: the tag, commit distance and dirty flag that setuptools-scm supplied, the date and timezone used, which branch of the algorithm ran (`exact_tag`, `patch_incremented`, `patch_reset`, `no_tag_fallback` or `incompatible_tag_fallback`), the effective configuration, and any `CALVER_SCM_*` overrides in force. It separates the `public_version` that calver-scm produced from the `local_segment` that your `local_scheme` appended afterwards. It runs the same code path as a real build, and it never prints absolute paths.

`--promote` proposes the final tag for the latest pre-release (in PEP 440 order, across channels) of the release that would otherwise be proposed, so `v2026.4.3rc2` gives `v2026.4.3`. It exits `3` with `no_prerelease` when there is nothing to promote, and with `prerelease_not_ancestor` when that pre-release is not an ancestor of HEAD, because the final tag would then not contain what was tested. If HEAD has moved on since the pre-release, it still succeeds but prints a warning to stderr.

`--post` proposes the next post-release of the latest release in the period, so with `v2026.4.2` released it gives `v2026.4.2.post1`, then `.post2`. It is the one mode that adds to an existing release, so unlike a final tag it works with `patch = false`. It exits `3` with `no_release` when the period has no release. `--pre`, `--promote` and `--post` cannot be combined (exit code `2`).

The `reason` is one of:

| Reason | Meaning |
| --- | --- |
| `no_tag_fallback` | **No tag, fallback.** There is no tag at all, so the configured fallback applies. |
| `incompatible_tag_fallback` | **Incompatible tag, fallback.** The tag does not fit the CalVer scheme (a repository with no tags is reported as 0.0), so the configured fallback applies. |
| `exact_tag` | **Exact tag.** HEAD is exactly on a clean tag, so that tag's version is used as it is. |
| `patch_incremented` | **Patch incremented.** There are commits since a tag from the current period, so the patch moves on by one. |
| `patch_reset` | **Patch reset.** The tag is from an earlier period (or patch is turned off), so the patch starts again at 0. |

### Diagnosing problems

```bash
calver-scm doctor
```

Runs independent checks and carries on past failures: whether the build configuration uses the calver-scm scheme, whether `[tool.calver-scm]` and the environment overrides are valid, whether Git is available, whether the version resolves, and warnings for shallow clones, a missing compatible tag, and `no_dev` combined with a local segment. Each finding has a code, a severity (`ok`, `info`, `warning` or `error`) and, where useful, a suggested fix. Warnings never fail the command; errors do. Error details can include file paths.

### Planning the next release tag

```bash
git tag "$(calver-scm next-tag)"     # prints e.g. v2026.4.3
calver-scm next-tag --date 2026-05-03  # plan for another date: v2026.5.0
calver-scm next-tag --pre rc           # next release candidate: v2026.4.3rc1
calver-scm next-tag --promote          # finalise the candidate: v2026.4.3rc2 -> v2026.4.3
calver-scm next-tag --post             # post-release of the latest: v2026.4.2.post1
```

`next-tag` is read-only: it proposes a tag and never creates or pushes one. It looks at every local tag, not only those reachable from HEAD, so a number used on another branch is not reused. Pre-releases and dev releases occupy no number, post-releases do, and tags that do not fit the scheme are ignored. It honours `tag_prefix`, `stable` and the timezone. With `patch = false` it refuses a second release in the same period. It also refuses a shallow clone, because the tag list cannot be trusted. Tags that exist only on the remote and have not been fetched cannot be seen, so run `git fetch --tags` first.

`--date YYYY-MM-DD` (`-d`) plans for that calendar date instead of today, which is useful for backfilling and for testing. The configured timezone does not apply to it, and anything that is not an ISO date is a usage error (exit code `2`).

`--pre a|b|rc` proposes the next pre-release of the release that would otherwise be proposed, so with `v2026.4.2` released it gives `v2026.4.3rc1`, then `v2026.4.3rc2` once that exists. Numbers start at 1 and are counted per period, patch and channel, so an existing `rc2` does not affect `--pre b`. Dev releases occupy no number. `--pre` follows the same refusals as a final tag, including `patch = false` with the period already released.

The `reason` is one of:

| Reason | Meaning |
| --- | --- |
| `new_period` | **New period.** No release exists in this period yet, so numbering starts at 0. |
| `next_patch` | **Next patch.** A release already exists in this period, so the patch moves on from it. |
| `new_prerelease` | **First pre-release.** No pre-release of this channel exists for the next release yet, so numbering starts at 1. |
| `next_prerelease` | **Next pre-release.** A pre-release of this channel already exists for the next release, so the number moves on from it. |
| `promotion` | **Promotion.** A pre-release exists for the next release, so the final tag promotes it. |
| `new_postrelease` | **First post-release.** The latest release has no post-release yet, so numbering starts at 1. |
| `next_postrelease` | **Next post-release.** The latest release already has a post-release, so the number moves on from it. |

#### How `next-tag` differs from `version`

`calver-scm version` describes the commit you are on; `next-tag` plans a release. They agree in a simple, linear history, so `CALVER_SCM_NO_DEV=true calver-scm version` and `calver-scm next-tag` give the same number there. They are not the same thing:

| Situation | `version` (with `no_dev`) | `next-tag` |
| --- | --- | --- |
| Commits past the latest release, linear history | the next patch, e.g. `2026.11.1` | `v2026.11.1`, the same number |
| HEAD is exactly on a release tag | that tag, `2026.11.0` | the next number, `v2026.11.1` |
| The nearest tag is a pre-release (`rc1`) | moves on from the pre-release's number | ignores pre-releases |
| A later tag exists only on another branch | ignores it (not reachable from HEAD) | counts it, so it never reuses a number |
| Uncommitted changes | adds a local segment such as `+g1a2b3c4.d20261101` | unaffected |
| `patch = false` | always patch `0`, which can repeat a release | refuses a second release in the period |

Use `version` to see what a build will be called, and `next-tag` to decide what to tag.

### Short flags

| Flag | Short | Applies to |
| --- | --- | --- |
| `--root` | `-r` | every command |
| `--tag` | `-t` | `validate` |
| `--against-repo` | none | `validate` |
| `--date` | `-d` | `next-tag` |
| `--pre` | none | `next-tag` |
| `--promote` | none | `next-tag` |
| `--post` | none | `next-tag` |
| `--format` | `-f` | every command |
| `--json` | `-j` | every command |

### Output formats

Pick how results are written with the global `--format` option, before or after the command:

| Format | Output |
| --- | --- |
| `auto` (default) | `rich` when stdout is a terminal, otherwise `plain` |
| `rich` | Coloured, human-friendly output (honours `NO_COLOR`) |
| `plain` | Unstyled text, one value per line, for scripts |
| `json` | A single JSON object; `--json` (`-j`) is shorthand for `--format json` (`-f json`) |

```bash
calver-scm version                    # rich in a terminal
calver-scm version | cat              # plain: 2026.4.3.dev3+g1a2b3c4
calver-scm --format json version
```

Piping or redirecting therefore always gives plain text without needing a flag. Plain is the stable format for scripts: one value per line, or `key: value` lines, with no decoration. Run `calver-scm --help`, or `calver-scm COMMAND --help`, for the options, worked examples and exit codes of each command. `calver-scm --version` prints the installed `calver-scm` release.

### Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success. For `validate`, the input is valid. For `doctor`, no errors (warnings are allowed). |
| `1` | `validate`: the input is invalid. `doctor`: errors were found. |
| `2` | Invalid usage, invalid configuration, or the version could not be resolved. |
| `3` | `validate --against-repo`: a shallow clone. `next-tag`: no safe tag can be proposed (a shallow clone, `patch = false` with the period already released, `--promote` with nothing to promote, or `--post` with no release in the period). |

### Errors and invalid configuration

Errors are always plain text on stderr, whatever the format, and leave stdout empty. If `[tool.calver-scm]`, a `CALVER_SCM_*` variable or `pyproject.toml` itself is invalid, every command stops with `error: Invalid config: …` and exit code 2. `doctor` is the exception: it reports the problem as an error check, carries on with the other checks, and exits 1. The build behaves the same way in spirit: setuptools-scm raises a `RuntimeError` with the same message, so the build fails instead of producing a wrong version.

`validate` is also an exception to "errors go to stderr": an invalid input is its answer, so the verdict goes to stdout, and with `--json` it stays parseable.

### JSON output

`--json` (or `--format json`) prints a single JSON object on one line. A missing value is always `null`, never an omitted key. New keys may be added in a future release, so ignore keys you do not know. The `reason`, `severity`, `status` and error `code` values below are stable identifiers; the wording of messages and summaries is not.

```jsonc
// version
{"version": "2026.4.3.dev3+g1a2b3c4"}

// validate (exit code 1 when "valid" is false)
{"valid": false, "input": "2026.13.1",
 "errors": [{"code": "invalid_month", "message": "Month must be between 1 and 12, got 13"}]}

// next-tag
{"tag": "v2026.4.3", "version": "2026.4.3", "patch": 3,
 "reason": "next_patch", "latest_tag": "v2026.4.2",   // latest_tag is null for a new period
 "is_prerelease": false, "channel": null}             // channel is "a", "b" or "rc" with --pre

// explain
{"version": "2026.4.3.dev3+g1a2b3c4", "public_version": "2026.4.3.dev3",
 "local_segment": "g1a2b3c4",                        // null when the local_scheme adds nothing
 "reason": "patch_incremented",
 "scm": {"tag": "2026.4.2", "distance": 3, "dirty": false},
 "calculation": {"date": "2026-04-15", "timezone": "UTC", "base": "2026.4",
                 "tag_base": "2026.4", "tag_patch": 2, "patch": 3},
 "config": {"mode": "month", "scheme": "YYYY.MM", "patch": true, "stable": true,
            "no_dev": false, "fallback": "dev", "tag_prefix": "v"},
 "env_overrides": {"CALVER_SCM_NO_DEV": "true"}}      // {} when none are set

// doctor
{"status": "warning",                                // ok, warning or error
 "checks": [{"code": "no_compatible_tag", "severity": "warning",
             "summary": "No tag fits the configured CalVer scheme",
             "detail": "The fallback applied; the tag seen was '0.0'.",
             "remediation": "Tag a release, for example v2026.4.0, …"}]}
```

#### `validate` error codes

| Code | Meaning |
| --- | --- |
| `missing_tag_prefix` | With `--tag`, the input does not start with the configured `tag_prefix`. |
| `invalid_pep440` | Not a valid PEP 440 version. |
| `missing_stability_prefix` | `stable = false`, but the release does not start with `0.`. |
| `unexpected_stability_prefix` | `stable = true`, but the release starts with `0.`. |
| `invalid_release_shape` | The wrong number of components for your scheme. |
| `invalid_year`, `invalid_month`, `invalid_week`, `invalid_day` | A date component is outside its calendar range. |
| `tag_exists` | With `--against-repo`, the tag (or the same version spelled differently) already exists and is not the tag at HEAD. |
| `past_period` | With `--against-repo`, the tag belongs to an earlier period than the current one. |
| `skipped_patch` | With `--against-repo`, the patch is beyond the one `next-tag` would use for a final or pre-release tag. |
| `lower_than_existing` | With `--against-repo`, a final tag is lower than an existing final tag. |

#### `doctor` check codes

| Code | Severity | Meaning |
| --- | --- | --- |
| `build_config` | `ok` or `error` | The build is configured with `version_scheme = "calver-scm"` (setuptools or Hatch-VCS). |
| `calver_config` | `ok` or `error` | `[tool.calver-scm]` and the `CALVER_SCM_*` variables are valid. |
| `env_overrides` | `info` | `CALVER_SCM_*` variables are overriding `pyproject.toml`. |
| `git_available` | `ok` or `error` | Git is installed and on `PATH`. |
| `resolution` | `ok` or `error` | The version resolves. Skipped when `build_config` fails. |
| `shallow_checkout` | `warning` | A shallow clone, so tags and commit distance may be missing. |
| `no_compatible_tag` | `warning` | No tag fits the scheme, so the fallback applied. |
| `dirty_tree` | `info` | There are uncommitted changes. |
| `no_dev_local_segment` | `warning` | `no_dev` does not remove the local version segment. |

Without the `cli` extra the `calver-scm` command still exists but only prints how to install it.

---

## Requirements

- Python >= 3.11
- setuptools-scm >= 10.0.5
- For the command line: the `cli` extra (installs [Cyclopts](https://github.com/BrianPugh/cyclopts), which also brings in Rich)

---

## Contributing

```bash
git clone https://github.com/samcorky/calver-scm
cd calver-scm
uv sync --group dev
uv run poe init
uv run poe check
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for full contribution guidance.

Pull requests and issues are welcome!

## Security

Please report vulnerabilities privately via [`SECURITY.md`](SECURITY.md).

---

## License

[MIT][license-link]

[pypi-version-badge]: https://img.shields.io/pypi/v/calver-scm?logo=pypi&logoColor=white
[pypi-downloads-badge]: https://img.shields.io/pypi/dm/calver-scm?logo=pypi&logoColor=white
[python-badge]: https://img.shields.io/pypi/pyversions/calver-scm?logo=python&logoColor=white
[license-badge]: https://img.shields.io/badge/license-MIT-green
[lint-badge]: https://img.shields.io/github/actions/workflow/status/samcorky/calver-scm/lint.yml?branch=main&logo=githubactions&label=lint
[format-badge]: https://img.shields.io/github/actions/workflow/status/samcorky/calver-scm/format.yml?branch=main&logo=githubactions&label=format
[tests-badge]: https://img.shields.io/github/actions/workflow/status/samcorky/calver-scm/tests.yml?branch=main&logo=githubactions&label=tests
[coverage-badge]: https://codecov.io/github/samcorky/calver-scm/graph/badge.svg?token=62AQDRXNIA
[ruff-badge]: https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json
[uv-badge]: https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json
[mypy-badge]: https://img.shields.io/badge/mypy-checked-blue?logo=python&logoColor=white

[pypi-link]: https://pypi.org/project/calver-scm/
[lint-link]: https://github.com/samcorky/calver-scm/actions/workflows/lint.yml
[format-link]: https://github.com/samcorky/calver-scm/actions/workflows/format.yml
[tests-link]: https://github.com/samcorky/calver-scm/actions/workflows/tests.yml
[coverage-link]: https://codecov.io/github/samcorky/calver-scm
[ruff-link]: https://github.com/astral-sh/ruff
[uv-link]: https://github.com/astral-sh/uv
[mypy-link]: https://mypy-lang.org/
[license-link]: LICENSE

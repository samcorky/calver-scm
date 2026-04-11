<div align="center">

# calver-scm

**Automatic, date-based versioning for Python projects — powered by your Git history.**

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
[![pre-commit.ci][precommit-badge]][precommit-link]

</div>

---

`calver-scm` is a [setuptools-scm](https://github.com/pypa/setuptools_scm) plugin that generates [CalVer](https://calver.org) version strings directly from your Git tags and commit history. No `__version__` files to maintain, no manual bumping — just tag and go.

Versions look like this:

```
2026.04.0          ← clean tag, April 2026, patch 0
2026.04.1.dev3     ← 3 commits after that tag, still April, patch incremented
2026.05.0.dev3     ← 3 commits after an old tag, month rolled over, patch reset
2026.04.15.0       ← day mode: clean tag on the 15th
2026.04.15.1.dev2  ← day mode: 2 commits after a tag on the same day
2026.04.0.dev12    ← no tag yet, 12 commits in
```

---

## Contents

- [Installation](#installation)
- [How versions are generated](#how-versions-are-generated)
- [Pre-release, post-release, and local tags](#pre-release-post-release-and-local-tags)
- [Configuration](#configuration)
- [Environment variable overrides](#environment-variable-overrides)
- [Local scheme](#local-scheme)
- [Requirements](#requirements)
- [Contributing](#contributing)

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
version_scheme = "calver_scm"
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
version_scheme = "calver_scm"
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

Every version follows the pattern:

```
YYYY.MM[.DD].PATCH[.devN][+dirty]
```

| Situation                               | Example           |
|-----------------------------------------|-------------------|
| Clean tag, month mode                   | `2026.04.0`       |
| Commits after tag, same month           | `2026.04.1.dev3`  |
| Commits after tag, previous month's tag | `2026.05.0.dev3`  |
| Clean tag, day mode                     | `2026.04.15.0`    |
| Dirty working tree                      | `2026.04.0+dirty` |
| No tag yet                              | `2026.04.0.dev12` |

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
v2026.04.0a1     → 2026.04.0a1
v2026.04.0beta2  → 2026.04.0b2
v2026.04.0pre1   → 2026.04.0rc1
v2026.04.0rc1    → 2026.04.0rc1
```

### Post-release suffixes (`post`)

| Tag suffix             | Canonical output |
|------------------------|------------------|
| `-rN` / `revN`         | `postN`          |
| `post-N` / `postN`     | `postN`          |

```
v2026.04.0-r1     → 2026.04.0.post1
v2026.04.0.rev2   → 2026.04.0.post2
v2026.04.0.post-3 → 2026.04.0.post3
v2026.04.0.post3  → 2026.04.0.post3
```

### Dev suffixes (`dev`)

| Tag suffix      | Canonical output |
|-----------------|------------------|
| `dev` (bare)    | `dev0`           |
| `dev-N` / `devN`| `devN`           |

```
v2026.04.0.dev    → 2026.04.0.dev0
v2026.04.0.dev-4  → 2026.04.0.dev4
v2026.04.0.dev4   → 2026.04.0.dev4
```

### Local version segment (`+`)

A `+local` segment on a tag is preserved as-is. PEP 440 normalises
underscores to dots within local identifiers:

```
v2026.04.0+abc            → 2026.04.0+abc
v2026.04.0+linux.x86_64   → 2026.04.0+linux.x86.64
```

> **Note:** The `+local` segment on a *tag* is distinct from the `+dirty`
> suffix that setuptools-scm appends for uncommitted working-tree changes.
> See [Local scheme](#local-scheme) for how to control that behaviour.

### Combining suffixes

All segments can be combined and are each normalised independently:

```
v2026.04.0rc1.post2.dev3+local → 2026.04.0rc1.post2.dev3+local
```

---

## Configuration

Add a `[tool.calver_scm]` section to `pyproject.toml` to customise behaviour. All fields are optional — the defaults shown below are sensible for most projects.

```toml
[tool.calver_scm]
mode       = "month"   # "year" | "month" | "week" | "day"
scheme     = "YYYY.0M" # optional token scheme; defaults from mode
patch      = true      # auto-increment patch within a period
fallback   = "dev"     # "dev" | "date" — when no tag exists
tag_prefix = "v"       # prefix stripped when reading tags
timezone   = "UTC"     # "UTC" (default), "local", or IANA tz name
```

If `scheme` is omitted, `calver-scm` uses sensible defaults:

- `mode = "year"` -> `YYYY`
- `mode = "month"` -> `YYYY.0M`
- `mode = "week"` -> `YYYY.0W`
- `mode = "day"` -> `YYYY.0M.0D`

Supported `scheme` tokens follow CalVer terminology: `YYYY`, `YY`, `0Y`, `MM`,
`0M`, `WW`, `0W`, `DD`, `0D`.

> Week tokens (`WW`, `0W`) cannot be combined with month/day tokens.

### `mode`

Controls the time granularity of the version base.

- `"year"` — base is `YYYY` (e.g. `2026`)
- `"month"` — base is `YYYY.MM` (e.g. `2026.04`)
- `"week"` — base is `YYYY.WW` (e.g. `2026.16`)
- `"day"` — base is `YYYY.MM.DD` (e.g. `2026.04.15`)

```toml
# Year mode — annual cadence
[tool.calver_scm]
mode = "year"
# -> 2026.0, 2026.1.dev3 …

# Month mode (default) — good for most projects
[tool.calver_scm]
mode = "month"
# → 2026.04.0, 2026.04.1.dev3, 2026.05.0.dev1 …

# Week mode — weekly cadence
[tool.calver_scm]
mode = "week"
# -> 2026.16.0, 2026.16.1.dev2 …

# Day mode — useful for projects that release frequently
[tool.calver_scm]
mode = "day"
# → 2026.04.15.0, 2026.04.15.1.dev2, 2026.04.16.0.dev1 …
```

### `scheme`

Defines the date portion explicitly using CalVer tokens.

```toml
# Explicitly match the default month style
[tool.calver_scm]
scheme = "YYYY.0M"

# Short year + month
[tool.calver_scm]
scheme = "YY.0M"
# -> 26.04.0, 26.04.1.dev3

# Year + ISO week (week schemes are month/day-exclusive)
[tool.calver_scm]
scheme = "YYYY.0W"
# -> 2026.16.0, 2026.16.1.dev2
```

### `patch`

When `true`, the patch number increments from the last tag within the same period. When `false`, patch is always `0` and only the `.devN` distance distinguishes pre-release builds.

```toml
# patch = true (default) — each build within a period gets a unique patch number
[tool.calver_scm]
patch = true
# tag v2026.04.2, then 3 commits later → 2026.04.3.dev3

# patch = false — patch stays 0, only devN changes
[tool.calver_scm]
patch = false
# tag v2026.04.2, then 3 commits later → 2026.04.0.dev3
```

### `fallback`

Controls what happens when no tag exists yet in the repository.

- `"dev"` — emits `YYYY.MM.0.devN` where N is the total commit count *(default)*
- `"date"` — emits `YYYY.MM.0` with no dev segment, useful for initial releases

```toml
# fallback = "dev" (default) — makes it clear this is a pre-release build
[tool.calver_scm]
fallback = "dev"
# 12 commits, no tag yet → 2026.04.0.dev12

# fallback = "date" — emits a clean version even before the first tag
[tool.calver_scm]
fallback = "date"
# 12 commits, no tag yet → 2026.04.0
```

### `tag_prefix`

The string that must prefix a tag for it to be recognised as a CalVer tag. Set to `""` if your tags have no prefix.

```toml
# tag_prefix = "v" (default) — tags like v2026.04.0
[tool.calver_scm]
tag_prefix = "v"

# No prefix — tags like 2026.04.0
[tool.calver_scm]
tag_prefix = ""

# Custom prefix — tags like release-2026.04.0
[tool.calver_scm]
tag_prefix = "release-"
```

### `timezone`

Controls which timezone is used to compute the date segment.

- `"UTC"` — default; deterministic across environments
- `"local"` — machine local timezone
- Any valid IANA timezone, e.g. `"Europe/London"`, `"America/New_York"`

```toml
# Default, recommended for CI/reproducibility
[tool.calver_scm]
timezone = "UTC"

# Use host local timezone
[tool.calver_scm]
timezone = "local"

# Explicit IANA timezone
[tool.calver_scm]
timezone = "Pacific/Auckland"
```

---

## Environment variable overrides

Every option can be overridden at build time without touching `pyproject.toml` — handy for CI pipelines.

| Variable                | Equivalent option          |
|-------------------------|----------------------------|
| `CALVER_SCM_MODE`       | `mode`                     |
| `CALVER_SCM_SCHEME`     | `scheme`                   |
| `CALVER_SCM_PATCH`      | `patch` (`true` / `false`) |
| `CALVER_SCM_FALLBACK`   | `fallback`                 |
| `CALVER_SCM_TAG_PREFIX` | `tag_prefix`               |
| `CALVER_SCM_TIMEZONE`   | `timezone`                 |

Environment variables take precedence over `pyproject.toml`.

> **Migration note:** Environment variable names were renamed from
> `SCM_CALVER_*` to `CALVER_SCM_*`.
>
> - `SCM_CALVER_MODE` -> `CALVER_SCM_MODE`
> - `SCM_CALVER_SCHEME` -> `CALVER_SCM_SCHEME`
> - `SCM_CALVER_PATCH` -> `CALVER_SCM_PATCH`
> - `SCM_CALVER_FALLBACK` -> `CALVER_SCM_FALLBACK`
> - `SCM_CALVER_TAG_PREFIX` -> `CALVER_SCM_TAG_PREFIX`
> - `SCM_CALVER_TIMEZONE` -> `CALVER_SCM_TIMEZONE`

---

## Local scheme

`calver_scm` controls the **public** version segment only. The `+dirty` suffix is handled separately by setuptools-scm's built-in local schemes. Pick whichever suits you:

```toml
[tool.setuptools_scm]
version_scheme = "calver_scm"
local_scheme   = "dirty-tag"         # +dirty on uncommitted changes (recommended)
# local_scheme = "no-local-version"  # suppress the local segment entirely
# local_scheme = "node-and-date"     # +g1a2b3c4.d20260415 (setuptools-scm default)
```

---

## Requirements

- Python ≥ 3.10
- setuptools-scm ≥ 10.0.5
- `tomli` ≥ 2.4.1 on Python < 3.11 (the stdlib `tomllib` is used on 3.11+)

---

## Contributing

```bash
git clone https://github.com/samcorky/calver-scm
cd calver-scm
uv sync --group dev
pre-commit install
pytest
```

Pull requests and issues are welcome!

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
[precommit-badge]: https://results.pre-commit.ci/badge/github/samcorky/calver-scm/main.svg

[pypi-link]: https://pypi.org/project/calver-scm/
[lint-link]: https://github.com/samcorky/calver-scm/actions/workflows/lint.yml
[format-link]: https://github.com/samcorky/calver-scm/actions/workflows/format.yml
[tests-link]: https://github.com/samcorky/calver-scm/actions/workflows/tests.yml
[coverage-link]: https://codecov.io/github/samcorky/calver-scm
[ruff-link]: https://github.com/astral-sh/ruff
[uv-link]: https://github.com/astral-sh/uv
[mypy-link]: https://mypy-lang.org/
[precommit-link]: https://results.pre-commit.ci/latest/github/samcorky/calver-scm/main
[license-link]: https://github.com/samcorky/calver-scm/blob/main/LICENSE

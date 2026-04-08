# calver-scm

**Automatic, date-based versioning for Python projects — powered by your Git history.**

[![PyPI version][pypi-version-badge]][pypi-link]
[![PyPI downloads][pypi-downloads-badge]][pypi-link]
[![Python versions][python-badge]][pypi-link]
[![License: MIT][license-badge]](LICENSE)
[![CI][ci-badge]][ci-link]
[![Ruff][ruff-badge]][ruff-link]
[![uv][uv-badge]][uv-link]
[![mypy][mypy-badge]][mypy-link]
[![pre-commit][precommit-badge]][precommit-link]

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

## Installation

```bash
pip install calver-scm
```

Then wire it into your `pyproject.toml`. Pick the setup that matches your build backend:

### With setuptools

```toml
[build-system]
requires = ["setuptools", "setuptools-scm", "calver-scm"]
build-backend = "setuptools.build_meta"

[tool.setuptools_scm]
version_scheme = "calver_scm"
local_scheme   = "dirty-tag"
```

### With hatch-vcs (recommended)

[hatch-vcs](https://github.com/ofek/hatch-vcs) is a Hatchling plugin that delegates versioning to setuptools-scm under the hood. It's a great pairing with `calver-scm` — Hatchling handles your build, hatch-vcs reads the Git tags, and `calver-scm` turns them into CalVer strings.

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

The `raw-options` table passes arguments directly through hatch-vcs to setuptools-scm, so `calver_scm` is picked up exactly as if you had configured it directly.

Optionally, you can have hatch-vcs write the resolved version to a `_version.py` file at build time — handy if you want `your_package.__version__` to be available at runtime:

```toml
[tool.hatch.build.hooks.vcs]
version-file = "src/your_package/_version.py"
```

Then in your `__init__.py`:

```python
from ._version import __version__
```

That's it. Your project will now version itself automatically on every build.

---

## How versions are generated

Every version follows the pattern:

```
YYYY.MM[.DD].PATCH[.devN][+dirty]
```

| Situation | Example |
|---|---|
| Clean tag, month mode | `2026.04.0` |
| Commits after tag, same month | `2026.04.1.dev3` |
| Commits after tag, previous month's tag | `2026.05.0.dev3` |
| Clean tag, day mode | `2026.04.15.0` |
| Dirty working tree | `2026.04.0+dirty` |
| No tag yet | `2026.04.0.dev12` |

The **patch** segment increments automatically from your last tag within the current period, and resets to `0` whenever the month (or day, in day mode) rolls over.

---

## Configuration

Add a `[tool.calver_scm]` section to `pyproject.toml` to customise behaviour. All fields are optional — the defaults shown below are sensible for most projects.

```toml
[tool.calver_scm]
mode       = "month"   # "month" | "day"
patch      = true      # auto-increment patch within a period
fallback   = "dev"     # "dev" | "date" — when no tag exists
tag_prefix = "v"       # prefix stripped when reading tags
```

### `mode`

Controls the time granularity of the version base.

- `"month"` — base is `YYYY.MM` (e.g. `2026.04`)
- `"day"` — base is `YYYY.MM.DD` (e.g. `2026.04.15`)

```toml
# Month mode (default) — good for most projects
[tool.calver_scm]
mode = "month"
# → 2026.04.0, 2026.04.1.dev3, 2026.05.0.dev1 …

# Day mode — useful for projects that release frequently
[tool.calver_scm]
mode = "day"
# → 2026.04.15.0, 2026.04.15.1.dev2, 2026.04.16.0.dev1 …
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

---

## Environment variable overrides

Every option can be overridden at build time without touching `pyproject.toml` — handy for CI pipelines.

| Variable | Equivalent option |
|---|---|
| `SCM_CALVER_MODE` | `mode` |
| `SCM_CALVER_PATCH` | `patch` (`true` / `false`) |
| `SCM_CALVER_FALLBACK` | `fallback` |
| `SCM_CALVER_TAG_PREFIX` | `tag_prefix` |

Environment variables take precedence over `pyproject.toml`.

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
- setuptools-scm ≥ 9.2.2
- `tomli` ≥ 2.0.0 on Python 3.10 (the stdlib `tomllib` is used on 3.11+)

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

[MIT](LICENSE)

<!-- Badge references -->
[pypi-version-badge]: https://img.shields.io/pypi/v/calver-scm?logo=pypi&logoColor=white
[pypi-downloads-badge]: https://img.shields.io/pypi/dm/calver-scm?logo=pypi&logoColor=white
[python-badge]: https://img.shields.io/pypi/pyversions/calver-scm?logo=python&logoColor=white
[license-badge]: https://img.shields.io/badge/license-MIT-green
[ci-badge]: https://img.shields.io/github/actions/workflow/status/samcorky/calver-scm/tests.yml?logo=github&label=CI
[ruff-badge]: https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json
[uv-badge]: https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json
[mypy-badge]: https://img.shields.io/badge/mypy-checked-blue?logo=python&logoColor=white
[precommit-badge]: https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit

[pypi-link]: https://pypi.org/project/calver-scm/
[ci-link]: https://github.com/samcorky/calver-scm/actions/workflows/publish.yml
[ruff-link]: https://github.com/astral-sh/ruff
[uv-link]: https://github.com/astral-sh/uv
[mypy-link]: https://mypy-lang.org/
[precommit-link]: https://pre-commit.com/

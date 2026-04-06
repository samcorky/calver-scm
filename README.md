# scm-calver-config

A configurable [CalVer](https://calver.org) versioning plugin for [setuptools-scm](https://github.com/pypa/setuptools_scm).

Generates version strings like `2026.04.3.dev7` automatically from your Git history — no manual version bumping required.

## Installation

```toml
# pyproject.toml
[build-system]
requires = ["hatchling", "setuptools-scm", "scm-calver-config"]
build-backend = "hatchling.build"

[tool.setuptools_scm]
version_scheme = "calver_scm"
local_scheme   = "dirty-tag"   # built-in; use "no-local-version" to suppress
```

## Version format

Versions follow the pattern `YYYY.MM[.DD].PATCH[.devN][+dirty]`.

| Situation | Example |
|---|---|
| Clean tag, month mode | `2026.04.0` |
| Commits after tag, same month | `2026.04.1.dev3` |
| Commits after tag, new month | `2026.05.0.dev3` |
| Clean tag, day mode | `2026.04.15.0` |
| Dirty working tree | `2026.04.0+dirty` |
| No tag yet | `2026.04.0.dev12` |

The patch segment auto-increments within a period and resets when the month (or day) rolls over.

## Configuration

Add a `[tool.calver_scm]` section to `pyproject.toml`:

```toml
[tool.calver_scm]
mode       = "month"   # "month" | "day"  — period granularity
patch      = true      # true | false     — auto-increment patch within a period
fallback   = "dev"     # "dev" | "date"   — behaviour when no tag exists
tag_prefix = "v"       # string           — prefix stripped when parsing tags
```

All fields are optional; the values above are the defaults.

### Options

**`mode`** — controls the time granularity of the version base.

- `"month"` — base is `YYYY.MM`, e.g. `2026.04`
- `"day"` — base is `YYYY.MM.DD`, e.g. `2026.04.15`

**`patch`** — when `true`, the patch number increments from the last tag within the same period. When `false`, the patch is always `0` and only the `.devN` distance distinguishes pre-release builds.

**`fallback`** — controls what happens when no tag exists in the repository.

- `"dev"` — emits `YYYY.MM.0.devN` where N is the commit count
- `"date"` — emits `YYYY.MM.0` with no dev segment (useful for initial releases)

**`tag_prefix`** — the string that must prefix a tag for it to be recognised. Set to `""` if your tags have no prefix.

### Environment variable overrides

Every option can be overridden at build time without touching `pyproject.toml`:

| Variable | Equivalent field |
|---|---|
| `SCM_CALVER_MODE` | `mode` |
| `SCM_CALVER_PATCH` | `patch` (`true` / `false`) |
| `SCM_CALVER_FALLBACK` | `fallback` |
| `SCM_CALVER_TAG_PREFIX` | `tag_prefix` |

Environment variables take precedence over `pyproject.toml`.

## Local scheme

`calver_scm` only controls the public version string. The `+dirty` suffix is handled separately by setuptools-scm's built-in `dirty-tag` local scheme. Pair it with any built-in local scheme:

```toml
[tool.setuptools_scm]
version_scheme = "calver_scm"
local_scheme   = "dirty-tag"        # +dirty on uncommitted changes (recommended)
# local_scheme = "no-local-version" # suppress the local segment entirely
# local_scheme = "node-and-date"    # +g1a2b3c4.d20260415 (setuptools-scm default)
```

## Requirements

- Python ≥ 3.10
- setuptools-scm ≥ 9.2.2
- `tomli` ≥ 2.0.0 on Python 3.10 (stdlib `tomllib` is used on 3.11+)

## Development

```bash
git clone https://github.com/samcorky/scm-calver-config
cd scm-calver-config
uv sync --group dev
pre-commit install
pytest
```

## License

[MIT](LICENSE)

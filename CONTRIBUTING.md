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
uv sync --group dev
pre-commit install
```

## Run checks locally

Before opening a pull request, run:

```bash
pre-commit run --all-files
uv run pytest
uv run mypy
```

For quicker iteration while coding:

```bash
uv run ruff format
uv run ruff check
```

## Coding guidelines

- Target Python 3.10+.
- Keep changes focused and easy to review.
- Add or update tests for behaviour changes.
- Keep types strict and avoid introducing unnecessary `Any`.
- Follow the existing style and naming conventions.

## Tests

- Place tests in [`tests/`](tests/).
- Keep unit tests fast and deterministic.
- Add end-to-end coverage for version parsing/scheme behaviour changes.
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

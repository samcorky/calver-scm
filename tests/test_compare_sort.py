from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING

import pytest

from calver_scm.cli import main

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.e2e


def run(
    capsys: pytest.CaptureFixture[str], root: Path, *args: str
) -> tuple[int, str, str]:
    code = main([*args, "-r", str(root)])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.mark.parametrize(
    ("a", "b", "order"),
    [
        ("2026.4.2", "2026.4.3", "less"),
        ("2026.4.3", "2026.4.2", "greater"),
        ("2026.4.2", "2026.4.2", "equal"),
        ("2026.4.9", "2026.4.10", "less"),
        ("2026.4.3rc1", "2026.4.3", "less"),
        ("2026.4.3.dev1", "2026.4.3rc1", "less"),
        ("2026.4.3", "2026.4.3.post1", "less"),
        ("2026.4.3rc2", "2026.4.3rc10", "less"),
        ("2026.3.9", "2026.4.0", "less"),
    ],
)
def test_compare_orders_by_pep_440(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], a: str, b: str, order: str
) -> None:
    """Order suffixes and numbers as PEP 440 does, which `sort -V` cannot."""
    code, out, _ = run(capsys, tmp_path, "--format", "plain", "compare", a, b)
    assert (code, out) == (0, f"{order}\n")


def test_compare_json_names_both_sides(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Give a script both inputs and the verdict in one object."""
    code, out, _ = run(capsys, tmp_path, "--json", "compare", "2026.4.2", "2026.4.3")
    assert code == 0
    assert json.loads(out) == {"a": "2026.4.2", "b": "2026.4.3", "order": "less"}


def test_compare_tags_respects_the_prefix(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Strip the tag prefix before ordering, and order the numbers numerically."""
    code, out, _ = run(
        capsys,
        tmp_path,
        "--format",
        "plain",
        "compare",
        "v2026.4.2",
        "v2026.4.10",
        "-t",
    )
    assert (code, out) == (0, "less\n")


@pytest.mark.parametrize(
    ("a", "b", "bad"), [("2026.13.1", "2026.4.2", "2026.13.1"), ("2026.4.2", "x", "x")]
)
def test_compare_reports_an_invalid_input_like_validate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], a: str, b: str, bad: str
) -> None:
    """Stop with the findings for the first bad input, so a script fails loudly."""
    code, out, _ = run(capsys, tmp_path, "--format", "plain", "compare", a, b)
    assert code == 1
    assert out.startswith(f"invalid: {bad}\n")


def test_compare_a_tag_without_the_prefix_is_invalid(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Hold tags to the configured prefix, as validate does."""
    code, out, _ = run(
        capsys, tmp_path, "--format", "plain", "compare", "2026.4.2", "v2026.4.3", "-t"
    )
    assert code == 1
    assert "missing_tag_prefix" in out


def test_sort_orders_versions_ascending(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Sort numerically and through the PEP 440 suffixes."""
    code, out, _ = run(
        capsys,
        tmp_path,
        "--format",
        "plain",
        "sort",
        "2026.4.10",
        "2026.4.2",
        "2026.4.3",
        "2026.4.3rc1",
        "2026.4.3.post1",
        "2026.4.3.dev1",
    )
    assert code == 0
    assert out.splitlines() == [
        "2026.4.2",
        "2026.4.3.dev1",
        "2026.4.3rc1",
        "2026.4.3",
        "2026.4.3.post1",
        "2026.4.10",
    ]


def test_sort_reverse_puts_the_newest_first(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Make 'the latest release' the first line."""
    code, out, _ = run(
        capsys,
        tmp_path,
        "--format",
        "plain",
        "sort",
        "--reverse",
        "2026.4.2",
        "2026.4.10",
        "2026.4.3",
    )
    assert code == 0
    assert out.splitlines() == ["2026.4.10", "2026.4.3", "2026.4.2"]


def test_sort_reads_tags_from_stdin_and_keeps_them_as_written(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Take `git tag` output, skip blank lines and print each tag as written."""
    monkeypatch.setattr(
        "sys.stdin", io.StringIO("v2026.4.10\n\n  v2026.4.2  \nv2026.4.3\n")
    )
    code, out, _ = run(capsys, tmp_path, "--format", "plain", "sort", "-t")
    assert code == 0
    assert out.splitlines() == ["v2026.4.2", "v2026.4.3", "v2026.4.10"]


def test_sort_json_is_a_list_of_versions(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Give a script a single parseable result."""
    code, out, _ = run(capsys, tmp_path, "--json", "sort", "2026.4.3", "2026.4.2")
    assert code == 0
    assert json.loads(out) == {"versions": ["2026.4.2", "2026.4.3"]}


def test_sort_with_an_invalid_input_prints_no_ordering(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fail on the first bad input rather than quietly drop it."""
    code, out, _ = run(
        capsys, tmp_path, "--format", "plain", "sort", "2026.4.2", "2026.13.1"
    )
    assert code == 1
    assert out.startswith("invalid: 2026.13.1\n")


def test_sort_with_nothing_to_sort_is_a_usage_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Say so, instead of printing an empty result a script would take as success."""
    monkeypatch.setattr("sys.stdin", io.StringIO("\n"))
    code, out, err = run(capsys, tmp_path, "--format", "plain", "sort")
    assert (code, out) == (2, "")
    assert "no versions to sort" in err


def test_unstable_projects_order_by_the_same_rules(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Honour `stable = false`: its `0.` prefix is required, then ordering is normal."""
    (tmp_path / "calver-scm.toml").write_text("stable = false\n", encoding="utf-8")
    code, out, _ = run(
        capsys, tmp_path, "--format", "plain", "sort", "0.2026.4.10", "0.2026.4.2"
    )
    assert (code, out.splitlines()) == (0, ["0.2026.4.2", "0.2026.4.10"])
    code, out, _ = run(capsys, tmp_path, "--format", "plain", "sort", "2026.4.2")
    assert code == 1
    assert "missing_stability_prefix" in out


def test_unusable_configuration_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit 2 with the configuration error, as the other commands do."""
    (tmp_path / "calver-scm.toml").write_text("mode = 'fortnight'\n", encoding="utf-8")
    for command in (["compare", "1", "2"], ["sort", "1"]):
        code, out, err = run(capsys, tmp_path, "--format", "plain", *command)
        assert (code, out) == (2, "")
        assert err.startswith("error:")


def test_summaries_are_written_for_both_commands(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Show the ordering on the run page like every other command."""
    summary = tmp_path / "summary"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert run(capsys, tmp_path, "--summary", "compare", "2026.4.2", "2026.4.3")[0] == 0
    assert run(capsys, tmp_path, "--summary", "sort", "2026.4.3", "2026.4.2")[0] == 0
    text = summary.read_text(encoding="utf-8")
    assert "## calver-scm compare" in text
    assert "| `order` | less |" in text
    assert "## calver-scm sort" in text
    assert "| 1 | 2026.4.2 |" in text


def test_rich_output_shows_the_ordering(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Render a readable panel on a terminal."""
    code, out, _ = run(
        capsys, tmp_path, "--format", "rich", "compare", "2026.4.2", "2026.4.3"
    )
    assert code == 0
    assert "2026.4.2" in out
    assert "<" in out
    code, out, _ = run(
        capsys, tmp_path, "--format", "rich", "sort", "2026.4.3", "2026.4.2"
    )
    assert code == 0
    assert out.index("2026.4.2") < out.index("2026.4.3")


@pytest.fixture
def stable_project(tmp_path: Path) -> Path:
    """A project that has crossed from `stable = false` to `stable = true`."""
    (tmp_path / "calver-scm.toml").write_text("stable = true\n", encoding="utf-8")
    return tmp_path


def test_skip_other_stability_drops_legacy_tags_after_going_stable(
    stable_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Order the stable tags and leave the `0.` ones behind, as `tags` does."""
    code, out, err = run(
        capsys,
        stable_project,
        "--format",
        "plain",
        "sort",
        "--tag",
        "--skip-other-stability",
        "v0.2026.11.1",
        "v2026.12.1",
        "v0.2026.10.0",
        "v2026.12.0",
    )
    assert code == 0
    assert out.splitlines() == ["v2026.12.0", "v2026.12.1"]
    assert err == (
        "note: skipped 2 versions with a leading '0.' prefix, "
        "which does not fit stable = true\n"
    )


def test_without_the_flag_a_legacy_tag_still_fails(
    stable_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Keep the default strict, so the first run shows the problem."""
    code, out, err = run(
        capsys, stable_project, "--format", "plain", "sort", "--tag", "v0.2026.11.1"
    )
    assert code == 1
    assert "unexpected_stability_prefix" in out
    assert err == ""


def test_skip_other_stability_works_in_the_other_direction(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Skip versions without the `0.` prefix when the project is unstable."""
    (tmp_path / "calver-scm.toml").write_text("stable = false\n", encoding="utf-8")
    code, out, err = run(
        capsys,
        tmp_path,
        "--format",
        "plain",
        "sort",
        "--skip-other-stability",
        "2026.4.2",
        "0.2026.4.10",
        "0.2026.4.3",
    )
    assert (code, out.splitlines()) == (0, ["0.2026.4.3", "0.2026.4.10"])
    assert err == (
        "note: skipped 1 version with no '0.' prefix, "
        "which does not fit stable = false\n"
    )


def test_skip_other_stability_does_not_hide_real_mistakes(
    stable_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Still fail on a malformed version, which is not a stability mismatch."""
    code, out, _ = run(
        capsys,
        stable_project,
        "--format",
        "plain",
        "sort",
        "--skip-other-stability",
        "0.2026.4.1",
        "2026.13.1",
        "2026.4.2",
    )
    assert code == 1
    assert out.startswith("invalid: 2026.13.1\n")


def test_skip_other_stability_is_quiet_when_nothing_is_skipped(
    stable_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Say nothing on stderr when every input was usable."""
    code, out, err = run(
        capsys,
        stable_project,
        "--format",
        "plain",
        "sort",
        "--skip-other-stability",
        "2026.4.3",
        "2026.4.2",
    )
    assert (code, out.splitlines(), err) == (0, ["2026.4.2", "2026.4.3"], "")


def test_skipping_everything_is_a_usage_error(
    stable_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Refuse an empty result a script would take as success."""
    code, out, err = run(
        capsys,
        stable_project,
        "--format",
        "plain",
        "sort",
        "--skip-other-stability",
        "0.2026.4.1",
        "0.2026.4.2",
    )
    assert (code, out) == (2, "")
    assert "no versions left to sort" in err


def test_skip_note_goes_to_stderr_so_json_stays_parseable(
    stable_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Keep stdout to the result, whatever the format."""
    code, out, err = run(
        capsys,
        stable_project,
        "--json",
        "sort",
        "--skip-other-stability",
        "0.2026.4.1",
        "2026.4.2",
    )
    assert code == 0
    assert json.loads(out) == {"versions": ["2026.4.2"]}
    assert "skipped 1 version" in err

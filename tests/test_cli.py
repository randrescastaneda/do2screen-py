"""CLI: JSON output, exit codes, flags, determinism."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from do2screen.cli import main
from tests.conftest import write_do


def test_valid_invocation_writes_single_json(tmp_path, capsys):
    path = write_do(tmp_path, "f.do", "gen x = 1\n")
    code = main([str(path), "x"])
    assert code == 0
    out, err = capsys.readouterr()
    data = json.loads(out)
    assert data["variable"] == "x"
    assert "ranges" in data
    assert "attributed_ranges" in data
    assert "unresolved_blocks" in data
    assert "coverage" in data
    assert data["provenance_chunk"]["variable"] == "x"
    assert "error" not in err


def test_invalid_variable_exit_2(tmp_path, capsys):
    path = write_do(tmp_path, "f.do", "gen x = 1\n")
    code = main([str(path), "not a variable"])
    assert code == 2
    assert "invalid variable" in capsys.readouterr().err


def test_invalid_path_exit_1(tmp_path, capsys):
    code = main([str(tmp_path / "missing.do"), "x"])
    assert code == 1


def test_non_file_path_exit_1(tmp_path, capsys):
    code = main([str(tmp_path), "x"])
    assert code == 1


def test_no_follow_parents_flag(tmp_path, capsys):
    path = write_do(tmp_path, "f.do", "gen y = 1\ngen x = y + 1\n")
    code = main([str(path), "x", "--no-follow-parents"])
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["ancestors"] == []


def test_labels_flag(tmp_path, capsys):
    path = write_do(tmp_path, "f.do", 'label variable x "label"\ngen x = 1\n')
    code = main([str(path), "x", "--labels"])
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    # With the registry absent all statements degrade to unknown_command; the
    # JSON shape still holds and the label flag is accepted without error.
    assert set(data) >= {"variable", "ranges", "ancestors"}


def test_indent_flag(tmp_path, capsys):
    path = write_do(tmp_path, "f.do", "gen x = 1\n")
    code = main([str(path), "x", "--indent", "0"])
    assert code == 0
    out = capsys.readouterr().out
    assert "\n  " not in out  # compact output


def test_deterministic_stdout(tmp_path, capsys):
    path = write_do(tmp_path, "f.do", "gen x = 1\n")
    main([str(path), "x"])
    first = capsys.readouterr().out
    main([str(path), "x"])
    assert capsys.readouterr().out == first


def test_markdown_format_renders_contiguous_lineage_and_assessment(tmp_path, capsys):
    path = write_do(tmp_path, "f.do", "gen y = 1\ngen x = y + 1\n")
    assert main([str(path), "x", "--format", "markdown"]) == 0
    out, err = capsys.readouterr()
    assert err == ""
    assert out.startswith("# Variable provenance: x\n")
    assert "Resolved lineage slice." in out
    assert "Standalone Stata execution is not assessed." in out
    assert "Ordering: execution order." in out
    assert "## Resolved lineage code" in out
    assert "```stata\n" in out
    assert "gen y = 1\n\n* [" in out
    assert "gen x = y + 1" in out
    assert "## Potential replication context" in out
    assert "No unresolved blocks or project diagnostics were recorded." in out


def test_markdown_format_renders_unresolved_context(tmp_path, capsys):
    path = write_do(tmp_path, "f.do", "gen x = 1\nunknown_command x\n")
    assert main([str(path), "x", "--format", "markdown"]) == 0
    out, _ = capsys.readouterr()
    assert "## Potential replication context" in out
    assert "Reason: unknown_command" in out
    assert "Source range:" in out
    assert "Context:" in out
    assert "Statement:" in out
    assert "unknown_command x" in out
    assert "Source lines:" in out


def test_markdown_format_is_deterministic_and_ignores_indent(tmp_path, capsys):
    path = write_do(tmp_path, "f.do", 'gen x = "```"\n')
    assert main([str(path), "x", "--format", "markdown", "--indent", "0"]) == 0
    first = capsys.readouterr().out
    assert main([str(path), "x", "--format", "markdown", "--indent", "4"]) == 0
    second = capsys.readouterr().out
    assert second == first
    assert "````stata\n" in first
    assert "gen x = \"```\"" in first


def test_markdown_format_empty_target_is_explicit(tmp_path, capsys):
    path = write_do(tmp_path, "f.do", "gen y = 1\n")
    assert main([str(path), "missing", "--format", "markdown"]) == 0
    out, _ = capsys.readouterr()
    assert "Lineage variables without lifecycle ranges:" in out
    assert "- `missing`" in out
    assert "No selected lifecycle statements were resolved." in out


def test_module_invocation_smoke(tmp_path):
    path = write_do(tmp_path, "f.do", "gen x = 1\n")
    proc = subprocess.run(
        [sys.executable, "-m", "do2screen.cli", str(path), "x"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    json.loads(proc.stdout)


def test_directory_project_mode(tmp_path, capsys):
    write_do(tmp_path, "a.do", "gen base = 1\n")
    write_do(tmp_path, "b.do", "gen x = base + 1\n")
    code = main(["--dir", str(tmp_path), "--variable", "x"])
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["input_mode"] == "directory"
    assert data["variable"] == "x"


def test_project_modes_are_byte_deterministic(tmp_path, capsys):
    source = write_do(tmp_path, "one.do", "gen x = 1\n")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"version": 1, "files": [source.name]}), encoding="utf-8")
    invocations = [
        ["--dir", str(tmp_path), "--variable", "x"],
        ["--files", str(source), "--variable", "x"],
        ["--manifest", str(manifest), "--variable", "x"],
    ]
    for invocation in invocations:
        assert main(invocation) == 0
        first = capsys.readouterr().out
        assert main(invocation) == 0
        second = capsys.readouterr().out
        assert second == first


def test_files_project_mode_preserves_order(tmp_path, capsys):
    first = write_do(tmp_path, "first.do", "gen base = 1\n")
    second = write_do(tmp_path, "second.do", "gen x = base + 1\n")
    code = main(["--files", str(first), str(second), "--variable", "x"])
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["input_mode"] == "files"
    assert data["project_files"] == [str(first.resolve()), str(second.resolve())]


def test_manifest_project_mode(tmp_path, capsys):
    source = write_do(tmp_path, "one.do", "gen x = 1\n")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"version": 1, "files": [source.name]}),
        encoding="utf-8",
    )
    code = main(["--manifest", str(manifest), "--variable", "x"])
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["input_mode"] == "manifest"
    assert data["manifest_path"] == str(manifest.resolve())


def test_project_mode_requires_named_variable(tmp_path):
    with pytest.raises(SystemExit):
        main(["--dir", str(tmp_path)])


def test_project_mode_rejects_positional_arguments(tmp_path):
    with pytest.raises(SystemExit):
        main(["--dir", str(tmp_path), "x"])


def test_recursive_requires_directory(tmp_path):
    with pytest.raises(SystemExit):
        main(["--files", str(tmp_path / "one.do"), "--variable", "x", "--recursive"])


def test_invalid_project_invocation_returns_two_and_no_stdout(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["--dir", str(tmp_path)])
    assert exc_info.value.code == 2
    out, err = capsys.readouterr()
    assert out == ""
    assert "--variable is required" in err


def test_project_partial_success_keeps_diagnostic_in_json(tmp_path, capsys):
    existing = write_do(tmp_path, "exists.do", "gen x = 1\n")
    code = main(
        [
            "--files",
            str(existing),
            str(tmp_path / "missing.do"),
            "--variable",
            "x",
        ]
    )
    assert code == 0
    out, err = capsys.readouterr()
    data = json.loads(out)
    assert data["ranges"]
    assert any(item["code"] == "missing_root" for item in data["project_diagnostics"])
    assert out.lstrip().startswith("{\n")
    assert "error" not in err


def test_project_with_no_readable_roots_has_no_stdout_json(tmp_path, capsys):
    code = main(
        [
            "--files",
            str(tmp_path / "missing.do"),
            "--variable",
            "x",
        ]
    )
    assert code == 1
    out, err = capsys.readouterr()
    assert out == ""
    assert "missing" in err

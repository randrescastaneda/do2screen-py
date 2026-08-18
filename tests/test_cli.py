"""CLI: JSON output, exit codes, flags, determinism."""

from __future__ import annotations

import json
import subprocess
import sys

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
"""Deterministic directory and explicit-file ingestion."""

from __future__ import annotations

import pytest

from do2screen.ingest import directory_spec, files_spec


def test_files_spec_is_ordered_and_preserves_root_occurrences(tmp_path):
    first = tmp_path / "first.do"
    second = tmp_path / "second.ado"
    spec = files_spec([first, second, first])
    assert spec.mode == "files"
    assert spec.ordered is True
    assert spec.files == (str(first.resolve()), str(second.resolve()), str(first.resolve()))


def test_files_spec_rejects_empty_input():
    with pytest.raises(ValueError):
        files_spec([])


def test_directory_spec_discovers_visible_stata_sources(tmp_path):
    (tmp_path / "z.do").write_text("", encoding="utf-8")
    (tmp_path / "a.ado").write_text("", encoding="utf-8")
    (tmp_path / "ignored.txt").write_text("", encoding="utf-8")
    (tmp_path / ".hidden.do").write_text("", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "nested.do").write_text("", encoding="utf-8")

    flat = directory_spec(tmp_path)
    recursive = directory_spec(tmp_path, recursive=True)
    assert flat.files == (str((tmp_path / "a.ado").resolve()), str((tmp_path / "z.do").resolve()))
    assert recursive.files == (
        str((tmp_path / "a.ado").resolve()),
        str((nested / "nested.do").resolve()),
        str((tmp_path / "z.do").resolve()),
    )
    assert flat.ordered is False
    assert flat.recursive is False
    assert recursive.recursive is True


def test_directory_spec_excludes_external_file_symlink(tmp_path):
    outside = tmp_path.parent / "outside.do"
    outside.write_text("", encoding="utf-8")
    link = tmp_path / "linked.do"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symbolic links are unavailable")
    spec = directory_spec(tmp_path)
    assert str(link.resolve()) not in spec.files
    assert any(d.code == "external_symlink_excluded" for d in spec.diagnostics)


def test_empty_directory_is_explicitly_diagnostic(tmp_path):
    spec = directory_spec(tmp_path)
    assert spec.files == ()
    assert any(d.code == "empty_directory" for d in spec.diagnostics)


def test_directory_spec_excludes_external_symlinked_directory(tmp_path):
    outside = tmp_path.parent / "outside_sources"
    outside.mkdir()
    (outside / "external.do").write_text("gen x = 1\n", encoding="utf-8")
    link = tmp_path / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links are unavailable")
    spec = directory_spec(tmp_path, recursive=True)
    assert str((outside / "external.do").resolve()) not in spec.files

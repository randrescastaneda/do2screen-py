"""Manifest V1 validation and path normalization."""

from __future__ import annotations

import json

import pytest

from do2screen.manifest import load_manifest


def write_manifest(tmp_path, payload):
    path = tmp_path / "project.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_manifest_v1_resolves_relative_paths_and_deduplicates(tmp_path):
    path = write_manifest(
        tmp_path,
        {"version": 1, "files": ["a.do", "./a.do", "nested/../b.ado"]},
    )
    manifest_path, files = load_manifest(path)
    assert manifest_path == str(path.resolve())
    assert files == [str((tmp_path / "a.do").resolve()), str((tmp_path / "b.ado").resolve())]


@pytest.mark.parametrize(
    "payload",
    [
        {"version": 1, "files": []},
        {"version": 2, "files": ["a.do"]},
        {"version": 1.0, "files": ["a.do"]},
        {"version": True, "files": ["a.do"]},
        {"version": None, "files": ["a.do"]},
        {"files": ["a.do"]},
        {"version": 1},
        {"version": 1, "files": [1]},
        {"version": 1, "files": ["a.do"], "extra": True},
    ],
)
def test_manifest_rejects_invalid_v1_shapes(tmp_path, payload):
    with pytest.raises(ValueError):
        load_manifest(write_manifest(tmp_path, payload))


def test_manifest_rejects_non_object(tmp_path):
    path = tmp_path / "project.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        load_manifest(path)


def test_manifest_rejects_malformed_json(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text('{"version": 1,', encoding="utf-8")
    with pytest.raises(ValueError):
        load_manifest(path)


def test_manifest_accepts_and_canonicalizes_absolute_entries(tmp_path):
    source = tmp_path / "source.do"
    source.write_text("", encoding="utf-8")
    path = write_manifest(tmp_path, {"version": 1, "files": [str(source)]})
    _, files = load_manifest(path)
    assert files == [str(source.resolve())]

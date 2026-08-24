"""Validation and loading for the project manifest V1 format."""

from __future__ import annotations

import json
import os
from typing import Any


def canonical_path(path: str | os.PathLike[str]) -> str:
    """Return a normalized absolute physical path without requiring existence."""
    value = os.fsdecode(os.fspath(path))
    return os.path.realpath(os.path.abspath(value))


def load_manifest(path: str | os.PathLike[str]) -> tuple[str, list[str]]:
    """Load exactly ``{"version": 1, "files": [...]}`` from *path*.

    Relative entries are resolved from the manifest directory. Canonical
    duplicates are removed with the first occurrence retained.
    """
    manifest_path = canonical_path(path)
    try:
        with open(manifest_path, encoding="utf-8") as handle:
            payload: Any = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid manifest {manifest_path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("manifest must be a JSON object")
    if set(payload) != {"version", "files"}:
        unknown = sorted(set(payload) - {"version", "files"})
        missing = sorted({"version", "files"} - set(payload))
        details: list[str] = []
        if unknown:
            details.append(f"unknown keys: {', '.join(unknown)}")
        if missing:
            details.append(f"missing keys: {', '.join(missing)}")
        raise ValueError("invalid manifest schema (" + "; ".join(details) + ")")
    if type(payload["version"]) is not int or payload["version"] != 1:
        raise ValueError("unsupported manifest version; expected integer 1")
    entries = payload["files"]
    if not isinstance(entries, list) or not entries:
        raise ValueError("manifest files must be a non-empty array")

    base_dir = os.path.dirname(manifest_path)
    files: list[str] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, str) or not entry.strip():
            raise ValueError(f"manifest files[{index}] must be a non-empty string")
        candidate = entry if os.path.isabs(entry) else os.path.join(base_dir, entry)
        resolved = canonical_path(candidate)
        if resolved not in seen:
            seen.add(resolved)
            files.append(resolved)
    return manifest_path, files


__all__ = ["canonical_path", "load_manifest"]

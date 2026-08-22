"""Deterministic project input discovery and normalization."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from do2screen.manifest import canonical_path, load_manifest
from do2screen.models import ProjectDiagnostic

InputMode = Literal["files", "directory", "manifest"]


@dataclass(frozen=True)
class IngestionSpec:
    """Normalized project inputs and non-terminal discovery diagnostics."""

    mode: InputMode
    files: tuple[str, ...]
    ordered: bool
    recursive: bool = False
    directory: str | None = None
    manifest_path: str | None = None
    diagnostics: tuple[ProjectDiagnostic, ...] = field(default_factory=tuple)


def files_spec(
    files: list[str | os.PathLike[str]]
    | tuple[str | os.PathLike[str], ...],
) -> IngestionSpec:
    """Normalize an explicitly ordered file list, rejecting empty input."""
    if not files:
        raise ValueError("files must contain at least one path")
    normalized: list[str] = []
    for index, path in enumerate(files):
        if not isinstance(path, (str, os.PathLike)):
            raise ValueError(f"files[{index}] must be a path-like value")
        normalized.append(canonical_path(path))
    return IngestionSpec(
        mode="files",
        files=tuple(normalized),
        ordered=True,
    )


def manifest_spec(path: str | os.PathLike[str]) -> IngestionSpec:
    """Load and normalize a manifest V1 input."""
    manifest_path, files = load_manifest(path)
    return IngestionSpec(
        mode="manifest",
        files=tuple(files),
        ordered=True,
        manifest_path=manifest_path,
    )


def directory_spec(
    directory: str | os.PathLike[str],
    *,
    recursive: bool = False,
) -> IngestionSpec:
    """Discover visible ``.do``/``.ado`` files deterministically.

    Lexical directories and files are visited in sorted order. Physical
    symlink targets are canonicalized before containment checks, and contained
    symlink directories are followed only once so aliases and cycles cannot
    duplicate or loop through the corpus. Directory discovery never asserts
    that the resulting sort order is execution order.
    """
    root = canonical_path(directory)
    diagnostics: list[ProjectDiagnostic] = []
    if not os.path.isdir(root):
        code = "missing_directory" if not os.path.exists(root) else "not_directory"
        diagnostics.append(
            ProjectDiagnostic(
                code=code,
                source=root,
                message=f"project directory is not readable: {root}",
            )
        )
        return IngestionSpec(
            mode="directory",
            files=(),
            ordered=False,
            recursive=recursive,
            directory=root,
            diagnostics=tuple(diagnostics),
        )

    root_path = Path(root)
    discovered: set[str] = set()
    visited_directories: set[str] = set()

    def is_contained(path: str) -> bool:
        try:
            return os.path.commonpath([root, path]) == root
        except ValueError:
            return False

    def is_hidden(path: str) -> bool:
        try:
            relative = Path(path).relative_to(root_path)
        except ValueError:
            return True
        return any(part.startswith(".") for part in relative.parts)

    def external_symlink(path: str) -> None:
        diagnostics.append(
            ProjectDiagnostic(
                code="external_symlink_excluded",
                source=canonical_path(path),
                message="symbolic-link target is outside the requested directory",
            )
        )

    def walk(current: str) -> None:
        canonical_current = canonical_path(current)
        if canonical_current in visited_directories:
            return
        if not is_contained(canonical_current) or is_hidden(canonical_current):
            return
        visited_directories.add(canonical_current)
        try:
            entries = sorted(os.scandir(current), key=lambda entry: entry.name)
        except OSError as exc:
            diagnostics.append(
                ProjectDiagnostic(
                    code="unreadable_directory",
                    source=canonical_current,
                    message=str(exc),
                    context={"error": str(exc)},
                )
            )
            return

        for entry in entries:
            if entry.name.startswith("."):
                continue
            lexical = entry.path
            resolved = lexical
            try:
                resolved = canonical_path(lexical)
                is_directory = entry.is_dir(follow_symlinks=True)
                is_file = entry.is_file(follow_symlinks=True)
            except OSError as exc:
                diagnostics.append(
                    ProjectDiagnostic(
                        code="unreadable_path",
                        source=resolved,
                        message=str(exc),
                        context={"error": str(exc)},
                    )
                )
                continue

            if not is_contained(resolved):
                if entry.is_symlink():
                    external_symlink(lexical)
                continue
            if is_hidden(resolved):
                continue
            if is_directory:
                if recursive:
                    walk(lexical)
                continue
            if not is_file or Path(entry.name).suffix.lower() not in {".do", ".ado"}:
                continue
            discovered.add(resolved)

    walk(root)
    if not discovered:
        diagnostics.append(
            ProjectDiagnostic(
                code="empty_directory",
                source=root,
                message=f"no visible .do or .ado files found in: {root}",
            )
        )
    return IngestionSpec(
        mode="directory",
        files=tuple(sorted(discovered)),
        ordered=False,
        recursive=recursive,
        directory=root,
        diagnostics=tuple(diagnostics),
    )


__all__ = [
    "IngestionSpec",
    "InputMode",
    "directory_spec",
    "files_spec",
    "manifest_spec",
]

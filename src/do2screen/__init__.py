"""do2screen-py: trace variable construction inside Stata do files.

``do2screen-py`` (import name ``do2screen``) is a Python reimplementation of
the tracing logic in do2screen (Stata). Given a do file path and a variable
name, ``trace`` returns the physical source lines that create, modify,
drop, or (when requested) label that variable, plus the ancestor variables it
depends on, recursively -- see ``TraceResult``.

The package is deterministic and offline. Command vocabulary comes from the
``stata-command-registry`` dependency; this package supplies the grammar and
never hardcodes Stata command names.

Public API:

- ``trace`` -- the entry point.
- ``trace_files``, ``trace_directory``, and ``trace_manifest`` --
  project input modes.
- ``TraceResult`` and its public submodels -- the semver-locked contract.
- ``RegistryIncompatibilityError`` -- raised when the registry cannot
  serve lookups (absent or API-incompatible).
"""

from __future__ import annotations

from do2screen.cli import main
from do2screen.models import (
    LifecycleKind,
    LineRange,
    ProjectDiagnostic,
    ProvenanceOrdering,
    ProvenanceStatement,
    RangeAttribution,
    SourceProvenance,
    TraceResult,
    UnresolvedBlock,
    VariableContext,
    VariableEffect,
    VariableIdentity,
    VariableProvenanceChunk,
    VariableTrace,
)
from do2screen.registry import RegistryIncompatibilityError
from do2screen.trace import trace, trace_directory, trace_files, trace_manifest

__version__ = "0.1.0"

__all__ = [
    "LifecycleKind",
    "LineRange",
    "ProjectDiagnostic",
    "ProvenanceOrdering",
    "ProvenanceStatement",
    "RangeAttribution",
    "RegistryIncompatibilityError",
    "SourceProvenance",
    "TraceResult",
    "UnresolvedBlock",
    "VariableEffect",
    "VariableContext",
    "VariableIdentity",
    "VariableProvenanceChunk",
    "VariableTrace",
    "main",
    "trace",
    "trace_directory",
    "trace_files",
    "trace_manifest",
]

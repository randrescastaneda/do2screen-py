"""Dependency traversal and ``TraceResult`` projection.

The whole resolved source graph is parsed before a target is selected, so the
result always carries the complete attribution inventory, unresolved blocks,
and coverage regardless of whether the target exists. Dependency cycles are
terminated with a visited set; each reachable variable is represented once.
Coverage is ``covered_executable_lines / executable_lines`` across all
traversed sources, with a documented sentinel of ``1.0`` when a source has no
executable lines.
"""

from __future__ import annotations

import os
from collections.abc import Iterable

from do2screen.ingest import directory_spec, files_spec, manifest_spec
from do2screen.models import SourceProvenance, TraceResult, VariableTrace
from do2screen.parser import ParsedGraph, Parser
from do2screen.provenance import ProvenanceEvent, build_provenance_chunk
from do2screen.registry import RegistryAdapter


def _resolve_ancestors(variable: str, parents: dict[str, list[str]]) -> list[str]:
    """Iterative depth-first ancestor resolution with cycle termination.

    Traverses direct parents depth-first in first-reference order; each
    variable appears at most once. The target itself is never its own ancestor
    (self-references via ``replace x = x`` are seeded as visited). An explicit
    stack keeps long real-world dependency chains from exhausting the Python
    recursion limit.
    """
    out: list[str] = []
    visited: set[str] = {variable}
    # Each frame holds (node, next parent index) mirroring the recursive walk.
    stack: list[tuple[str, int]] = [(variable, 0)]
    while stack:
        node, idx = stack[-1]
        plist = parents.get(node, [])
        if idx >= len(plist):
            stack.pop()
            continue
        stack[-1] = (node, idx + 1)
        parent = plist[idx]
        if parent in visited:
            continue
        visited.add(parent)
        out.append(parent)
        stack.append((parent, 0))
    return out


def _coverage_pairs(graph: ParsedGraph) -> tuple[set[tuple[str, int]], set[tuple[str, int]]]:
    """Executable and attributed (source, line) pairs across all sources.

    Coverage is keyed by ``(source, line)`` because physical line numbers
    collide across files in an include graph; flattening them to bare line
    numbers would let a fully-attributed child mask an unattributed line in
    the root.
    """
    executable: set[tuple[str, int]] = set()
    covered: set[tuple[str, int]] = set()
    for f in graph.files:
        for ln in f.executable_lines:
            executable.add((f.path, ln))
    for att in graph.attributions:
        for ln in range(att.range.start_line, att.range.end_line + 1):
            covered.add((att.range.source, ln))
    return executable, covered


def coverage_of(graph: ParsedGraph) -> float:
    """Coverage across all traversed sources, keyed by (source, line)."""
    executable, covered = _coverage_pairs(graph)
    if not executable:
        return 1.0
    numerator = sum(1 for key in executable if key in covered)
    return numerator / len(executable)


def _coverage(
    executable_lines: Iterable[int],
    attributed_lines: set[int],
) -> float:
    executable = set(executable_lines)
    if not executable:
        return 1.0
    covered = sum(1 for line in executable if line in attributed_lines)
    return covered / len(executable)


def build_result(
    graph: ParsedGraph,
    variable: str,
    *,
    follow_parents: bool,
) -> TraceResult:
    """Project a parsed graph onto a ``TraceResult`` for one variable."""
    target_lifecycle = graph.lifecycle.get(variable, [])
    if follow_parents:
        ancestors = _resolve_ancestors(variable, graph.parents)
    else:
        ancestors = []

    coverage = coverage_of(graph)
    lineage_variables = [variable, *ancestors]

    return TraceResult(
        variable=variable,
        ranges=list(target_lifecycle),
        ancestors=ancestors,
        attributed_ranges=list(graph.attributions),
        unresolved_blocks=list(graph.unresolved),
        coverage=coverage,
        sources=[f.provenance for f in graph.files],
        source=graph.files[0].provenance if graph.files else _empty_source(graph.root_path),
        provenance_chunk=build_provenance_chunk(
            variable,
            lineage_variables,
            _legacy_provenance_events(graph),
            ordering="execution",
            include_labels=graph.include_labels,
            unresolved_blocks=graph.unresolved,
            project_diagnostics=[],
        ),
    )


def _legacy_provenance_events(graph: ParsedGraph) -> list[ProvenanceEvent]:
    """Replay the parsed legacy include graph in call-site order."""
    by_source = {
        os.path.realpath(os.path.abspath(parsed.path)): parsed for parsed in graph.files
    }
    events: list[ProvenanceEvent] = []
    active: set[str] = set()

    def replay(parsed, sequence: int) -> None:
        canonical = os.path.realpath(os.path.abspath(parsed.path))
        if canonical in active:
            return
        active.add(canonical)
        try:
            ordered_events = sorted(
                enumerate(parsed.events),
                key=lambda item: (
                    item[1].range.start_line,
                    item[1].range.end_line,
                    item[0],
                ),
            )
            for _, event in ordered_events:
                if event.kind == "records" and event.attributions:
                    events.append(
                        ProvenanceEvent(
                            range=event.range,
                            attributions=tuple(event.attributions),
                            occurrence_sequence=sequence,
                        )
                    )
                if event.kind != "include" or event.include_source is None:
                    continue
                child = by_source.get(
                    os.path.realpath(os.path.abspath(event.include_source))
                )
                if child is None:
                    continue
                nonlocal_occurrence[0] += 1
                replay(child, nonlocal_occurrence[0])
        finally:
            active.remove(canonical)

    nonlocal_occurrence = [0]
    if graph.files:
        nonlocal_occurrence[0] = 1
        replay(graph.files[0], nonlocal_occurrence[0])
    return events


def _empty_source(root_path: str) -> SourceProvenance:
    return SourceProvenance(
        path=os.path.normpath(root_path),
        line_count=0,
        used_delimit=False,
        traversal_index=0,
    )


def trace(
    path: str | os.PathLike[str],
    variable: str,
    *,
    follow_parents: bool = True,
    include_labels: bool = False,
) -> TraceResult:
    """Trace a variable through a Stata do file and its includes.

    Args:
        path: Path to the root do file.
        variable: Variable name to trace.
        follow_parents: When False, leave ``ancestors`` empty while retaining
            the target's ranges and the global audit inventory.
        include_labels: When True, include label lifecycle events in the
            target and ancestor traces.

    Returns:
        A frozen, JSON-lossless ``TraceResult``. The output depends only
        on the input file and the registry version -- no network, randomness,
        or environment-dependent behaviour.

    Example:
        ``trace("data/clean.do", "income", include_labels=True)`` returns a
        ``TraceResult`` whose ``ranges`` contain the physical source
        lines for ``income``.
    """
    registry = RegistryAdapter()
    parser = Parser(registry, include_labels=include_labels)
    graph = parser.parse_graph(str(path))
    result = build_result(graph, variable, follow_parents=follow_parents)
    return result


def trace_files(
    files: list[str | os.PathLike[str]] | tuple[str | os.PathLike[str], ...],
    variable: str,
    *,
    follow_parents: bool = True,
    include_labels: bool = False,
) -> TraceResult:
    """Trace *variable* through an explicitly ordered list of source files.

    Duplicate paths are retained as separate root occurrences so execution
    order remains observable; each physical source is still parsed once.

    Args:
        files: Non-empty list or tuple of source paths. The supplied order is
            the execution order for project lineage.
        variable: Variable name to trace.
        follow_parents: When False, leave ``ancestors`` empty while retaining
            the target's ranges and the global audit inventory.
        include_labels: When True, include label lifecycle events in the
            target and ancestor traces.

    Returns:
        A project ``TraceResult`` with ``input_mode="files"``.

    Raises:
        ValueError: If ``files`` is empty or contains an invalid path-like
            value.
        RegistryIncompatibilityError: If the installed registry cannot provide
            the source-driver capability required by project tracing.
    """
    from do2screen.project import trace_project

    return trace_project(
        files_spec(files),
        variable,
        follow_parents=follow_parents,
        include_labels=include_labels,
    )


def trace_directory(
    directory: str | os.PathLike[str],
    variable: str,
    *,
    recursive: bool = False,
    follow_parents: bool = True,
    include_labels: bool = False,
) -> TraceResult:
    """Trace *variable* through visible ``.do``/``.ado`` files in a directory.

    Discovery is deterministic but semantically unordered. Cross-file lineage
    is therefore omitted when no explicit occurrence order exists and is
    reported in ``project_diagnostics``.

    Args:
        directory: Directory containing the project source files.
        variable: Variable name to trace.
        recursive: When True, discover files in nested visible directories.
        follow_parents: When False, leave ``ancestors`` empty while retaining
            the target's ranges and the global audit inventory.
        include_labels: When True, include label lifecycle events in the
            target and ancestor traces.

    Returns:
        A project ``TraceResult`` with ``input_mode="directory"``. Missing
        inputs and unordered cross-file references are reported in
        ``project_diagnostics``.

    Raises:
        RegistryIncompatibilityError: If the installed registry cannot provide
            the source-driver capability required by project tracing.
    """
    from do2screen.project import trace_project

    return trace_project(
        directory_spec(directory, recursive=recursive),
        variable,
        follow_parents=follow_parents,
        include_labels=include_labels,
    )


def trace_manifest(
    manifest_path: str | os.PathLike[str],
    variable: str,
    *,
    follow_parents: bool = True,
    include_labels: bool = False,
) -> TraceResult:
    """Trace *variable* through the ordered files in a manifest V1 document.

    Manifest V1 accepts exactly ``{"version": 1, "files": [strings]}``.

    Args:
        manifest_path: Path to a Manifest V1 JSON document.
        variable: Variable name to trace.
        follow_parents: When False, leave ``ancestors`` empty while retaining
            the target's ranges and the global audit inventory.
        include_labels: When True, include label lifecycle events in the
            target and ancestor traces.

    Returns:
        A project ``TraceResult`` with ``input_mode="manifest"`` and the
        canonical ``manifest_path``.

    Raises:
        ValueError: If the manifest cannot be read or does not match the
            Manifest V1 schema.
        RegistryIncompatibilityError: If the installed registry cannot provide
            the source-driver capability required by project tracing.
    """
    from do2screen.project import trace_project

    return trace_project(
        manifest_spec(manifest_path),
        variable,
        follow_parents=follow_parents,
        include_labels=include_labels,
    )


__all__ = [
    "VariableTrace",
    "trace",
    "trace_directory",
    "trace_files",
    "trace_manifest",
]

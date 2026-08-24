"""Project-wide tracing over ordered inputs and unordered directories.

Project mode is deliberately separate from the legacy parser graph. Each
canonical physical source is parsed at most once and its immutable events are
replayed at every root/include occurrence. The replay stream carries execution
order; the persisted attribution and unresolved records remain one physical
inventory per source for coverage and the no-dropped-lines invariant.
"""

from __future__ import annotations

import errno
import json
import os
from dataclasses import dataclass, field
from typing import Iterable

from do2screen.ingest import IngestionSpec
from do2screen.models import (
    LineRange,
    ProjectDiagnostic,
    RangeAttribution,
    SourceProvenance,
    TraceResult,
    UnresolvedBlock,
    VariableContext,
    VariableIdentity,
)
from do2screen.parser import ParsedEvent, ParsedFile, Parser
from do2screen.provenance import ProvenanceEvent, build_provenance_chunk
from do2screen.registry import RegistryAdapter
from do2screen.trace import _empty_source

_MAX_INCLUDE_DEPTH = 64


@dataclass(frozen=True)
class SourceOccurrence:
    """One execution occurrence of a cached physical source."""

    source: str
    root_order: int
    sequence: int
    caller_source: str | None = None
    caller_range: LineRange | None = None
    caller_sequence: int | None = None


@dataclass(frozen=True)
class ExecutionEvent:
    """One cached parser event replayed in an occurrence."""

    occurrence: SourceOccurrence
    event: ParsedEvent
    event_index: int = 0


@dataclass
class ProjectGraph:
    """Physical records, source occurrences, and project diagnostics."""

    root_path: str
    mode: str
    ordered: bool
    requested_files: tuple[str, ...] = field(default_factory=tuple)
    manifest_path: str | None = None
    files: dict[str, ParsedFile] = field(default_factory=dict)
    occurrences: list[SourceOccurrence] = field(default_factory=list)
    execution_events: list[ExecutionEvent] = field(default_factory=list)
    attributions: list[RangeAttribution] = field(default_factory=list)
    unresolved: list[UnresolvedBlock] = field(default_factory=list)
    diagnostics: list[ProjectDiagnostic] = field(default_factory=list)
    sources: list[SourceProvenance] = field(default_factory=list)
    file_order: dict[str, int] = field(default_factory=dict)
    persisted_sources: set[str] = field(default_factory=set)
    include_terminal_keys: set[tuple[str, int, int, int]] = field(default_factory=set)
    readable_roots: int = 0
    _sequence: int = 0

    @property
    def project_files(self) -> list[str]:
        """Return accepted inputs followed by newly reached canonical sources."""
        result: list[str] = []
        seen: set[str] = set()
        for path in self.requested_files:
            if path not in seen:
                seen.add(path)
                result.append(path)
        for path in self.file_order:
            if path not in seen:
                seen.add(path)
                result.append(path)
        return result


@dataclass
class DefinitionNode:
    """Occurrence-qualified definition context for one variable."""

    node_id: int
    variable: str
    source: str
    occurrence_sequence: int
    root_order: int
    first_creation_line: int | None = None
    lifecycle_ranges: list[LineRange] = field(default_factory=list)
    lifecycle_event_ids: list[int] = field(default_factory=list)
    parent_names: list[str] = field(default_factory=list)
    parent_nodes: list[int | None] = field(default_factory=list)

    def add_parent(self, name: str, node_id: int | None) -> None:
        """Add a direct parent once, preserving first-reference order."""
        for existing_name, existing_id in zip(
            self.parent_names,
            self.parent_nodes,
        ):
            if existing_name == name and existing_id == node_id:
                return
        self.parent_names.append(name)
        self.parent_nodes.append(node_id)


@dataclass
class _LineageState:
    nodes: list[DefinitionNode] = field(default_factory=list)
    by_variable: dict[str, list[DefinitionNode]] = field(default_factory=dict)
    lifecycle_by_variable: dict[str, list[LineRange]] = field(default_factory=dict)
    lifecycle_event_ids_by_variable: dict[str, list[int]] = field(default_factory=dict)
    active: dict[str, DefinitionNode] = field(default_factory=dict)
    active_by_root: dict[int, dict[str, DefinitionNode]] = field(default_factory=dict)
    known_variables: set[str] = field(default_factory=set)
    unbound_references: list[tuple[SourceOccurrence, RangeAttribution]] = field(
        default_factory=list
    )
    cross_root_candidates: dict[tuple[int, str], list[str]] = field(
        default_factory=dict
    )
    unordered_cross_file_references: list[
        tuple[SourceOccurrence, RangeAttribution]
    ] = field(default_factory=list)


def trace_project(
    spec: IngestionSpec,
    variable: str,
    *,
    follow_parents: bool = True,
    include_labels: bool = False,
    registry: RegistryAdapter | None = None,
) -> TraceResult:
    """Trace *variable* through a normalized project input specification."""
    project = build_project_graph(
        spec,
        include_labels=include_labels,
        registry=registry,
    )
    return _build_project_result(
        project,
        variable,
        follow_parents=follow_parents,
        include_labels=include_labels,
    )


def build_project_graph(
    spec: IngestionSpec,
    *,
    include_labels: bool = False,
    registry: RegistryAdapter | None = None,
) -> ProjectGraph:
    """Build physical project records and the occurrence execution stream."""
    adapter = registry or RegistryAdapter()
    adapter.ensure_source_driver()
    parser = Parser(
        adapter,
        include_labels=include_labels,
        require_source_driver=True,
    )
    project = ProjectGraph(
        root_path=spec.directory or (spec.files[0] if spec.files else ""),
        mode=spec.mode,
        ordered=spec.ordered,
        requested_files=spec.files,
        manifest_path=spec.manifest_path,
        diagnostics=list(spec.diagnostics),
    )
    cache: dict[str, ParsedFile | OSError] = {}
    active: list[str] = []

    for root_order, root in enumerate(spec.files):
        canonical = _canonical(root)
        try:
            parsed = _get_cached_file(parser, cache, canonical)
        except OSError as exc:
            project.diagnostics.append(
                _root_diagnostic(spec, canonical, root_order, exc)
            )
            continue
        project.readable_roots += 1
        _register_file(project, parsed)
        _persist_file_records(project, parsed)
        _replay_occurrence(
            project,
            parser,
            cache,
            parsed,
            root_order=root_order,
            caller=None,
            active=active,
        )

    assert_project_records_complete(project)
    return project


def coverage_of_project(project: ProjectGraph) -> float:
    """Compute coverage over unique cached sources using ``(source, line)``."""
    executable: set[tuple[str, int]] = set()
    covered: set[tuple[str, int]] = set()
    for parsed in project.files.values():
        executable.update((parsed.path, line) for line in parsed.executable_lines)
    for attribution in project.attributions:
        covered.update(
            (attribution.range.source, line)
            for line in range(
                attribution.range.start_line,
                attribution.range.end_line + 1,
            )
        )
    if not executable:
        return 1.0
    return len(executable & covered) / len(executable)


def assert_project_records_complete(project: ProjectGraph) -> None:
    """Assert persisted terminal records partition every executable line."""
    for parsed in project.files.values():
        executable = set(parsed.executable_lines)
        attributed = {
            line
            for attribution in project.attributions
            if attribution.range.source == parsed.path
            for line in range(
                attribution.range.start_line,
                attribution.range.end_line + 1,
            )
        }
        unresolved = {
            line
            for block in project.unresolved
            if block.range.source == parsed.path
            for line in range(block.range.start_line, block.range.end_line + 1)
        }
        terminal = (attributed | unresolved) & executable
        if terminal != executable:
            raise AssertionError(
                f"{parsed.path}: project no-dropped-lines violated; "
                f"executable={sorted(executable)} terminal={sorted(terminal)}"
            )
        overlap = (attributed & unresolved) & executable
        if overlap:
            raise AssertionError(
                f"{parsed.path}: project terminal records overlap {sorted(overlap)}"
            )


def _get_cached_file(
    parser: Parser,
    cache: dict[str, ParsedFile | OSError],
    path: str,
) -> ParsedFile:
    """Parse *path* once, caching both successful parses and OS failures."""
    if path not in cache:
        try:
            cache[path] = parser.parse_file(path)
        except OSError as exc:
            cache[path] = exc
    result = cache[path]
    if isinstance(result, OSError):
        raise result
    return result


def _register_file(project: ProjectGraph, parsed: ParsedFile) -> None:
    """Register one canonical source and assign global provenance order."""
    canonical = _canonical(parsed.path)
    if canonical in project.files:
        return
    index = len(project.file_order)
    project.files[canonical] = parsed
    project.file_order[canonical] = index
    project.sources.append(
        parsed.provenance.model_copy(
            update={"path": canonical, "traversal_index": index}
        )
    )


def _persist_file_records(project: ProjectGraph, parsed: ParsedFile) -> None:
    """Persist a physical source's records exactly once per project run."""
    canonical = _canonical(parsed.path)
    if canonical in project.persisted_sources:
        return
    project.persisted_sources.add(canonical)
    project.attributions.extend(parsed.attributions)
    project.unresolved.extend(parsed.unresolved)


def _replay_occurrence(
    project: ProjectGraph,
    parser: Parser,
    cache: dict[str, ParsedFile | OSError],
    parsed: ParsedFile,
    *,
    root_order: int,
    caller: tuple[str, LineRange] | None,
    caller_sequence: int | None = None,
    active: list[str],
) -> None:
    """Replay one source and recurse into includes at event call sites."""
    canonical = _canonical(parsed.path)
    if canonical in active:
        return
    project._sequence += 1
    occurrence = SourceOccurrence(
        source=canonical,
        root_order=root_order,
        sequence=project._sequence,
        caller_source=caller[0] if caller else None,
        caller_range=caller[1] if caller else None,
        caller_sequence=caller_sequence,
    )
    project.occurrences.append(occurrence)
    active.append(canonical)
    try:
        for event_index, event in enumerate(_ordered_events(parsed.events)):
            project.execution_events.append(
                ExecutionEvent(occurrence, event, event_index)
            )
            if event.kind != "include":
                continue
            _replay_include(
                project,
                parser,
                cache,
                parsed,
                event,
                root_order=root_order,
                caller_occurrence=occurrence,
                event_index=event_index,
                active=active,
            )
    finally:
        active.pop()


def _replay_include(
    project: ProjectGraph,
    parser: Parser,
    cache: dict[str, ParsedFile | OSError],
    parsed: ParsedFile,
    event: ParsedEvent,
    *,
    root_order: int,
    caller_occurrence: SourceOccurrence,
    event_index: int,
    active: list[str],
) -> None:
    target = event.include_target or ""
    caller_range = event.range
    if not target or _contains_include_macro(target):
        _record_include_terminal(
            project,
            caller_range,
            target=target,
            reason="macro_or_missing",
            event_index=event_index,
        )
        return

    child_path = _canonical(
        target
        if os.path.isabs(target)
        else os.path.join(os.path.dirname(parsed.path), target)
    )
    if child_path in active:
        _record_include_terminal(
            project,
            caller_range,
            target=target,
            reason="cycle",
            event_index=event_index,
        )
        return
    if len(active) >= _MAX_INCLUDE_DEPTH:
        _record_include_terminal(
            project,
            caller_range,
            target=target,
            reason="depth_exceeded",
            event_index=event_index,
        )
        return
    if project.mode == "directory" and project.root_path:
        if not _is_within(project.root_path, child_path):
            _record_include_terminal(
                project,
                caller_range,
                target=target,
                reason="outside_project",
                event_index=event_index,
            )
            return

    try:
        child = _get_cached_file(parser, cache, child_path)
    except OSError as exc:
        _record_include_terminal(
            project,
            caller_range,
            target=target,
            reason="missing" if _is_missing_error(exc) else "unreadable",
            error=str(exc),
            event_index=event_index,
        )
        return

    _register_file(project, child)
    _persist_file_records(project, child)
    _record_include_terminal(
        project,
        caller_range,
        target=target,
        reason="resolved",
        event_index=event_index,
    )
    _replay_occurrence(
        project,
        parser,
        cache,
        child,
        root_order=root_order,
        caller=(parsed.path, caller_range),
        caller_sequence=caller_occurrence.sequence,
        active=active,
    )


def _ordered_events(events: Iterable[ParsedEvent]) -> list[ParsedEvent]:
    """Return events in physical order while preserving same-range order."""
    return sorted(
        events,
        key=lambda event: (event.range.start_line, event.range.end_line),
    )


def _record_include_terminal(
    project: ProjectGraph,
    line_range: LineRange,
    *,
    target: str,
    reason: str,
    error: str | None = None,
    event_index: int,
) -> None:
    """Persist one include call's physical terminal disposition once."""
    key = (
        line_range.source,
        line_range.start_line,
        line_range.end_line,
        event_index,
    )
    if key in project.include_terminal_keys:
        return
    descriptor = {"target": target, "reason": reason}
    if error:
        descriptor["error"] = error
    for start_line, end_line in _available_project_intervals(project, line_range):
        piece_range = _range_slice(line_range, start_line, end_line)
        if reason == "resolved":
            block = UnresolvedBlock(
                range=piece_range,
                reason="no_variable_attribution",
                context={
                    "include": target,
                    "resolved": "true",
                    "include_calls": _encode_include_calls([descriptor]),
                },
                statement=None,
            )
        else:
            context = {"target": target, "reason": reason}
            if error:
                context["error"] = error
            context["include_calls"] = _encode_include_calls([descriptor])
            block = UnresolvedBlock(
                range=piece_range,
                reason="unresolved_include",
                context=context,
                statement=None,
            )
        project.unresolved.append(block)
    if not _available_project_intervals(project, line_range):
        existing = next(
            (
                block
                for block in project.unresolved
                if block.range.source == line_range.source
                and block.range.start_line == line_range.start_line
                and block.range.end_line == line_range.end_line
                and "include_calls" in block.context
                and block.reason == "no_variable_attribution"
            ),
            None,
        )
        if existing is not None:
            calls = _decode_include_calls(existing.context.get("include_calls", "[]"))
            calls.append(descriptor)
            context = dict(existing.context)
            context["include_calls"] = _encode_include_calls(calls)
            replacement = UnresolvedBlock(
                range=existing.range,
                reason=existing.reason,
                context=context,
                statement=existing.statement,
            )
            position = project.unresolved.index(existing)
            project.unresolved[position] = replacement
    project.include_terminal_keys.add(key)


def _build_project_result(
    project: ProjectGraph,
    variable: str,
    *,
    follow_parents: bool,
    include_labels: bool,
) -> TraceResult:
    state = _build_lineage(project, include_labels=include_labels)
    if follow_parents:
        ancestors, reachable_node_ids = _resolve_node_lineage(variable, state)
    else:
        ancestors = []
        reachable_node_ids = {
            node.node_id for node in state.by_variable.get(variable, [])
        }
    first_source = _project_source(project)
    lineage_variables = [variable, *ancestors]
    return TraceResult(
        variable=variable,
        ranges=list(state.lifecycle_by_variable.get(variable, [])),
        ancestors=ancestors,
        attributed_ranges=list(project.attributions),
        unresolved_blocks=list(project.unresolved),
        coverage=coverage_of_project(project),
        sources=list(project.sources),
        source=first_source,
        input_mode=project.mode,
        project_files=project.project_files,
        variable_identities=_identities(state, project),
        manifest_path=project.manifest_path,
        project_diagnostics=list(project.diagnostics),
        provenance_chunk=build_provenance_chunk(
            variable,
            lineage_variables,
            _project_provenance_events(
                project,
                state,
                variable,
                reachable_node_ids,
            ),
            ordering="execution" if project.ordered else "per_source",
            include_labels=include_labels,
            unresolved_blocks=project.unresolved,
            project_diagnostics=project.diagnostics,
        ),
    )


def _build_lineage(
    project: ProjectGraph,
    *,
    include_labels: bool,
) -> _LineageState:
    state = _LineageState()
    state.known_variables = {
        attribution.variable
        for execution in project.execution_events
        for attribution in execution.event.attributions
        if attribution.kind == "created"
    }
    if not project.ordered:
        state.cross_root_candidates = _build_cross_root_candidate_index(project)

    for event_id, execution in enumerate(project.execution_events):
        event = execution.event
        if event.kind != "records" or not event.attributions:
            continue
        _apply_event(
            state,
            event,
            execution.occurrence,
            event_id=event_id,
            ordered=project.ordered,
            include_labels=include_labels,
        )

    if project.ordered:
        _add_ordered_diagnostics(project, state)
    else:
        _add_unordered_diagnostics(project, state)
    return state


def _apply_event(
    state: _LineageState,
    event: ParsedEvent,
    occurrence: SourceOccurrence,
    *,
    event_id: int,
    ordered: bool,
    include_labels: bool,
) -> None:
    target_attrs = [
        attribution
        for attribution in event.attributions
        if attribution.kind != "referenced"
        and (attribution.kind != "labelled" or include_labels)
    ]
    reference_attrs = [
        attribution
        for attribution in event.attributions
        if attribution.kind == "referenced"
    ]
    active = (
        state.active
        if ordered
        else state.active_by_root.setdefault(occurrence.root_order, {})
    )

    reference_nodes: list[tuple[RangeAttribution, DefinitionNode | None]] = []
    for reference in reference_attrs:
        parent = active.get(reference.variable)
        candidates = (
            state.cross_root_candidates.get(
                (occurrence.root_order, reference.variable),
                [],
            )
            if not ordered
            else []
        )
        if not ordered and parent is None and candidates:
            parent = None
            state.unordered_cross_file_references.append((occurrence, reference))
        if parent is None and reference.variable in state.known_variables:
            state.unbound_references.append((occurrence, reference))
        reference_nodes.append((reference, parent))

    target_nodes: list[DefinitionNode] = []
    for attribution in target_attrs:
        state.lifecycle_by_variable.setdefault(attribution.variable, []).append(
            attribution.range
        )
        state.lifecycle_event_ids_by_variable.setdefault(
            attribution.variable, []
        ).append(event_id)
        if attribution.kind == "created":
            node = DefinitionNode(
                node_id=len(state.nodes),
                variable=attribution.variable,
                source=occurrence.source,
                occurrence_sequence=occurrence.sequence,
                root_order=occurrence.root_order,
                first_creation_line=attribution.range.start_line,
            )
            state.nodes.append(node)
            state.by_variable.setdefault(node.variable, []).append(node)
            active[node.variable] = node
            node.lifecycle_ranges.append(attribution.range)
            node.lifecycle_event_ids.append(event_id)
            target_nodes.append(node)
            continue

        node = active.get(attribution.variable)
        if node is not None:
            node.lifecycle_ranges.append(attribution.range)
            node.lifecycle_event_ids.append(event_id)
            target_nodes.append(node)
        if attribution.kind == "dropped":
            active.pop(attribution.variable, None)

    for reference, parent in reference_nodes:
        if parent is None and reference.variable in state.known_variables:
            continue
        for node in target_nodes:
            node.add_parent(reference.variable, parent.node_id if parent else None)

    if event.effect == "renames":
        for reference in reference_attrs:
            active.pop(reference.variable, None)


def _add_ordered_diagnostics(
    project: ProjectGraph,
    state: _LineageState,
) -> None:
    seen: set[tuple[str, int, str]] = set()
    for occurrence, attribution in state.unbound_references:
        key = (
            attribution.range.source,
            attribution.range.start_line,
            attribution.variable,
        )
        if key in seen:
            continue
        seen.add(key)
        project.diagnostics.append(
            ProjectDiagnostic(
                code="unbound_reference",
                message="reference has no active preceding definition",
                source=attribution.range.source,
                variable=attribution.variable,
                range=attribution.range,
                context={
                    "reason": "no_active_definition",
                    "occurrence_sequence": str(occurrence.sequence),
                },
            )
        )


def _add_unordered_diagnostics(
    project: ProjectGraph,
    state: _LineageState,
) -> None:
    definitions = {
        variable: list(nodes)
        for variable, nodes in state.by_variable.items()
        if any(node.first_creation_line is not None for node in nodes)
    }
    seen_references: set[tuple[str, int, str, tuple[str, ...]]] = set()
    for occurrence, attribution in state.unordered_cross_file_references:
        candidates = _cross_root_candidates(
            project,
            occurrence,
            attribution,
            definitions,
        )
        key = (
            attribution.range.source,
            attribution.range.start_line,
            attribution.variable,
            tuple(candidates),
        )
        if key in seen_references:
            continue
        seen_references.add(key)
        project.diagnostics.append(
            ProjectDiagnostic(
                code="cross_file_unordered",
                message="cross-file reference has no declared execution order",
                source=attribution.range.source,
                variable=attribution.variable,
                candidate_sources=candidates,
                range=attribution.range,
                context={
                    "referencing_source": attribution.range.source,
                    "root_order": str(occurrence.root_order),
                },
            )
        )

    seen_unbound: set[tuple[str, int, str]] = set()
    for occurrence, attribution in state.unbound_references:
        if state.cross_root_candidates.get(
            (occurrence.root_order, attribution.variable)
        ):
            continue
        key = (
            attribution.range.source,
            attribution.range.start_line,
            attribution.variable,
        )
        if key in seen_unbound:
            continue
        seen_unbound.add(key)
        project.diagnostics.append(
            ProjectDiagnostic(
                code="unbound_reference",
                message="reference has no active definition in this source occurrence",
                source=attribution.range.source,
                variable=attribution.variable,
                range=attribution.range,
                context={
                    "reason": "no_active_definition",
                    "root_order": str(occurrence.root_order),
                },
            )
        )

    for variable, nodes in definitions.items():
        by_source: dict[str, list[DefinitionNode]] = {}
        by_root: dict[int, set[str]] = {}
        for node in nodes:
            if node.first_creation_line is None:
                continue
            by_source.setdefault(node.source, []).append(node)
            by_root.setdefault(node.root_order, set()).add(node.source)
        if len(by_root) < 2 or len(by_source) < 2:
            continue
        sources = sorted(by_source)
        for source in sources:
            first = min(
                by_source[source],
                key=lambda node: (
                    node.first_creation_line or 0,
                    node.node_id,
                ),
            )
            project.diagnostics.append(
                ProjectDiagnostic(
                    code="cross_file_unordered",
                    message="variable has definitions in multiple unordered sources",
                    source=source,
                    variable=variable,
                    candidate_sources=[candidate for candidate in sources if candidate != source],
                    range=first.lifecycle_ranges[0] if first.lifecycle_ranges else None,
                    context={"kind": "duplicate_definition"},
                )
            )


def _cross_root_candidates(
    project: ProjectGraph,
    occurrence: SourceOccurrence,
    attribution: RangeAttribution,
    definitions: dict[str, list[DefinitionNode]],
) -> list[str]:
    current_sources = {
        current.source
        for current in project.occurrences
        if current.root_order == occurrence.root_order
    }
    return sorted(
        {
            node.source
            for node in definitions.get(attribution.variable, [])
            if node.root_order != occurrence.root_order
            and node.source not in current_sources
            and node.source != attribution.range.source
        }
    )


def _build_cross_root_candidate_index(
    project: ProjectGraph,
) -> dict[tuple[int, str], list[str]]:
    definitions: dict[str, list[tuple[str, int]]] = {}
    for execution in project.execution_events:
        for attribution in execution.event.attributions:
            if attribution.kind == "created":
                definitions.setdefault(attribution.variable, []).append(
                    (
                        execution.occurrence.source,
                        execution.occurrence.root_order,
                    )
                )
    root_sources: dict[int, set[str]] = {}
    for occurrence in project.occurrences:
        root_sources.setdefault(occurrence.root_order, set()).add(occurrence.source)

    result: dict[tuple[int, str], list[str]] = {}
    for variable, candidates in definitions.items():
        for root_order, current_sources in root_sources.items():
            sources = sorted(
                {
                    source
                    for source, candidate_root in candidates
                    if candidate_root != root_order
                    and source not in current_sources
                }
            )
            if sources:
                result[(root_order, variable)] = sources
    return result


def _resolve_node_lineage(
    variable: str,
    state: _LineageState,
) -> tuple[list[str], set[int]]:
    """Resolve names and occurrence-qualified nodes in first-reference DFS order."""
    result: list[str] = []
    seen_names: set[str] = {variable}
    visited_nodes: set[int] = set()
    for root in state.by_variable.get(variable, []):
        if root.node_id in visited_nodes:
            continue
        visited_nodes.add(root.node_id)
        stack: list[tuple[DefinitionNode, int]] = [(root, 0)]
        while stack:
            node, index = stack[-1]
            if index >= len(node.parent_names):
                stack.pop()
                continue
            stack[-1] = (node, index + 1)
            name = node.parent_names[index]
            parent_id = node.parent_nodes[index]
            if name not in seen_names:
                seen_names.add(name)
                result.append(name)
            if parent_id is not None and parent_id not in visited_nodes:
                parent = state.nodes[parent_id]
                visited_nodes.add(parent.node_id)
                stack.append((parent, 0))
    return result, visited_nodes


def _resolve_node_ancestors(variable: str, state: _LineageState) -> list[str]:
    """Resolve occurrence-qualified nodes in first-reference DFS order."""
    ancestors, _ = _resolve_node_lineage(variable, state)
    return ancestors


def _project_provenance_events(
    project: ProjectGraph,
    state: _LineageState,
    variable: str,
    reachable_node_ids: set[int],
) -> list[ProvenanceEvent]:
    """Select exact lifecycle event occurrences from reachable definition nodes."""
    selected_event_ids = {
        event_id
        for node in state.nodes
        if node.node_id in reachable_node_ids
        for event_id in node.lifecycle_event_ids
    }
    selected_event_ids.update(
        event_id
        for event_id in state.lifecycle_event_ids_by_variable.get(variable, [])
    )
    events: list[tuple[int, ProvenanceEvent]] = []
    for event_id, execution in enumerate(project.execution_events):
        if event_id not in selected_event_ids:
            continue
        events.append(
            (
                event_id,
                ProvenanceEvent(
                    range=execution.event.range,
                    attributions=tuple(execution.event.attributions),
                    occurrence_sequence=(
                        execution.occurrence.sequence if project.ordered else None
                    ),
                ),
            )
        )
    if not project.ordered:
        events.sort(
            key=lambda item: (
                item[1].range.source,
                item[1].range.start_line,
                item[1].range.end_line,
                item[0],
            )
        )
        deduplicated: list[tuple[int, ProvenanceEvent]] = []
        seen_physical_events: set[tuple[str, int]] = set()
        for event_id, event in events:
            execution = project.execution_events[event_id]
            identity = (execution.occurrence.source, execution.event_index)
            if identity in seen_physical_events:
                continue
            seen_physical_events.add(identity)
            deduplicated.append((event_id, event))
        events = deduplicated
    return [event for _, event in events]


def _identities(
    state: _LineageState,
    project: ProjectGraph,
) -> list[VariableIdentity]:
    occurrences = {
        occurrence.sequence: occurrence
        for occurrence in project.occurrences
    }
    result: list[VariableIdentity] = []
    for variable, nodes in state.by_variable.items():
        contexts = [
            VariableContext(
                source=node.source,
                first_creation_line=node.first_creation_line,
                lifecycle_ranges=list(node.lifecycle_ranges),
                direct_parents=list(node.parent_names),
                occurrence_sequence=node.occurrence_sequence,
                caller_sequence=(
                    occurrences[node.occurrence_sequence].caller_sequence
                    if node.occurrence_sequence in occurrences
                    else None
                ),
                caller_source=(
                    occurrences[node.occurrence_sequence].caller_source
                    if node.occurrence_sequence in occurrences
                    else None
                ),
                caller_range=(
                    occurrences[node.occurrence_sequence].caller_range
                    if node.occurrence_sequence in occurrences
                    else None
                ),
            )
            for node in nodes
            if node.first_creation_line is not None
        ]
        if contexts:
            result.append(VariableIdentity(variable=variable, contexts=contexts))
    return result


def _project_source(project: ProjectGraph) -> SourceProvenance:
    if project.requested_files:
        first_requested = _canonical(project.requested_files[0])
        for source in project.sources:
            if source.path == first_requested:
                return source
        return _empty_source(first_requested)
    if project.sources:
        return project.sources[0]
    fallback = project.requested_files[0] if project.requested_files else project.root_path
    return _empty_source(_canonical(fallback) if fallback else fallback)


def _root_diagnostic(
    spec: IngestionSpec,
    path: str,
    root_order: int,
    error: OSError,
) -> ProjectDiagnostic:
    code = "unresolved_manifest_file" if spec.mode == "manifest" else (
        "missing_root" if _is_missing_error(error) else "unreadable_root"
    )
    return ProjectDiagnostic(
        code=code,
        source=path,
        manifest_path=spec.manifest_path,
        message=f"project input is missing or unreadable: {path}",
        context={
            "root_order": str(root_order),
            "error": str(error),
        },
    )


def _is_missing_error(error: OSError) -> bool:
    return getattr(error, "errno", None) in {errno.ENOENT, errno.ENOTDIR}


def _is_within(root: str, path: str) -> bool:
    try:
        return os.path.commonpath([_canonical(root), _canonical(path)]) == _canonical(root)
    except ValueError:
        return False


def _available_project_intervals(
    project: ProjectGraph,
    line_range: LineRange,
) -> list[tuple[int, int]]:
    blocked: set[int] = set()
    for attribution in project.attributions:
        if attribution.range.source != line_range.source:
            continue
        blocked.update(
            range(
                attribution.range.start_line,
                attribution.range.end_line + 1,
            )
        )
    for block in project.unresolved:
        if block.range.source != line_range.source:
            continue
        blocked.update(range(block.range.start_line, block.range.end_line + 1))
    return _open_intervals(line_range.start_line, line_range.end_line, blocked)


def _open_intervals(
    start_line: int,
    end_line: int,
    blocked: set[int],
) -> list[tuple[int, int]]:
    intervals: list[tuple[int, int]] = []
    interval_start: int | None = None
    for line in range(start_line, end_line + 1):
        if line in blocked:
            if interval_start is not None:
                intervals.append((interval_start, line - 1))
                interval_start = None
        elif interval_start is None:
            interval_start = line
    if interval_start is not None:
        intervals.append((interval_start, end_line))
    return intervals


def _range_slice(
    line_range: LineRange,
    start_line: int,
    end_line: int,
) -> LineRange:
    offset = start_line - line_range.start_line
    return LineRange(
        source=line_range.source,
        start_line=start_line,
        end_line=end_line,
        comment_start_line=(
            line_range.comment_start_line
            if start_line == line_range.start_line
            else None
        ),
        comment_end_line=(
            line_range.comment_end_line
            if start_line == line_range.start_line
            else None
        ),
        source_lines=line_range.source_lines[
            offset : offset + end_line - start_line + 1
        ],
    )


def _encode_include_calls(calls: list[dict[str, str]]) -> str:
    """Serialize same-line include outcomes deterministically in a context value."""
    return json.dumps(calls, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _decode_include_calls(value: str) -> list[dict[str, str]]:
    """Decode the private same-line include outcome context defensively."""
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(decoded, list):
        return []
    return [
        {str(key): str(item) for key, item in entry.items()}
        for entry in decoded
        if isinstance(entry, dict)
    ]


def _contains_include_macro(text: str) -> bool:
    return "`" in text or "$" in text


def _canonical(path: str | os.PathLike[str]) -> str:
    return os.path.realpath(os.path.abspath(os.fspath(path)))


__all__ = [
    "DefinitionNode",
    "ExecutionEvent",
    "ProjectGraph",
    "SourceOccurrence",
    "assert_project_records_complete",
    "build_project_graph",
    "coverage_of_project",
    "trace_project",
]

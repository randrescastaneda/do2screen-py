"""Projection and display helpers for variable provenance chunks.

This module consumes parser attributions and replay events. It deliberately
does not classify Stata commands or infer execution semantics.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import cast

from do2screen.models import (
    LifecycleKind,
    LineRange,
    ProjectDiagnostic,
    ProvenanceOrdering,
    ProvenanceStatement,
    RangeAttribution,
    TraceResult,
    UnresolvedBlock,
    VariableEffect,
    VariableProvenanceChunk,
)

_LIFECYCLE_KINDS = frozenset({"created", "modified", "dropped", "labelled"})


@dataclass(frozen=True)
class ProvenanceEvent:
    """One parser statement occurrence offered to the provenance projection."""

    range: LineRange
    attributions: tuple[RangeAttribution, ...]
    occurrence_sequence: int | None = None


def build_provenance_chunk(
    variable: str,
    lineage_variables: list[str],
    events: Iterable[ProvenanceEvent],
    *,
    ordering: ProvenanceOrdering,
    include_labels: bool,
    unresolved_blocks: Iterable[UnresolvedBlock],
    project_diagnostics: Iterable[ProjectDiagnostic],
) -> VariableProvenanceChunk:
    """Build one deterministic chunk from already-selected parser events.

    Each input event represents one physical statement occurrence. Effects are
    deduplicated within that event, while separate same-range events remain
    separate because delimiter-separated statements can share a line range.
    """
    lineage_set = set(lineage_variables)
    statements: list[ProvenanceStatement] = []
    variables_with_ranges: set[str] = set()

    for event in events:
        effects: list[VariableEffect] = []
        seen_effects: set[tuple[str, str]] = set()
        for attribution in event.attributions:
            kind = attribution.kind
            if kind not in _LIFECYCLE_KINDS:
                continue
            if kind == "labelled" and not include_labels:
                continue
            if attribution.variable not in lineage_set:
                continue
            key = (attribution.variable, kind)
            if key in seen_effects:
                continue
            seen_effects.add(key)
            effects.append(
                VariableEffect(
                    variable=attribution.variable,
                    kind=cast(LifecycleKind, kind),
                )
            )
            variables_with_ranges.add(attribution.variable)
        if effects:
            statements.append(
                ProvenanceStatement(
                    range=event.range,
                    effects=effects,
                    occurrence_sequence=event.occurrence_sequence,
                )
            )

    return VariableProvenanceChunk(
        variable=variable,
        lineage_variables=list(lineage_variables),
        ordering=ordering,
        statements=statements,
        text=_render_text(statements),
        lineage_variables_without_ranges=[
            name for name in lineage_variables if name not in variables_with_ranges
        ],
        unresolved_blocks=list(unresolved_blocks),
        project_diagnostics=list(project_diagnostics),
    )


def _render_text(statements: Iterable[ProvenanceStatement]) -> str:
    """Render statements as marked, contiguous Stata source text."""
    groups: list[str] = []
    for statement in statements:
        line_range = statement.range
        range_text = _range_text(line_range)
        effects_text = ", ".join(
            f"{effect.variable}:{effect.kind}" for effect in statement.effects
        )
        header = f"* [{line_range.source}:{range_text} | {effects_text}"
        if statement.occurrence_sequence is not None:
            header += f" | occurrence:{statement.occurrence_sequence}"
        header += "]"
        groups.append("\n".join([header, *line_range.source_lines]))
    return "\n\n".join(groups)


def _range_text(line_range: LineRange) -> str:
    if line_range.start_line == line_range.end_line:
        return str(line_range.start_line)
    return f"{line_range.start_line}-{line_range.end_line}"


def render_markdown(result: TraceResult) -> str:
    """Render a ``TraceResult`` as a deterministic provenance document."""
    chunk = result.provenance_chunk
    if chunk is None:
        # This is only reachable for a caller validating old persisted JSON;
        # tracing entry points always populate the additive field.
        chunk = _legacy_chunk(result)

    lines = [
        f"# Variable provenance: {_escape_text(chunk.variable)}",
        "",
        "Resolved lineage slice. Standalone Stata execution is not assessed.",
        f"Ordering: {_ordering_text(chunk.ordering)}.",
        "",
        f"Target variable: `{_escape_text(chunk.variable)}`",
        f"Resolved ancestor variables: {_names_text(chunk.lineage_variables[1:])}",
        f"Lineage variables: {_names_text(chunk.lineage_variables)}",
        "Lineage variables without lifecycle ranges:",
    ]
    if chunk.ordering == "per_source":
        lines.insert(
            4,
            "Warning: no global execution sequence is known for this input.",
        )
    if chunk.lineage_variables_without_ranges:
        lines.extend(
            f"- `{_escape_text(name)}`"
            for name in chunk.lineage_variables_without_ranges
        )
    else:
        lines.append("- None")

    lines.extend(["", "## Resolved lineage code", ""])
    rendered_text = _render_text(chunk.statements)
    if rendered_text:
        fence = _fence_for([rendered_text])
        lines.extend([f"{fence}stata", rendered_text, fence])
    else:
        lines.append("No selected lifecycle statements were resolved.")

    lines.extend(["", "## Potential replication context", ""])
    context_records = _context_markdown(chunk)
    if context_records:
        lines.extend(context_records)
    else:
        lines.append("No unresolved blocks or project diagnostics were recorded.")
    return "\n".join(lines)


def _legacy_chunk(result: TraceResult) -> VariableProvenanceChunk:
    """Project legacy fields into a best-effort display-only chunk."""
    lineage = [result.variable, *result.ancestors]
    events = [
        ProvenanceEvent(
            range=attribution.range,
            attributions=(attribution,),
        )
        for attribution in result.attributed_ranges
        if attribution.variable in lineage and attribution.kind != "referenced"
    ]
    return build_provenance_chunk(
        result.variable,
        lineage,
        events,
        ordering="execution",
        include_labels=True,
        unresolved_blocks=result.unresolved_blocks,
        project_diagnostics=result.project_diagnostics,
    )


def _ordering_text(ordering: ProvenanceOrdering) -> str:
    return "execution order" if ordering == "execution" else "per-source order"


def _names_text(names: list[str]) -> str:
    return ", ".join(f"`{_escape_text(name)}`" for name in names) if names else "none"


def _context_markdown(chunk: VariableProvenanceChunk) -> list[str]:
    lines: list[str] = []
    for index, block in enumerate(chunk.unresolved_blocks, start=1):
        lines.extend(
            _record_markdown(
                f"Unresolved block {index}",
                [
                    ("Reason", block.reason),
                    ("Source range", _range_text_with_source(block.range)),
                    ("Context", _json_text(block.context)),
                    ("Statement", block.statement or "(none)"),
                    ("Source lines", "\n".join(block.range.source_lines)),
                ],
            )
        )
    offset = len(chunk.unresolved_blocks)
    for index, diagnostic in enumerate(chunk.project_diagnostics, start=1):
        details = [
            ("Code", diagnostic.code),
            ("Message", diagnostic.message or "(none)"),
            ("Source", diagnostic.source or "(none)"),
            ("Variable", diagnostic.variable or "(none)"),
            ("Candidate sources", _json_text(diagnostic.candidate_sources)),
            ("Context", _json_text(diagnostic.context)),
        ]
        if diagnostic.range is not None:
            details.insert(2, ("Source range", _range_text_with_source(diagnostic.range)))
        lines.extend(_record_markdown(f"Project diagnostic {offset + index}", details))
    return lines


def _record_markdown(title: str, details: list[tuple[str, str]]) -> list[str]:
    lines = [f"### {title}", ""]
    for label, value in details:
        if "\n" not in value:
            lines.append(f"{label}: {_escape_text(value)}")
            continue
        fence = _fence_for([value])
        lines.extend([f"{label}:", f"{fence}text", value, fence])
    lines.append("")
    return lines


def _range_text_with_source(line_range: LineRange) -> str:
    return f"{line_range.source}:{_range_text(line_range)}"


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _fence_for(values: Iterable[str]) -> str:
    longest = 0
    for value in values:
        current = 0
        for character in value:
            if character == "`":
                current += 1
                longest = max(longest, current)
            else:
                current = 0
    return "`" * max(3, longest + 1)


def _escape_text(value: str) -> str:
    """Escape inline Markdown hazards without changing multiline source blocks."""
    return value.replace("\\", "\\\\").replace("`", "\\`").replace("\r", "\\r").replace(
        "\n", "\\n"
    )


__all__ = [
    "ProvenanceEvent",
    "build_provenance_chunk",
    "render_markdown",
]

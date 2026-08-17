"""Reusable no-dropped-lines invariant assertion.

AGENTS.md section 3.1: every non-blank, non-comment line in a parsed file must
end up in exactly one of two places: attributed to a variable, or recorded in
``unresolved_blocks``. Silent absence is the worst failure of this tool.

The three quantities compared here are derived independently from *different*
sources:

- executable lines: from the scanner (physical lines with code characters),
  scanned per source file;
- attributed lines: recomputed from the ``RangeAttribution`` contract records;
- unresolved lines: recomputed from the ``UnresolvedBlock`` contract records.

Because the attributed/unresolved sets are derived from the persisted contract
objects (not from parser bookkeeping that is updated in the same code paths),
a regression that writes wrong ranges while updating bookkeeping consistently
would still be caught. In an include graph, every traversed file is checked
individually and coverage is keyed by ``(source, line)`` so physical line
numbers across files do not collide.
"""

from __future__ import annotations

from pathlib import Path

from do2screen.parser import Parser
from do2screen.registry import RegistryAdapter
from do2screen.scanner import scan
from do2screen.trace import coverage_of
from tests.mock_registry import MockStataRegistry


def parse_fixture(path: str | Path):
    """Parse a do file with the mock registry; return (scan, parsed_graph)."""
    text = Path(path).read_text(encoding="utf-8")
    scanned = scan(text)
    registry = RegistryAdapter(module=MockStataRegistry())
    parser = Parser(registry)
    graph = parser.parse_graph(str(path))
    return scanned, graph


def _executable_for(path: str | Path) -> set[int]:
    text = Path(path).read_text(encoding="utf-8")
    return {line.line_no for line in scan(text).lines if line.has_code()}


def attributed_lines_from_records(graph) -> set[int]:
    return {
        ln
        for att in graph.attributions
        for ln in range(att.range.start_line, att.range.end_line + 1)
    }


def unresolved_lines_from_records(graph) -> set[int]:
    return {
        ln
        for block in graph.unresolved
        for ln in range(block.range.start_line, block.range.end_line + 1)
    }


def assert_no_dropped_lines(path: str | Path):
    """Assert the no-dropped-lines invariant for a fixture and its includes."""
    registry = RegistryAdapter(module=MockStataRegistry())
    graph = Parser(registry).parse_graph(str(path))

    # Per-source checks: every traversed file's executable set equals its
    # terminal set and the two terminal dispositions never overlap.
    assert graph.files, "parser produced no source records"
    for f in graph.files:
        executable = _executable_for(f.path)
        attributed = {
            ln
            for att in f.attributions
            for ln in range(att.range.start_line, att.range.end_line + 1)
        }
        unresolved = {
            ln
            for block in f.unresolved
            for ln in range(block.range.start_line, block.range.end_line + 1)
        }
        terminal = (attributed | unresolved) & executable
        assert terminal == executable, (
            f"{f.path}: no-dropped-lines violated. "
            f"executable={sorted(executable)} "
            f"terminal={sorted(terminal)}"
        )
        overlap = (attributed & unresolved) & executable
        assert not overlap, f"{f.path}: overlapping terminal lines {sorted(overlap)}"
    return graph


def assert_coverage_match(path: str | Path) -> None:
    """Assert graph coverage equals direct attributed/executable (source, line)
    counts computed independently."""
    registry = RegistryAdapter(module=MockStataRegistry())
    graph = Parser(registry).parse_graph(str(path))

    executable_pairs: set[tuple[str, int]] = set()
    for f in graph.files:
        for ln in _executable_for(f.path):
            executable_pairs.add((f.path, ln))
    covered_pairs: set[tuple[str, int]] = set()
    for att in graph.attributions:
        for ln in range(att.range.start_line, att.range.end_line + 1):
            covered_pairs.add((att.range.source, ln))

    if not executable_pairs:
        assert coverage_of(graph) == 1.0
        return
    expected = len(covered_pairs & executable_pairs) / len(executable_pairs)
    actual = coverage_of(graph)
    assert abs(actual - expected) < 1e-9, (
        f"{path}: coverage {actual} != expected {expected}"
    )

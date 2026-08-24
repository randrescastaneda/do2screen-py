---
date: 2026-08-22
title: "Project tracing needs physical-source records plus occurrence replay"
category: "testing-patterns"
language: "Python"
tags: [project-tracing, source-lines, include-cache, lineage, invariants]
root-cause: "Physical parsing, execution occurrences, and terminal coverage were conflated, making repeated includes and cross-file uncertainty unsafe to represent."
severity: "P1"
plan: ".cg-docs/plans/2026-08-21-project-wide-tracing-with-source-lines.md"
reviewed-in: ".cg-docs/reviews/2026-08-21-project-wide-tracing-with-source-lines-verify-review.md"
related: [".cg-docs/solutions/testing-patterns/2026-08-17-no-dropped-lines-invariant-and-source-aware-coverage.md"]
---

# Project Tracing Needs Physical-Source Records Plus Occurrence Replay

## Problem

Project-wide tracing must support ordered file lists, manifests, and unordered
directory discovery while preserving exact physical source lines. A physical
file can be included more than once, and two files can share the same physical
line number. Treating a source path as both a parse cache key and an execution
event loses repeated include occurrences; flattening line numbers loses coverage
failures; and merging parents by variable name binds redefinitions incorrectly.

## Root Cause

The parser's physical inventory and the execution semantics are different
dimensions. A canonical source should be parsed once, but its immutable events
must be replayed for every root/include occurrence. Terminal coverage is a
third dimension and must be computed from persisted attribution/unresolved
records, keyed by `(source, line)`.

## Solution

Use three explicit layers:

1. `ParsedFile` stores decoded physical lines, terminal parser records, and
   replayable events. The source cache maps one canonical path to one
   `ParsedFile`, including cached `OSError` failures.
2. `SourceOccurrence` records each root or resolved include execution with root
   order, monotonically increasing occurrence sequence, caller source/range, and
   caller sequence. Replay the cached event stream at include call sites while
   maintaining an active path stack for cycle detection.
3. Project invariant checks derive executable coordinates from the scanner and
   terminal coordinates independently from persisted `RangeAttribution` and
   `UnresolvedBlock` objects:

```python
executable = {(parsed.path, line) for line in parsed.executable_lines}
attributed = {
    (item.range.source, line)
    for item in project.attributions
    for line in range(item.range.start_line, item.range.end_line + 1)
}
unresolved = {
    (item.range.source, line)
    for item in project.unresolved
    for line in range(item.range.start_line, item.range.end_line + 1)
}
assert (attributed | unresolved) & executable == executable
assert not ((attributed & unresolved) & executable)
```

For ordered inputs, bind references to the latest active occurrence-qualified
definition node. For directory inputs, keep local edges but emit
`ProjectDiagnostic(code="cross_file_unordered")` for uncertain cross-root
references or duplicate definitions instead of selecting a path-order winner.

## Prevention

- Keep canonical physical cache records separate from occurrence execution
  records; never deduplicate occurrences by `(source, line)`.
- Carry `LineRange.source_lines` from the decoded physical source, never rebuild
  it from normalized statement text.
- Test repeated includes with one parse call and multiple occurrence records.
- Test source-aware invariants with `(source, line)` pairs, not bare line sets.
- Test ordered redefinitions, drop/recreate, future references, and cycles with
  occurrence-qualified lineage fixtures.
- Treat directory sort order as discovery determinism only, never execution
  order.

## Related

- [Source-aware no-dropped-lines invariant](2026-08-17-no-dropped-lines-invariant-and-source-aware-coverage.md)
- [Project-wide tracing plan](../../plans/2026-08-21-project-wide-tracing-with-source-lines.md)
- [Verification review](../../reviews/2026-08-21-project-wide-tracing-with-source-lines-verify-review.md)

# Output & Response Formats

The Python API returns a frozen Pydantic v2 `TraceResult`. The `do2screen` CLI
serialises the same model as one JSON document on stdout and communicates the
outcome through its exit code.

---

## TraceResult

The top-level result of tracing one variable through one source graph.

| Field | Type | Description |
|---|---|---|
| `variable` | `str` | The traced target variable |
| `ranges` | `list[LineRange]` | Lifecycle ranges of the target across all sources |
| `ancestors` | `list[str]` | Recursively resolved ancestors (empty when `follow_parents=False`) |
| `attributed_ranges` | `list[RangeAttribution]` | Complete audit inventory for all variables |
| `unresolved_blocks` | `list[UnresolvedBlock]` | Regions that could not be attributed |
| `coverage` | `float` | Fraction of executable lines covered by at least one attribution |
| `sources` | `list[SourceProvenance]` | Provenance of every traversed source, in traversal order |
| `source` | `SourceProvenance` | Provenance of the root source (the first requested source in project mode) |
| `input_mode` | `"files" \| "directory" \| "manifest" \| None` | Project input mode; `None` for legacy `trace()` |
| `project_files` | `list[str]` | Canonical accepted inputs and sources reached by includes |
| `variable_identities` | `list[VariableIdentity]` | Occurrence-qualified definition contexts |
| `manifest_path` | `str \| None` | Canonical manifest path for manifest input |
| `project_diagnostics` | `list[ProjectDiagnostic]` | Non-terminal project uncertainty and input facts |
| `provenance_chunk` | `VariableProvenanceChunk \| None` | Target-focused auditable lineage slice; defaulted for old persisted JSON |

---

## LineRange

An inclusive range of physical source lines.

| Field | Type | Description |
|---|---|---|
| `source` | `str` | Path of the source file |
| `start_line` | `int` | First physical line (1-based, inclusive) |
| `end_line` | `int` | Last physical line (1-based, inclusive) |
| `comment_start_line` | `int \| None` | First line of a preceding full-line comment |
| `comment_end_line` | `int \| None` | Last line of that preceding comment |
| `source_lines` | `list[str]` | Decoded physical lines from `start_line` through `end_line`, without terminators |

When a statement is preceded by a contiguous block of full-line comments, the
comment range is included so the consumer can display the comments alongside the
code.

`source_lines` is inclusive and ordered, so its length is
`end_line - start_line + 1`. Text is decoded as UTF-8 after removing a leading
BOM; undecodable bytes use the replacement character. The payload is physical
line text, not reconstructed statement text and not byte-for-byte source data.

---

## RangeAttribution

One attributed executable statement tied to one variable.

| Field | Type | Description |
|---|---|---|
| `range` | `LineRange` | Physical line range of the statement |
| `variable` | `str` | The variable the statement affects or references |
| `kind` | `Kind` | Lifecycle or dependency kind |

### Kind

The kind of attribution recorded for a range:

| Value | Meaning |
|---|---|
| `created` | The variable is created (e.g. `gen x = ...`) |
| `modified` | The variable is modified in place (e.g. `replace x = ...`) |
| `dropped` | The variable is removed (e.g. `drop x`) |
| `labelled` | The variable receives a label (e.g. `label variable x "..."`) |
| `referenced` | The variable is referenced in an expression but not affected; this is a dependency attribution, not a lifecycle event |

---

## VariableTrace

Everything the tracer learned about one variable.

| Field | Type | Description |
|---|---|---|
| `variable` | `str` | The variable name |
| `ranges` | `list[LineRange]` | Lifecycle line ranges in source order |
| `parents` | `list[str]` | Direct dependency variables in first-reference order |
| `ancestors` | `list[str]` | Recursively resolved ancestors |

---

## UnresolvedBlock

A region of recognized-but-unattributed code, reported explicitly rather than
silently dropped.

| Field | Type | Description |
|---|---|---|
| `range` | `LineRange` | Physical line range of the unresolved region |
| `reason` | `UnresolvedReason` | Why the code could not be attributed |
| `context` | `dict[str, str]` | Additional parser facts (e.g. include target path) |
| `statement` | `str \| None` | Raw text of the statement, when available |

### Unresolved Reasons

| Reason | Description |
|---|---|
| `macro_or_loop` | Variable name is constructed from a macro or loop index |
| `unknown_command` | The registry does not recognise the command (e.g. user-written ado) |
| `unsupported_effect` | The command's `variable_effect` is not modelled (e.g. `restructure`) |
| `unsupported_syntax` | The command is known but the specific syntax variant is not handled |
| `unresolved_include` | An `include` directive's target path could not be resolved |
| `no_variable_attribution` | The statement is syntactically valid but cannot be tied to a variable |
| `unterminated_structure` | A brace structure or block comment is not closed before end of file |

---

## SourceProvenance

Provenance metadata for one traversed source file.

| Field | Type | Description |
|---|---|---|
| `path` | `str` | Normalized filesystem path |
| `line_count` | `int` | Number of physical lines |
| `used_delimit` | `bool` | True when the source uses `#delimit ;` anywhere |
| `traversal_index` | `int` | Ordered index of first physical-source registration (0 = first registered source) |

## Project Metadata

`VariableIdentity` groups occurrence-qualified definition contexts for one
variable. Each `VariableContext` records its canonical source, first creation
line, lifecycle ranges, direct parents, and caller provenance when reached
through an include.

`ProjectDiagnostic` is separate from `UnresolvedBlock`. It may have no range
and never changes the terminal parser partition. Typical codes include
`missing_root`, `unresolved_manifest_file`, `empty_directory`,
`cross_file_unordered`, and `unbound_reference`.

All added `TraceResult` project fields are defaulted, so legacy JSON without
them remains valid. Legacy `trace()` results use `input_mode: null`, an empty
`project_files` list, no variable identities, no manifest path, and an empty
`project_diagnostics` list.

## VariableProvenanceChunk

The chunk is one human-auditable lineage slice for the requested target. It is
not a standalone executable Stata program: dataset loading, macros, control
flow, restructuring, and user-written commands may still be required.

| Field | Type | Description |
|---|---|---|
| `variable` | `str` | Requested target variable |
| `lineage_variables` | `list[str]` | Target followed by resolved ancestors in deterministic order |
| `ordering` | `"execution" \| "per_source"` | Whether statements have an execution sequence or only source-local order |
| `statements` | `list[ProvenanceStatement]` | Selected lifecycle statements, one per physical execution occurrence |
| `text` | `str` | Deterministic marked Stata source block for display |
| `lineage_variables_without_ranges` | `list[str]` | Selected lineage variables without a resolved lifecycle statement |
| `standalone_execution` | `"not_assessed"` | Explicitly records that executable completeness is not assessed |
| `unresolved_blocks` | `list[UnresolvedBlock]` | All parser uncertainty records from the traversed result |
| `project_diagnostics` | `list[ProjectDiagnostic]` | All project uncertainty and input facts from the traversed result |

`ProvenanceStatement` contains a `range`, one or more `VariableEffect` records,
and an optional `occurrence_sequence`. Effects are limited to `created`,
`modified`, `dropped`, and `labelled`; dependency-only `referenced` records are
never emitted as statements. A physical statement with multiple selected effects
appears once with all effects preserved. `text` marks each group with a Stata
comment such as `* [file.do:38 | wages:created | occurrence:1]` and joins groups
with one blank line while preserving `LineRange.source_lines` exactly.

For `trace()`, explicit file lists, and manifests, statements are selected from
the call-site execution stream. Repeated includes therefore repeat source
statements with distinct occurrence values. Directory chunks use `per_source`
ordering, retain deterministic source-local line order, and explicitly state
that no global execution sequence is known.

For ordered project inputs, definitions are occurrence-qualified and references
bind to the latest active preceding definition. A drop deactivates that
definition; a later creation starts a new context. Include bodies are replayed
at each call site, so repeated includes produce repeated lifecycle occurrences
without duplicating the physical source inventory. Directory ordering is never
used as execution order. In ordered modes, `source` is the first requested root;
in directory mode, it is the first canonical discovery input even when that
input cannot be read. This provenance field does not establish semantic order.

---

## Coverage

Coverage is the fraction of executable physical lines covered by at least one
attributed range, across all traversed sources.

```
coverage = covered_executable_lines / executable_lines
```

Key details:

- Coverage is keyed by `(source, line)` pairs, not bare line numbers. This
  prevents a fully-attributed child file from masking unattributed lines in the
  root.
- When a source has no executable lines at all (e.g. a file with only comments),
  coverage is the sentinel value `1.0`.

---

## Representative JSON Example

The following legacy result shows the contract and representative audit records;
additional `attributed_ranges` records, including dependency references, may be
present in a real result. `source_lines` is included on every displayed
`LineRange`.

```json
{
  "variable": "income",
  "ranges": [
    {
      "source": "data/clean.do",
      "start_line": 42,
      "end_line": 42,
      "comment_start_line": 40,
      "comment_end_line": 41,
      "source_lines": ["gen income = wages + transfers"]
    }
  ],
  "ancestors": ["wages", "transfers"],
  "attributed_ranges": [
    {
      "range": {
        "source": "data/clean.do",
        "start_line": 38,
        "end_line": 38,
        "comment_start_line": null,
        "comment_end_line": null,
        "source_lines": ["gen wages = 1200"]
      },
      "variable": "wages",
      "kind": "created"
    },
    {
      "range": {
        "source": "data/clean.do",
        "start_line": 39,
        "end_line": 39,
        "comment_start_line": null,
        "comment_end_line": null,
        "source_lines": ["gen transfers = 300"]
      },
      "variable": "transfers",
      "kind": "created"
    },
    {
      "range": {
        "source": "data/clean.do",
        "start_line": 42,
        "end_line": 42,
        "comment_start_line": null,
        "comment_end_line": null,
        "source_lines": ["gen income = wages + transfers"]
      },
      "variable": "income",
      "kind": "created"
    },
    {
      "range": {
        "source": "data/clean.do",
        "start_line": 45,
        "end_line": 45,
        "comment_start_line": null,
        "comment_end_line": null,
        "source_lines": ["replace income = income * 1.05"]
      },
      "variable": "income",
      "kind": "modified"
    }
  ],
  "unresolved_blocks": [],
  "coverage": 1.0,
  "sources": [
    {
      "path": "data/clean.do",
      "line_count": 60,
      "used_delimit": false,
      "traversal_index": 0
    }
  ],
  "source": {
    "path": "data/clean.do",
    "line_count": 60,
    "used_delimit": false,
    "traversal_index": 0
  },
  "input_mode": null,
  "project_files": [],
  "variable_identities": [],
  "manifest_path": null,
  "project_diagnostics": []
}
```

---

## CLI Exit Codes

| Code | Meaning |
|---|---|
| `0` | Complete or partial project result; one `TraceResult` JSON document is written to stdout |
| `1` | Unreadable legacy input, registry incompatibility, or project with no readable roots; message on stderr and no success JSON |
| `2` | Invalid invocation or manifest schema; usage message on stderr |

Project input diagnostics are serialized in `project_diagnostics` on successful
partial results. They are not emitted as stderr errors. Parser terminal
uncertainty remains in `unresolved_blocks`.

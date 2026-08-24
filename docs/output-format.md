# Output & Response Formats

The Python API returns a frozen Pydantic v2 `TraceResult`. The `do2screen` CLI
writes either that model as one JSON document or a human-readable Markdown
provenance document to stdout and communicates the outcome through its exit
code.

## Choosing an Output

JSON is the default and is the stable choice for applications, databases, and
automated pipelines:

```sh
do2screen path/to/source.do income
do2screen path/to/source.do income --format json --indent 2
```

Markdown is intended for human review, reports, issue discussions, and
downstream prompts where the resolved code and uncertainty should be visible:

```sh
do2screen path/to/source.do income --format markdown
do2screen path/to/source.do income --format markdown > income-provenance.md
```

`--indent` only affects JSON. Both formats are deterministic projections of the
same `TraceResult`; selecting Markdown does not rerun or reinterpret the parser.

In Python, consume `result.provenance_chunk` for structured integration. Use
`render_markdown(result)` when the application needs the same document produced
by the CLI:

```python
from do2screen import trace
from do2screen.provenance import render_markdown

result = trace("path/to/source.do", "income")
chunk = result.provenance_chunk
document = render_markdown(result)
```

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

Every tracing entry point populates the field, including empty and partial
results. The field remains optional in the Pydantic model solely so old persisted
JSON created before this feature continues to validate.

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
the available call-site execution stream. Explicit file lists and manifests
replay repeated includes, so source statements can repeat with distinct
occurrence values. Legacy `trace()` preserves its existing repeat/cycle terminal
behavior and does not replay a source after its first traversal. Directory chunks
use `per_source` ordering, retain deterministic source-local line order, and
explicitly state that no global execution sequence is known.

### Selection semantics

The chunk is a projection over existing parser records; it does not parse Stata
again and does not add command vocabulary.

- `lineage_variables` is `[target, *resolved_ancestors]`, preserving the same
  deterministic ancestor order as `TraceResult.ancestors`.
- Only lifecycle effects are selected. A dependency-only `referenced`
  attribution can establish ancestry but does not become a source statement by
  itself.
- The target's lifecycle statements are included, followed by lifecycle
  statements for the exact ancestor definitions reachable from the target.
- In ordered project modes, occurrence-qualified definition edges prevent an
  older, superseded same-name definition from leaking into the chunk.
- `--no-follow-parents` / `follow_parents=False` makes `lineage_variables`
  contain only the target and excludes ancestor lifecycle statements.
- Label statements are selected only with `--labels` /
  `include_labels=True`. They remain present in the complete
  `attributed_ranges` inventory regardless.
- One physical statement occurrence appears once, even if it has several
  selected effects. All selected effects are retained in `effects` and in the
  marker comment.

### Ordering and execution occurrences

`ordering` describes what the chunk can honestly claim:

| Value | Inputs | Guarantee |
|---|---|---|
| `execution` | `trace()`, explicit file lists, manifests | Statements follow the available call-site execution stream |
| `per_source` | Directory discovery | Statements are deterministic within each physical source; no cross-file execution sequence is claimed |

An ordered `ProvenanceStatement.occurrence_sequence` identifies the source
execution occurrence. All statements from the first root occurrence commonly
have `occurrence_sequence: 1`; an included child receives another sequence. In
explicit file-list and manifest modes, a child that executes again repeats with a
different sequence. `occurrence_sequence` is `null` in `per_source` chunks
because directory order is not execution order.

The number is an occurrence identifier, not a statement counter. Use
`range.source`, `range.start_line`, and `range.end_line` to locate the physical
statement.

### Marked source text

`text` is a convenience rendering of `statements`. Each statement group has:

1. A generated, valid Stata comment with source range, selected effects, and the
   occurrence identifier when known.
2. The exact decoded physical lines from `LineRange.source_lines`.
3. One blank line before the next group.

For example:

```stata
* [data/clean.do:38 | wages:created | occurrence:1]
gen wages = 1200

* [data/clean.do:42 | income:created | occurrence:1]
gen income = wages + transfers
```

Consumers that need paths, effects, or ranges should read `statements` rather
than parse marker comments. The comments are display metadata, not a secondary
machine-readable protocol.

### Missing ranges and uncertainty

`lineage_variables_without_ranges` prevents a partial lineage from looking
complete. It can contain:

- A target that has no resolved lifecycle statement.
- An external or unbound ancestor referenced by a selected definition.
- A name whose lifecycle is inside unresolved macro or control-flow code.

An empty `statements` list and empty `text` do not prove that the variable is
absent. Always evaluate these fields together:

- `lineage_variables_without_ranges`
- `unresolved_blocks`
- `project_diagnostics`

The chunk copies all top-level unresolved blocks and project diagnostics without
filtering. This intentionally provides conservative potential replication
context: a downstream user can see uncertainty even when it is not tied to one
selected lineage statement.

### Standalone execution limitation

`standalone_execution` is always `"not_assessed"`. do2screen-py reports source
structure; it does not execute Stata or prove that a slice has all runtime
prerequisites. Common omitted prerequisites include:

- Dataset loading and data state established before the selected lines.
- Local/global macros and loop values.
- Control-flow conditions.
- Dataset restructuring effects.
- User-written ado commands.
- External files whose paths cannot be resolved.

Treat `text` as an auditable code excerpt, not as a generated standalone do file.

### Markdown document layout

`--format markdown` and `render_markdown()` produce these sections:

1. `# Variable provenance: <target>`
2. Assessment: resolved lineage slice, standalone execution disclaimer, and
   ordering semantics
3. Target, resolved ancestors, complete lineage, and names without ranges
4. `## Resolved lineage code`: one contiguous fenced `stata` block containing
   the marked statements, or an explicit no-statements message
5. `## Potential replication context`: every unresolved block followed by every
   project diagnostic, or an explicit no-context message

Fences expand automatically when source text contains backtick runs, so the
document remains valid Markdown without changing source lines. Paths and other
inline values are escaped. Rendering is deterministic and offline.

### Edge-case behavior

| Case | Result |
|---|---|
| Target not found | Target appears in `lineage_variables_without_ranges`; code section is explicitly empty |
| Macro-built variable | No guessed range; unresolved block is shown under replication context |
| Unresolved include | Resolved code remains visible; include failure and source lines remain explicit |
| Label event | Excluded by default; included as `labelled` only when label tracking is enabled |
| Same physical statement has several effects | One statement with all selected effects |
| Multiline or `#delimit ;` statement | Original physical `source_lines` and inclusive range are preserved |
| Repeated include in files/manifest mode | Statement repeats with a distinct occurrence identifier |
| Repeated include in legacy `trace()` | Existing non-replay behavior is preserved; repeat terminal remains reported |
| Include cycle | Traversal terminates; terminal cycle/repeat uncertainty remains reported |
| Directory input | `per_source` ordering, no occurrence identifiers, explicit no-global-order warning |
| Superseded same-name ancestor | Ordered selection follows the reachable occurrence-qualified definition only |
| Old persisted JSON without `provenance_chunk` | Still validates; rendering derives a best-effort display from legacy fields |

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
  "project_diagnostics": [],
  "provenance_chunk": {
    "variable": "income",
    "lineage_variables": ["income", "wages", "transfers"],
    "ordering": "execution",
    "statements": [
      {
        "range": {
          "source": "data/clean.do",
          "start_line": 38,
          "end_line": 38,
          "comment_start_line": null,
          "comment_end_line": null,
          "source_lines": ["gen wages = 1200"]
        },
        "effects": [{"variable": "wages", "kind": "created"}],
        "occurrence_sequence": 1
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
        "effects": [{"variable": "transfers", "kind": "created"}],
        "occurrence_sequence": 1
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
        "effects": [{"variable": "income", "kind": "created"}],
        "occurrence_sequence": 1
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
        "effects": [{"variable": "income", "kind": "modified"}],
        "occurrence_sequence": 1
      }
    ],
    "text": "* [data/clean.do:38 | wages:created | occurrence:1]\ngen wages = 1200\n\n* [data/clean.do:39 | transfers:created | occurrence:1]\ngen transfers = 300\n\n* [data/clean.do:42 | income:created | occurrence:1]\ngen income = wages + transfers\n\n* [data/clean.do:45 | income:modified | occurrence:1]\nreplace income = income * 1.05",
    "lineage_variables_without_ranges": [],
    "standalone_execution": "not_assessed",
    "unresolved_blocks": [],
    "project_diagnostics": []
  }
}
```

## Representative Markdown Example

The same result requested with `--format markdown` is:

````markdown
# Variable provenance: income

Resolved lineage slice. Standalone Stata execution is not assessed.
Ordering: execution order.

Target variable: `income`
Resolved ancestor variables: `wages`, `transfers`
Lineage variables: `income`, `wages`, `transfers`
Lineage variables without lifecycle ranges:
- None

## Resolved lineage code

```stata
* [data/clean.do:38 | wages:created | occurrence:1]
gen wages = 1200

* [data/clean.do:39 | transfers:created | occurrence:1]
gen transfers = 300

* [data/clean.do:42 | income:created | occurrence:1]
gen income = wages + transfers

* [data/clean.do:45 | income:modified | occurrence:1]
replace income = income * 1.05
```

## Potential replication context

No unresolved blocks or project diagnostics were recorded.
````

---

## CLI Exit Codes

| Code | Meaning |
|---|---|
| `0` | Complete or partial result; one JSON or Markdown document is written to stdout |
| `1` | Unreadable legacy input, registry incompatibility, or project with no readable roots; message on stderr and no success document |
| `2` | Invalid invocation or manifest schema; usage message on stderr |

Project input diagnostics are serialized in `project_diagnostics` on successful
JSON partial results and rendered under potential replication context in
Markdown. They are not emitted as stderr errors. Parser terminal uncertainty
remains in `unresolved_blocks` and is likewise rendered in Markdown.

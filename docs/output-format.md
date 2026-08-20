# Output & Response Formats

The `trace()` function and `do2screen` CLI both return a `TraceResult` -- a
frozen Pydantic v2 model that serialises to JSON without data loss.

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
| `source` | `SourceProvenance` | Provenance of the root/target source |

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

When a statement is preceded by a contiguous block of full-line comments, the
comment range is included so the consumer can display the comments alongside the
code.

---

## RangeAttribution

One attributed executable statement tied to one variable.

| Field | Type | Description |
|---|---|---|
| `range` | `LineRange` | Physical line range of the statement |
| `variable` | `str` | The variable the statement affects or references |
| `kind` | `Kind` | Lifecycle or dependency kind |

### Kind

The lifecycle effect of an attributed range:

| Value | Meaning |
|---|---|
| `created` | The variable is created (e.g. `gen x = ...`) |
| `modified` | The variable is modified in place (e.g. `replace x = ...`) |
| `dropped` | The variable is removed (e.g. `drop x`) |
| `labelled` | The variable receives a label (e.g. `label variable x "..."`) |
| `referenced` | The variable is referenced in an expression but not affected |

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
| `unterminated_structure` | An `if`/`foreach`/`while` block is not closed before end of file |

---

## SourceProvenance

Provenance metadata for one traversed source file.

| Field | Type | Description |
|---|---|---|
| `path` | `str` | Normalized filesystem path |
| `line_count` | `int` | Number of physical lines |
| `used_delimit` | `bool` | True when the source uses `#delimit ;` anywhere |
| `traversal_index` | `int` | Ordered index in depth-first traversal (0 = root) |

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

## Full Annotated JSON Example

```json
{
  "variable": "income",
  "ranges": [
    {
      "source": "data/clean.do",
      "start_line": 42,
      "end_line": 42,
      "comment_start_line": 40,
      "comment_end_line": 41
    }
  ],
  "ancestors": ["wages", "transfers"],
  "attributed_ranges": [
    {
      "range": { "source": "data/clean.do", "start_line": 38, "end_line": 38 },
      "variable": "wages",
      "kind": "created"
    },
    {
      "range": { "source": "data/clean.do", "start_line": 39, "end_line": 39 },
      "variable": "transfers",
      "kind": "created"
    },
    {
      "range": { "source": "data/clean.do", "start_line": 42, "end_line": 42 },
      "variable": "income",
      "kind": "created"
    },
    {
      "range": { "source": "data/clean.do", "start_line": 45, "end_line": 45 },
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
  }
}
```

---

## CLI Exit Codes

| Code | Meaning |
|---|---|
| `0` | Success -- `TraceResult` JSON written to stdout |
| `1` | Unreadable file or registry incompatibility (error on stderr) |
| `2` | Invalid arguments (error on stderr) |

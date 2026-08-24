# do2screen-py

**Trace how a variable is built inside a Stata do file.**

[![License](https://img.shields.io/github/license/randrescastaneda/do2screen-py)](https://github.com/randrescastaneda/do2screen-py/blob/main/LICENSE)

---

`do2screen-py` is a Python 3.10+ library and JSON CLI that, given a Stata do file
path and a variable name, returns the physical source lines for that variable's
create, modify, and drop lifecycle events, plus the ancestor variables it depends
on, recursively. Label lifecycle events are opt-in with `--labels` or
`include_labels=True`. It is a Python reimplementation of the tracing logic in
**do2screen (Stata)**, by the same author, for environments where Stata cannot
run.

This is a **general purpose Stata tool**. It reads text and reports structure;
it is not a Stata interpreter, does not execute code, and does not reason about
data values.

---

## Core Features

<div class="grid cards" markdown>

- :material-source-branch-check: **Variable Tracing**
    ---
    Trace create, modify, and drop events for any variable across a do file; add
    label events when requested.

- :material-family-tree: **Recursive Ancestor Resolution**
    ---
    Automatically resolve all dependency variables, recursively, with cycle termination.

- :material-file-tree: **Include Graph Traversal**
    ---
    Follow `include` directives across multiple files and attribute code to the correct source.

- :material-folder-multiple: **Project Inputs**
    ---
    Trace explicit file lists, manifest V1 documents, or deterministic directory corpora.

- :material-alert-circle-outline: **Unresolved Block Reporting**
    ---
    Seven explicit categories for code the parser could not attribute -- never silently dropped.

- :material-chart-bar: **Coverage Metrics**
    ---
    Fraction of executable lines covered by at least one attribution across all traversed sources.

- :material-lock: **Deterministic & Offline**
    ---
    No network, no randomness, no environment-dependent behavior. Byte-identical output for identical input.

- :material-console: **CLI + Python API**
    ---
    Use from the command line or import `trace()` in your Python code.

- :material-puzzle-outline: **Registry Boundary**
    ---
    Command vocabulary comes from `stata-command-registry`; this package supplies grammar.

</div>

---

## Architecture Overview

The parsing pipeline processes a Stata do file through five stages:

```
Scanner → Statements → Grammar → Parser → Trace
```

1. **Scanner** -- splits the file into physical lines and masks strings,
   comments, and continuation tails without changing source offsets.
2. **Statements** -- groups lines into executable statements, handling
   `#delimit` mode switching, `///` continuation, string literals, and brace
   structure.
3. **Grammar** -- extracts generic variable targets and references from each
   statement without knowing Stata command names.
4. **Parser** -- uses the registry for command vocabulary and effects, then
   builds a `ParsedGraph` with lifecycle events, parent edges, include traversal,
   and unresolved blocks.
5. **Trace** -- projects the graph onto a single variable's `TraceResult`,
   resolving ancestors and computing coverage.

---

## Quick Example

The example fixture is available in the repository checkout, not in the
installed distribution. Replace the path with one of your own Stata files when
running the example after installation. The output below assumes a conformant
registry is installed; without it, legacy tracing still runs but statements are
reported as unresolved commands.

=== "CLI"

    ```sh
    do2screen tests/fixtures/sample.do income
    ```

=== "Python"

    ```python
    from do2screen import trace

    result = trace("tests/fixtures/sample.do", "income")
    print(result.model_dump_json(indent=2))
    ```

Given `sample.do`:

```stata
* Sample: build total income from wage and transfer components.
gen wages = 1200
gen transfers = 300
gen income = wages + transfers
rename income total_income
replace total_income = total_income * 1.05
label variable total_income "Total household income"
```

The legacy output is abbreviated below; the actual JSON also includes
`source_lines` on every `LineRange`, dependency-reference and label audit
attributions, and the defaulted project fields at the end. The output is:

```json
{
  "variable": "income",
  "ranges": [
    {
      "source": "tests/fixtures/sample.do",
      "start_line": 4,
      "end_line": 4,
      "comment_start_line": null,
      "comment_end_line": null,
      "source_lines": ["gen income = wages + transfers"]
    }
  ],
  "ancestors": [
    "wages",
    "transfers"
  ],
  "attributed_ranges": [
    {
      "range": {
        "source": "...",
        "start_line": 2,
        "end_line": 2,
        "comment_start_line": 1,
        "comment_end_line": 1,
        "source_lines": ["gen wages = 1200"]
      },
      "variable": "wages",
      "kind": "created"
    },
    {
      "range": {
        "source": "...",
        "start_line": 3,
        "end_line": 3,
        "comment_start_line": null,
        "comment_end_line": null,
        "source_lines": ["gen transfers = 300"]
      },
      "variable": "transfers",
      "kind": "created"
    },
    {
      "range": {
        "source": "...",
        "start_line": 4,
        "end_line": 4,
        "comment_start_line": null,
        "comment_end_line": null,
        "source_lines": ["gen income = wages + transfers"]
      },
      "variable": "income",
      "kind": "created"
    },
    {
      "range": {
        "source": "...",
        "start_line": 5,
        "end_line": 5,
        "comment_start_line": null,
        "comment_end_line": null,
        "source_lines": ["rename income total_income"]
      },
      "variable": "total_income",
      "kind": "created"
    },
    {
      "range": {
        "source": "...",
        "start_line": 6,
        "end_line": 6,
        "comment_start_line": null,
        "comment_end_line": null,
        "source_lines": ["replace total_income = total_income * 1.05"]
      },
      "variable": "total_income",
      "kind": "modified"
    }
  ],
  "unresolved_blocks": [],
  "coverage": 1.0,
  "sources": [
    {
      "path": "tests/fixtures/sample.do",
      "line_count": 7,
      "used_delimit": false,
      "traversal_index": 0
    }
  ],
  "source": {
    "path": "tests/fixtures/sample.do",
    "line_count": 7,
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

Project results add `input_mode`, `project_files`, `variable_identities`,
`manifest_path`, and `project_diagnostics`. `project_diagnostics` is a
non-terminal JSON channel for missing inputs and unordered cross-file
ambiguity; parser uncertainty remains in `unresolved_blocks`.

---

## What do2screen-py is not

- It is **not** a Stata interpreter. It does not execute code, evaluate
  expressions, or reason about data values.
- It is **not** a semantic analyser. It does not explain what a transformation
  *means*.
- It knows **nothing** about survey harmonization, poverty measurement, or any
  specific variable name.

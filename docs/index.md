# do2screen-py

**Trace how a variable is built inside a Stata do file.**

[![PyPI version](https://img.shields.io/pypi/v/do2screen-py)](https://pypi.org/project/do2screen-py/)
[![Python version](https://img.shields.io/pypi/pyversions/do2screen-py)](https://pypi.org/project/do2screen-py/)
[![License](https://img.shields.io/pypi/l/do2screen-py)](https://github.com/randrescastaneda/do2screen-py/blob/main/LICENSE)

---

`do2screen-py` is a Python 3.10+ library and JSON CLI that, given a Stata do file
path and a variable name, returns the physical source lines that create, modify,
drop, or label that variable, plus the ancestor variables it depends on,
recursively. It is a Python reimplementation of the tracing logic in
**do2screen (Stata)**, by the same author, for environments where Stata cannot
run.

This is a **general purpose Stata tool**. It reads text and reports structure;
it is not a Stata interpreter, does not execute code, and does not reason about
data values.

---

## Core Features

<div class="grid cards" markdown>

- :material-variable-tree: **Variable Tracing**
    ---
    Trace create, modify, drop, and label events for any variable across a do file.

- :material-family-tree: **Recursive Ancestor Resolution**
    ---
    Automatically resolve all dependency variables, recursively, with cycle termination.

- :material-file-tree: **Include Graph Traversal**
    ---
    Follow `include` directives across multiple files and attribute code to the correct source.

- :material-alert-circle-outline: **Unresolved Block Reporting**
    ---
    Seven explicit categories for code the parser could not attribute -- never silently dropped.

- :material-chart-bar: **Coverage Metrics**
    ---
    Fraction of executable lines attributed to any variable across all traversed sources.

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

The parsing pipeline processes a Stata do file through four stages:

```
Scanner → Statements → Grammar → Parser → Trace
```

1. **Scanner** -- splits the file into physical lines, handling `#delimit ;` mode
   switching and `///` continuation.
2. **Statements** -- groups lines into executable statements, respecting
   delimiters and string literals.
3. **Grammar** -- classifies each statement using the registry: creates,
   modifies, renames, removes, labels, or restructures the dataset.
4. **Parser** -- builds a `ParsedGraph` with lifecycle events, parent edges,
   include traversal, and unresolved blocks.
5. **Trace** -- projects the graph onto a single variable's `TraceResult`,
   resolving ancestors and computing coverage.

---

## Quick Example

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

The output is:

```json
{
  "variable": "income",
  "ranges": [
    {
      "source": "tests/fixtures/sample.do",
      "start_line": 4,
      "end_line": 4,
      "comment_start_line": 1,
      "comment_end_line": 1
    }
  ],
  "ancestors": [
    "wages",
    "transfers"
  ],
  "attributed_ranges": [
    {
      "range": { "source": "...", "start_line": 2, "end_line": 2 },
      "variable": "wages",
      "kind": "created"
    },
    {
      "range": { "source": "...", "start_line": 3, "end_line": 3 },
      "variable": "transfers",
      "kind": "created"
    },
    {
      "range": { "source": "...", "start_line": 4, "end_line": 4 },
      "variable": "income",
      "kind": "created"
    },
    {
      "range": { "source": "...", "start_line": 5, "end_line": 5 },
      "variable": "income",
      "kind": "created"
    },
    {
      "range": { "source": "...", "start_line": 6, "end_line": 6 },
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
  }
}
```

---

## What do2screen-py is not

- It is **not** a Stata interpreter. It does not execute code, evaluate
  expressions, or reason about data values.
- It is **not** a semantic analyser. It does not explain what a transformation
  *means*.
- It knows **nothing** about survey harmonization, poverty measurement, or any
  specific variable name.

# do2screen-py

Trace how a variable is built inside a Stata do file.

`do2screen-py` (PyPI distribution name; import name `do2screen`) is a Python
3.10+ library and JSON CLI that, given a do file path and a variable name,
returns the physical source lines that create, modify, drop, or label that
variable, plus the ancestor variables it depends on, recursively. It is a
Python reimplementation of the tracing logic in **do2screen (Stata)**, by the
same author, for environments where Stata cannot run.

This is a **general purpose Stata tool**. It reads text and reports structure;
it is not a Stata interpreter, does not execute code, and does not reason about
data values.

## Installation

```sh
pip install do2screen-py
```

The package installs and runs without `stata-command-registry`. Optional extras:

```sh
pip install "do2screen-py[test]"       # pytest
pip install "do2screen-py[dev]"        # build + pytest
pip install "do2screen-py[registry]"   # latest upstream registry from GitHub main
```

> **Note on the `[registry]` extra**: it installs the latest available commit on
> `main` from the upstream `stata-command-registry` repository at install time.
> Run `pip install --upgrade --no-cache-dir "do2screen-py[registry]"` to refresh
> an existing environment. The base install remains usable without the registry;
> commands that cannot be resolved are classified as `unknown_command` unresolved
> blocks rather than being dropped.

## Command line

```sh
do2screen PATH VARIABLE [--no-follow-parents] [--labels] [--indent N]
```

Writes exactly one `TraceResult` JSON document to stdout. Diagnostics go to
stderr. Exit codes: `0` success, `1` unreadable file or registry
incompatibility, `2` invalid arguments.

```sh
do2screen data/clean.do income
do2screen data/clean.do income --no-follow-parents --indent 4
```

## API

```python
from do2screen import trace

result = trace("data/clean.do", "income")
result.model_dump()
```

`trace(path, variable, follow_parents=True, include_labels=False)` returns a
frozen Pydantic v2 `TraceResult`. The same input and installed registry revision
always produce byte-identical output; installation or upgrade is the point at
which the optional GitHub dependency is refreshed. Runtime tracing performs no
network calls, randomness, or environment-dependent lookups.

## What the result contains

- `ranges` — lifecycle line ranges of the traced variable (created, modified,
  dropped, labelled) across the root file and its includes.
- `ancestors` — recursively resolved dependency variables.
- `attributed_ranges` — the complete audit inventory (lifecycle *and*
  dependency references) for all variables in all traversed sources.
- `unresolved_blocks` — regions the parser recognized but could not attribute,
  reported explicitly rather than dropped. Reasons: `macro_or_loop`,
  `unknown_command`, `unsupported_effect`, `unsupported_syntax`,
  `unresolved_include`, `no_variable_attribution`, `unterminated_structure`.
- `coverage` — fraction of executable physical lines attributed to a variable
  across all traversed sources (sentinel `1.0` when there are no executable
  lines at all).
- `sources` / `source` — provenance (path, line count, `#delimit` usage,
  traversal order) per traversed file.

## Registry boundary

Command vocabulary comes from the upstream `stata-command-registry` repository
(installed distribution name `stata-registry`, import name `stata_registry`).
The optional `[registry]` extra tracks `main` and resolves its latest available
commit when installed or upgraded. The registry answers *what a word is*
(command, prefix, variable effect, include driver); this package answers *what
the shape of the text is*. When the registry is absent, the package still parses
and reports every statement, classifying commands it cannot resolve as unresolved
blocks; nothing is silently dropped.

## Known limitations

- Static structural tracer only: no macro expansion, condition evaluation, or
  data-dependent wildcard resolution. Macro-built variable targets are
  reported as `macro_or_loop` unresolved blocks rather than guessed.
- User-written `ado` programs are reported as `unknown_command` unresolved
  blocks.
- do2screen (Stata)'s `find` and `range` modes are out of scope.
- Delimiter/continuation output reports physical source lines; do2screen
  (Stata) reports transformed parser-record lines there by design.

## Development

```sh
uv pip install -e ".[dev]"   # (or pip)
pytest
python -m build
```

See `.cg-docs/plans/2026-08-17-do2screen-py-parser-pipeline.md` for the
implementation plan and `AGENTS.md` for the hard invariants this package
guarantees.

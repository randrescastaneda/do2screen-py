# do2screen-py

Trace how a variable is built inside a Stata do file.

`do2screen-py` (PyPI distribution name; import name `do2screen`) is a Python
3.10+ library and JSON/Markdown CLI that, given a do file path and a variable name,
returns the physical source lines for the variable's create, modify, drop, and
label lifecycle events, plus the ancestor variables it depends on, recursively.
Label events are opt-in. It is a Python reimplementation of the tracing logic
in **do2screen (Stata)**, by the same author, for environments where Stata
cannot run.

This is a **general purpose Stata tool**. It reads text and reports structure;
it is not a Stata interpreter, does not execute code, and does not reason about
data values.

## Installation

Install the published package from PyPI:

```sh
python -m pip install do2screen-py
```

The package installs and runs without `stata-command-registry`. To develop from
a checkout:

```sh
pip install -e ".[test]"                 # pytest
pip install -e ".[dev]"                  # build, pytest, Ruff, and Twine
pip install -e ".[docs]"                 # MkDocs website dependencies
```

Until `stata-registry` is available on PyPI, install it separately from its
source repository when full command attribution or project tracing is needed:

```sh
python -m pip install "stata-registry @ git+https://github.com/randrescastaneda/stata-command-registry.git@main"
```

The base install remains usable without the registry; commands that cannot be
resolved are classified as `unknown_command` unresolved blocks rather than
being dropped. Project APIs require a conformant `stata-registry>=0.4.0`
source-driver capability and fail explicitly when it is unavailable.

## Command line

```sh
do2screen PATH VARIABLE [--no-follow-parents] [--labels] [--format {json,markdown}] [--indent N]
```

Project tracing uses one of these exact forms:

```sh
do2screen --variable VARIABLE --dir DIR [--recursive]
do2screen --variable VARIABLE --files FILE [FILE ...]
do2screen --variable VARIABLE --manifest MANIFEST
```

Directory discovery is deterministic but unordered. Explicit file lists and
manifest entries define execution order. Project diagnostics such as missing
inputs and `cross_file_unordered` are included in successful JSON results.

Writes exactly one `TraceResult` JSON document to stdout on success by default.
Use `--format markdown` for a human-auditable provenance document. Exit codes:
`0` for a legacy result or a complete/partial project result, `1` for an
unreadable legacy input, project registry incompatibility, or a project with no
readable roots, and `2` for invalid invocation or manifest schema. Successful
project diagnostics are JSON fields; human-readable failures and warnings go to
stderr.

```sh
do2screen data/clean.do income             # replace with your do-file path
do2screen data/clean.do income --no-follow-parents --indent 4
do2screen data/clean.do income --format markdown
```

## API

```python
from do2screen import trace

result = trace("data/clean.do", "income")
result.model_dump()
```

`trace(path, variable, *, follow_parents=True, include_labels=False)` returns a
frozen Pydantic v2 `TraceResult`. Labels are excluded from `ranges` by default;
set `include_labels=True` to include them. The same input and installed registry
revision always produce byte-identical output; installation or upgrade is the
point at which the optional GitHub dependency is refreshed. Runtime tracing
performs no network calls, randomness, or environment-dependent lookups.

## What the result contains

- `ranges` — lifecycle line ranges of the traced variable (created, modified,
  and dropped by default; labelled when `include_labels=True`) across the root
  file and its includes.
- `ancestors` — recursively resolved dependency variables.
- `attributed_ranges` — the complete audit inventory (lifecycle *and*
  dependency references) for all variables in all traversed sources.
- `unresolved_blocks` — regions the parser recognized but could not attribute,
  reported explicitly rather than dropped. Reasons: `macro_or_loop`,
  `unknown_command`, `unsupported_effect`, `unsupported_syntax`,
  `unresolved_include`, `no_variable_attribution`, `unterminated_structure`.
- `coverage` — fraction of executable physical lines covered by at least one
  attribution across all traversed sources (sentinel `1.0` when there are no
  executable lines at all).
- `sources` / `source` — provenance (path, line count, `#delimit` usage,
  traversal order) per traversed file.
- `LineRange.source_lines` — inclusive decoded physical source lines without
  terminators. UTF-8 BOMs are removed and undecodable bytes use U+FFFD.
- `input_mode`, `project_files`, `variable_identities`, and `manifest_path` —
  project metadata, defaulted for legacy results.
- `project_diagnostics` — non-terminal project uncertainty and input facts;
  these are separate from terminal `unresolved_blocks`.
- `provenance_chunk` — one target-focused, human-auditable lineage slice. It
  contains `lineage_variables`, selected lifecycle `statements`, marked source
  `text`, and explicit `lineage_variables_without_ranges`. It also copies every
  `unresolved_blocks` and `project_diagnostics` record into potential replication
  context. The chunk is an audit slice, not a standalone executable Stata
  program; dataset loading, macros, control flow, restructuring, and user-written
  commands may still be required.

`provenance_chunk.ordering` is `execution` for `trace()`, explicit file lists,
and manifests. Repeated include occurrences receive distinct
`occurrence_sequence` values. Directory discovery uses `per_source` ordering and
explicitly warns that no global execution sequence is known; lexical discovery
order is never presented as execution order.

Manifest V1 is exactly `{"version": 1, "files": ["relative/path.do"]}`.
Unknown top-level keys, non-integer versions, non-string entries, empty arrays,
and unsupported versions are rejected. Relative entries resolve from the
manifest directory, canonical duplicates keep their first occurrence, and
include occurrences are replayed at their call sites without reparsing the
physical source.

### Markdown output

Markdown output contains `# Variable provenance: TARGET`, the standalone
execution disclaimer, lineage names, the ordering assessment, and one contiguous
fenced `stata` block under `## Resolved lineage code`. The
`## Potential replication context` section lists every unresolved block with its
reason, range, context, statement, and source lines, followed by every project
diagnostic. If no selected lifecycle statement exists, the section says so
explicitly. Structured `provenance_chunk.statements` is the source of truth for
renderers; `text` is the deterministic display form.

## Registry boundary

Command vocabulary comes from the upstream `stata-command-registry` repository
(installed distribution name `stata-registry`, import name `stata_registry`).
The registry answers *what a word is*
(command, prefix, variable effect, include driver); this package answers *what
the shape of the text is*. Legacy single-file tracing can run without the
registry and reports each unresolved command as an `unknown_command` block.
Project APIs additionally require the registry's conformant source-driver
capability so include and nested-source traversal cannot be guessed. Nothing is
silently dropped.

## Known limitations

- Static structural tracer only: no macro expansion, condition evaluation, or
  data-dependent wildcard resolution. Macro-built variable targets are
  reported as `macro_or_loop` unresolved blocks rather than guessed.
- User-written `ado` programs are reported as `unknown_command` unresolved
  blocks.
- do2screen (Stata)'s `find` and `range` modes are out of scope.
- Delimiter/continuation output reports physical source lines; do2screen
  (Stata) reports transformed parser-record lines there by design.
- No execution-order inference is performed for directory inputs. Cross-file
  references without explicit order are omitted from ancestry and reported as
  `cross_file_unordered` diagnostics.
- The parser does not evaluate macros, wildcard expansion, conditions, or data
  values. Caching is internal and parsing is currently serial.

## Development

```sh
python -m pip install -e ".[dev]"
ruff check .
pytest
python -m build
python -m twine check --strict dist/*
```

See `.cg-docs/plans/2026-08-21-project-wide-tracing-with-source-lines.md` for the
project-wide implementation plan and `AGENTS.md` for the hard invariants this
package guarantees.

Build the documentation website locally with:

```sh
uv pip install -e ".[docs]"
mkdocs build --strict
```

## Release workflow

Build and inspect both distribution formats from a clean checkout:

```sh
rm -rf build dist src/*.egg-info
python -m build
python -m twine check --strict dist/*
```

Test the release on TestPyPI before publishing it to PyPI:

```sh
python -m twine upload --repository testpypi dist/*
python -m venv /tmp/do2screen-testpypi
/tmp/do2screen-testpypi/bin/python -m pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ do2screen-py==0.1.0
/tmp/do2screen-testpypi/bin/do2screen --help
```

For a manual production upload, use an API token rather than a password:

```sh
python -m twine upload dist/*
```

The preferred production path is the GitHub Actions release workflow. Configure
the `pypi` GitHub environment as a Trusted Publisher on PyPI, then push a tag
matching `pyproject.toml`, such as `v0.1.0`. The workflow validates, publishes,
and creates the GitHub release with the wheel and source distribution attached.

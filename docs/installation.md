# Installation & Quickstart

## Requirements

- Python 3.10 or later
- pydantic v2 (installed automatically)

The legacy single-file API and CLI can run without the optional registry, but
commands then remain unresolved. Project tracing requires an installed,
conformant `stata-registry>=0.4.0` source-driver capability.

## Install from PyPI

```sh
python -m pip install do2screen-py
```

## Install from source

```sh
git clone https://github.com/randrescastaneda/do2screen-py.git
cd do2screen-py
python -m pip install .
```

## Optional extras

```sh
pip install -e ".[test]"                # pytest
pip install -e ".[dev]"                 # build, pytest, Ruff, and Twine
pip install -e ".[docs]"                # mkdocs-material + mkdocstrings
```

!!! note "About `stata-registry`"
    Until `stata-registry` is published on PyPI, install it separately with
    `python -m pip install "stata-registry @
    git+https://github.com/randrescastaneda/stata-command-registry.git@main"`.
    The base install remains usable without the
    registry; commands that cannot be resolved are classified as `unknown_command`
    unresolved blocks rather than being dropped. Project APIs require a
    conformant `stata-registry>=0.4.0` source-driver capability and fail
    explicitly when it is unavailable.

## CLI Quickstart

After installation, the `do2screen` command is available. In the legacy form,
`PATH` and `VARIABLE` are positional:

```sh
do2screen PATH VARIABLE [--no-follow-parents] [--labels] [--indent N]
```

Project inputs use an explicit, unambiguous grammar:

```sh
do2screen --variable VARIABLE --dir DIR [--recursive]
do2screen --variable VARIABLE --files FILE [FILE ...]
do2screen --variable VARIABLE --manifest MANIFEST
```

`--variable` is required with a project input flag and is not used with the
legacy positional form. `--recursive` is valid only with `--dir`.

**Arguments:**

| Argument | Description |
|---|---|
| `PATH` | Path to the Stata do file |
| `VARIABLE` | Variable name to trace |
| `--no-follow-parents` | Leave `ancestors` empty; still return the full audit inventory |
| `--labels` | Include `label variable` events in the traced ranges (excluded by default) |
| `--indent N` | JSON indentation level (default: 2) |

**Examples:**

The `data/clean.do` path below is a placeholder for one of your own Stata files.

```sh
# Basic trace
do2screen data/clean.do income  # replace with your do-file path

# Trace without ancestor resolution
do2screen data/clean.do income --no-follow-parents

# Include labels and pretty-print
do2screen data/clean.do income --labels --indent 4
```

**Exit codes:**

| Code | Meaning |
|---|---|
| `0` | Legacy result or complete/partial project result with one JSON document on stdout |
| `1` | Unreadable legacy input, project registry incompatibility, or no readable project roots |
| `2` | Invalid invocation or manifest schema |

The CLI writes exactly one `TraceResult` JSON document to stdout on successful
legacy or project tracing. A project with at least one readable root may return
partial results with input or ordering facts in `project_diagnostics`; this is
still exit code `0`. A project with no readable roots exits `1` and writes no
success JSON. Invalid invocation and invalid manifest schema exit `2`.
Diagnostics that are part of a successful result are JSON fields, not stderr
errors. Human-readable failures and warnings go to stderr.

## Python API Quickstart

```python
from do2screen import trace

result = trace("data/clean.do", "income")

# Access fields directly
print(result.variable)      # "income"
print(result.ranges)        # [LineRange(...), ...]
print(result.ancestors)     # ["wages", "transfers"]
print(result.coverage)      # 1.0

# Export as dictionary or JSON
d = result.model_dump()
j = result.model_dump_json(indent=2)
```

### `trace()` signature

```python
trace(
    path: str | os.PathLike[str],
    variable: str,
    *,
    follow_parents: bool = True,
    include_labels: bool = False,
) -> TraceResult
```

| Parameter | Default | Description |
|---|---|---|
| `path` | (required) | Path to the root Stata do file |
| `variable` | (required) | Variable name to trace |
| `follow_parents` | `True` | Resolve ancestor variables recursively |
| `include_labels` | `False` | Include `label variable` events in lifecycle ranges |

### Project API

```python
from do2screen import trace_directory, trace_files, trace_manifest

trace_files(
    files: list[str | os.PathLike[str]] | tuple[str | os.PathLike[str], ...],
    variable: str,
    *,
    follow_parents: bool = True,
    include_labels: bool = False,
) -> TraceResult

trace_directory(
    directory: str | os.PathLike[str],
    variable: str,
    *,
    recursive: bool = False,
    follow_parents: bool = True,
    include_labels: bool = False,
) -> TraceResult

trace_manifest(
    manifest_path: str | os.PathLike[str],
    variable: str,
    *,
    follow_parents: bool = True,
    include_labels: bool = False,
) -> TraceResult
```

`trace_files` and `trace_manifest` use the supplied order as execution order.
`trace_directory` discovers visible `.do` and `.ado` files in deterministic
lexical order but does not infer execution order; ambiguous cross-file lineage is
reported by `cross_file_unordered` diagnostics. Project APIs require the
conformant registry capability described above because include drivers come from
the upstream registry.

Manifest V1 is exactly:

```json
{"version": 1, "files": ["relative/path.do"]}
```

Unknown keys, non-integer versions, non-string entries, empty arrays, and
unsupported versions are rejected. Relative entries are resolved from the
manifest directory, absolute entries are canonicalized, and duplicate
canonical paths keep their first occurrence. Include occurrences are replayed at
their call sites without reparsing the physical source.

## Development Setup

```sh
git clone https://github.com/randrescastaneda/do2screen-py.git
cd do2screen-py

# Install with all dev dependencies
python -m pip install -e ".[dev]"

# Run quality checks and the test suite
ruff check .
pytest

# Build and validate both distributions
python -m build
python -m twine check --strict dist/*
```

# Installation & Quickstart

## Requirements

- Python 3.10 or later
- pydantic v2 (installed automatically)

## Install from PyPI

```sh
pip install do2screen-py
```

## Optional extras

```sh
pip install "do2screen-py[test]"       # pytest
pip install "do2screen-py[dev]"        # build + pytest
pip install "do2screen-py[docs]"       # mkdocs-material + mkdocstrings
pip install "do2screen-py[registry]"   # latest upstream registry from GitHub main
```

!!! note "About the `[registry]` extra"
    The `[registry]` extra installs the latest available commit on `main` from
    the upstream `stata-command-registry` repository at install time. Refresh an
    existing environment with `pip install --upgrade --no-cache-dir
    "do2screen-py[registry]"`. The base install remains usable without the
    registry; commands that cannot be resolved are classified as `unknown_command`
    unresolved blocks rather than being dropped. Project APIs require a
    conformant `stata-registry>=0.4.0` source-driver capability and fail
    explicitly when it is unavailable.

## CLI Quickstart

After installation, the `do2screen` command is available:

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
| `--labels` | Include label lifecycle events in the traced ranges |
| `--indent N` | JSON indentation level (default: 2) |

**Examples:**

```sh
# Basic trace
do2screen data/clean.do income

# Trace without ancestor resolution
do2screen data/clean.do income --no-follow-parents

# Include labels and pretty-print
do2screen data/clean.do income --labels --indent 4
```

**Exit codes:**

| Code | Meaning |
|---|---|
| `0` | Complete or partial project result with one JSON document on stdout |
| `1` | Unreadable legacy input, registry incompatibility, or no readable project roots |
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
`trace_directory` sorts visible `.do` and `.ado` files deterministically but
does not infer execution order; ambiguous cross-file lineage is reported by
`cross_file_unordered` diagnostics.

Manifest V1 is exactly:

```json
{"version": 1, "files": ["relative/path.do"]}
```

Unknown keys, non-integer versions, non-string entries, empty arrays, and
unsupported versions are rejected. Relative entries are resolved from the
manifest directory, absolute entries are canonicalized, and duplicate
canonical paths keep their first occurrence.

## Development Setup

```sh
git clone https://github.com/randrescastaneda/do2screen-py.git
cd do2screen-py

# Install with all dev dependencies
uv pip install -e ".[dev]"

# Run the test suite
pytest

# Build a distribution
python -m build
```

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
    unresolved blocks rather than being dropped.

## CLI Quickstart

After installation, the `do2screen` command is available:

```sh
do2screen PATH VARIABLE [--no-follow-parents] [--labels] [--indent N]
```

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
| `0` | Success |
| `1` | Unreadable file or registry incompatibility |
| `2` | Invalid arguments |

The CLI writes exactly one `TraceResult` JSON document to stdout. Diagnostics
go to stderr.

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

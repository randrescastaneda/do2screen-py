---
project-name: "do2screen-py"
team: "DECDG / GPID -- World Bank"
created: "2026-08-17"
last-reviewed: "2026-08-17"
---

# do2screen-py

## Objective

Build `do2screen-py` as a Python 3.10+ library and JSON CLI that traces how a variable is built inside a Stata do file. Given a file path and a variable name, it returns the lines that create, modify, drop, or label that variable, plus the ancestor variables it depends on, recursively. It is a Python reimplementation of the tracing logic in `do2screen (Stata)`, reporting original physical source-file line ranges rather than transformed parser-record numbering.

## Key Deliverables

- Python package `do2screen-py` (PyPI distribution), importable as `do2screen`
- JSON CLI: `do2screen PATH VARIABLE [--no-follow-parents] [--labels] [--indent N]`
- Lossless physical-line scanner and lexical masks (`scanner.py`)
- Delimiter-aware statement assembly and brace-block indexing (`statements.py`)
- Command-agnostic structural grammar and variable-token extraction (`grammar.py`)
- Narrow adapter around `stata-command-registry` (`registry.py`)
- Source graph traversal, statement classification, attribution, and invariant validation (`parser.py`)
- Dependency traversal and `TraceResult` projection (`trace.py`)
- Stable Pydantic v2 public contract (`models.py`)
- Differential testing against `do2screen (Stata)` reference implementation

## Constraints

- No dropped lines — every non-blank, non-comment line must be attributed or recorded in `unresolved_blocks`
- Deterministic and offline — no network calls, no language model calls, no randomness
- No hardcoded Stata command names — vocabulary from `stata-command-registry` dependency
- `TraceResult` is a public contract — stability required, breaking changes need major version bump
- Must achieve exact agreement with Stata original on line sets (differential testing); line ranges differ by design (physical source vs. parser-record)
- General purpose tool — no domain-specific vocabulary from downstream consumers
- Delimiter/continuation fixtures use physical source ranges in Python unit tests due to Stata's transformed parser-record numbering

## Current Focus

Set up project structure, implement core parsing pipeline, and establish differential testing.

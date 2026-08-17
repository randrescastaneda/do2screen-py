---
date: 2026-08-17
title: "do2screen-py core parsing pipeline"
status: completed
completed-date: 2026-08-17
scope: "Deep"
brainstorm: null
language: "Python"
estimated-effort: "large"
deviation-policy: "ask"
artifact-schema-version: 1
tags: [parser, stata, tracing, pydantic, cli]
execution-plan: .kilo/plans/1786843909688-do2screen-py-parser.md
execution-report: .cg-docs/work-reports/2026-08-17-do2screen-py-parser-pipeline.md
phases: 4
completed-phases: [1, 2, 3, 4]
---

# Plan: do2screen-py Core Parsing Pipeline

Build do2screen-py from scratch as a Python 3.10+ library and JSON CLI that
traces variable construction inside Stata do files, reporting physical source
line ranges. Derived from the detailed implementation plan at
`.kilo/plans/1786843909688-do2screen-py-parser.md`.

## Objective

Implement the full parsing pipeline (scanner, statement assembly, grammar,
parser, trace, CLI), establish the stable Pydantic v2 public contract, and
create a comprehensive test suite including the no-dropped-lines invariant and
differential testing scaffolding.

## Context

- PyPI distribution: `do2screen-py`; import name: `do2screen`
- Downstream requires `python>=3.10`, `pydantic>=2,<3`, `stata-command-registry`
- Entry point: `trace(path, variable, follow_parents=True, include_labels=False) -> TraceResult`
- No source code exists yet — greenfield implementation
- Upstream `stata-command-registry` needs `variable_effect` extension (external prerequisite)
- AGENTS.md hard invariants are non-negotiable

## Requirements

| ID | Requirement | Source |
|----|-------------|--------|
| R1 | Installable Python package with `do2screen` import and `do2screen` CLI | charter §deliverables |
| R2 | Frozen Pydantic v2 models: `TraceResult`, `VariableTrace`, `LineRange`, `UnresolvedBlock`, `SourceProvenance`, `RangeAttribution` | plan §stable JSON contract |
| R3 | Lossless physical-line scanner with code masks covering all comment/string forms | AGENTS.md §3.1-3.2, plan §lexing |
| R4 | Delimiter-aware statement assembly (`#delimit ;`, `///` continuation, brace blocks) | plan §lexing |
| R5 | Command-agnostic grammar: assignment, `gen()` option, pairs, varlists, labels, drops | plan §classification |
| R6 | Registry adapter with `variable_effect` lookup and clean failure on missing API | AGENTS.md §3.4, plan §upstream |
| R7 | Recursive source graph traversal with cycle detection and include resolution | plan §trace |
| R8 | Dependency traversal producing `VariableTrace` with ancestors | plan §trace |
| R9 | JSON CLI: `do2screen PATH VARIABLE [--no-follow-parents] [--labels] [--indent N]` | charter §deliverables |
| R10 | No-dropped-lines invariant: every executable line attributed or in `unresolved_blocks` | AGENTS.md §3.1 |
| R11 | All unresolved block categories covered: `macro_or_loop`, `unknown_command`, `unsupported_effect`, `unsupported_syntax`, `unresolved_include`, `no_variable_attribution`, `unterminated_structure` | AGENTS.md §3.2 |
| R12 | Golden file fixtures and differential testing scaffolding | AGENTS.md §5.1-5.2 |

> **R11 enum rationale**: AGENTS.md §3.2 lists four conceptual cases. The plan extends to seven `reason` values. Justification for each addition beyond the charter's four:
> - `unsupported_syntax`: distinct from `unsupported_effect` — the command is recognized and its effect is known (e.g., `creates`), but the local grammar cannot determine the variable's structural position. Folding into `unsupported_effect` would conflate "command not modeled" with "shape not parseable."
> - `no_variable_attribution`: distinct from `unsupported_effect` — the command is recognized with a modeled effect, but the statement has no extractable variable target (e.g., `drop _all`, or a command whose effect is `modifies` but the target is a macro). This is a parser outcome, not a registry gap.
> - `unterminated_structure`: distinct because it spans a *range* (from the opening delimiter/brace/comment to EOF), not a single statement. It represents a structural failure in the file, not an attribution failure.
>
> These become semver-locked public contract values once shipped (AGENTS.md §3.5). They are confirmed as desired before implementation.

## Implementation Steps

## Phase 1: Foundation

### 1. Project scaffolding and pyproject.toml
- **Requirements**: R1
- **Files**: `pyproject.toml`, `src/do2screen/__init__.py`, `src/do2screen/py.typed`
- **Details**: Create `pyproject.toml` with setuptools, python `>=3.10`, runtime deps (`pydantic>=2,<3`), optional test deps (`pytest`), console script `do2screen = do2screen.cli:main`, src layout. **`stata-command-registry` is an optional dependency** (declared under `[project.optional-dependencies]` as `registry`) because it is not yet published to PyPI under the required distribution name. The package must install and all unit tests must run without the registry present. Create `__init__.py` exporting `trace`, `TraceResult`, and documented public submodels. Add `py.typed` marker.
- **Test Scenarios**: editable install succeeds; `import do2screen` loads; `do2screen --help` runs; install works WITHOUT `stata-command-registry`
- **Tests**: `pip install -e . && python -c "import do2screen"` (no registry in env)
- **Acceptance criteria**: Package installs without registry, import works, CLI entrypoint resolves

### 2. Pydantic v2 public contract (models.py)
- **Requirements**: R2
- **Files**: `src/do2screen/models.py`
- **Details**: Implement frozen Pydantic v2 models with JSON-lossless primitives. `SourceProvenance`: path (str), line_count, used_delimit, source traversal index. `LineRange`: source (str), start_line, end_line, optional comment_start_line/comment_end_line. `RangeAttribution`: range, variable, kind (created/modified/dropped/labelled/referenced). `VariableTrace`: variable, ranges, parents, ancestors. `UnresolvedBlock`: range, reason (7 enum values), context, optional statement text. `TraceResult`: variable, ranges, ancestors, attributed_ranges, unresolved_blocks, coverage, sources, source. Paths serialized as normalized strings, never `Path`. Round-trip guarantee: `model_dump_json()` / `model_validate_json()`.
- **Test Scenarios**: model construction; JSON round-trip; field validation; enum values
- **Tests**: `tests/test_models.py`
- **Acceptance criteria**: `TraceResult` round-trips through JSON without loss

### 3. Registry adapter (registry.py)
- **Requirements**: R6
- **Files**: `src/do2screen/registry.py`, `tests/test_registry.py`, `tests/test_registry_conformance.py`
- **Details**: Narrow adapter around the upstream `stata_registry` import. The adapter is written against a **contract** to be delivered by upstream — the required API surface is:
  - `canonical_command(token: str) -> str | None` — resolve abbreviation to canonical name
  - `is_prefix(token: str) -> bool` — whether token is a bysort/bysort-style prefix
  - `variable_effect(command: str) -> str` — return one of `creates`, `modifies`, `renames`, `removes`, `labels`, `restructures`, `none`
  
  These methods are listed explicitly as the contract handed to the registry maintainer. If `stata_registry` is not importable (package absent) or lacks any required method, the adapter raises `RegistryIncompatibilityError` with version info at runtime — never at import time. This lets the package install and run all non-registry-dependent tests. Include a **conformance test** (`test_registry_conformance.py`) that runs once the registry is available (`pip install -e ".[registry]"`), verifying the actual API matches the contract. Stub tests use a mock registry when the real one is absent. No local command-name vocabulary.
- **Test Scenarios**: resolve known commands; resolve abbreviations; handle unknown tokens; clean failure on missing API; conformance test passes when registry installed
- **Tests**: `tests/test_registry.py` (mock-based), `tests/test_registry_conformance.py` (skips when registry absent)
- **Acceptance criteria**: Adapter works against available registry or fails with clear error; conformance test validates real API when present

## Phase 2: Parsing Pipeline

### 4. Physical-line scanner (scanner.py)
- **Requirements**: R3, R10
- **Files**: `src/do2screen/scanner.py`
- **Details**: Read files as UTF-8 with `utf-8-sig` encoding (strips leading BOM common in Windows-authored do files) preserving physical line numbers. Use a deterministic error policy: `errors="replace"` with a stderr diagnostic so undecodable bytes never crash the CLI. Build character-state scanner emitting per-line text plus same-length code mask. Track: standard strings (`"..."`), **compound strings (`` `"…"' `` — open: backtick+double-quote, close: double-quote+apostrophe)**, line comments (`*` at statement start, `//`), `///` continuation, inline/multiline `/* ... */` comments. Mark comment and string content non-code while preserving offsets. Emit `ScannedLine(text, code_mask, line_no)`. Correctly handle compound quotes containing embedded `"`, `'`, `` ` ``, `//`, `*`, `/*` — these must not break string/comment masking.
- **Test Scenarios**: all comment forms; string literals; compound quotes with embedded delimiters/comments/unmatched quotes; nested comments; mixed lines; continuation markers; BOM-stripped file; undecodable bytes
- **Tests**: `tests/test_scanner.py`
- **Acceptance criteria**: Code masks correctly identify code vs non-code regions for every comment/string combination in AGENTS.md §5.2, including compound-quote edge cases

### 5. Statement assembly (statements.py)
- **Requirements**: R4
- **Files**: `src/do2screen/statements.py`
- **Details**: Parse `#delimit` with local structural grammar, switching delimiter mode after its own statement completes. Handle all three forms: `#delimit ;` (semicolon mode), `#delimit cr` (return to carriage-return mode), and `#delimit clear` (reset to default CR mode). Treat `///` as continuation only in active code outside string/comment. Emit `Statement` with raw code, code mask, physical line span, member line set, preceding full-line comment range, delimiter mode, enclosing brace-block stack. Index balanced braces from code-mask. Unterminated blocks produce `unterminated_structure` through EOF. Dynamically constructed variable inside braced block produces unresolved block covering entire block.
- **Test Scenarios**: CR-terminated statements; semicolon-delimited blocks; `///` continuation; `#delimit ;` / `cr` / `clear` switching; file cycling through multiple mode changes; nested braces; unterminated blocks
- **Tests**: `tests/test_statements.py`
- **Acceptance criteria**: Statements correctly assembled with accurate physical line spans in all delimiter modes

### 6. Command-agnostic grammar (grammar.py)
- **Requirements**: R5, R10
- **Files**: `src/do2screen/grammar.py`
- **Details**: Extract first token with local lexical grammar, resolve through registry, strip prefixes. Implement generic shapes from code mask: assignment (LHS before top-level `=`), `gen(identifier)` option, simple ordered pairs, parenthesized paired varlists, plain varlist, label target, drop/remove varlist. Exclude tokens inside strings/comments, numeric literals, function names in call position, qualifiers (`if`/`in`), factor/time-series prefixes from parent candidates. Normalize variable references by removing structural prefixes. Deduplicate parents in first-seen order. Detect macro references structurally without expanding.
- **Test Scenarios**: assignment extraction; `gen()` option; varlist pairs; string exclusion; qualifier exclusion; macro detection; factor prefix stripping
- **Tests**: `tests/test_grammar.py`
- **Acceptance criteria**: All generic shapes correctly extract variable tokens and dependencies

### 7. Source parser and classification (parser.py)
- **Requirements**: R6, R10, R11
- **Files**: `src/do2screen/parser.py`
- **Details**: Orchestrate scanner → statements → grammar for a single file. Classify each statement: unknown registry command → `unknown_command`; recognized command with `none`/`restructures`/unavailable effect → `unsupported_effect`; unresolvable shape → `unsupported_syntax`. Apply effect only when shape and effect agree. Resolve include/nested-do targets with local path grammar relative to including source. Traverse depth-first, guard cycles with canonical paths, retain child provenance on every range. Macro-built targets → `unresolved_include`. Build complete attribution index. Validate no-dropped-lines invariant: every executable line in exactly one terminal disposition.
- **Test Scenarios**: command classification; include resolution; cycle detection; missing include target; attribution of all statement types
- **Tests**: `tests/test_parser.py`
- **Acceptance criteria**: All executable lines attributed or in unresolved_blocks; include traversal works

## Phase 3: Trace & CLI

### 8. Dependency traversal (trace.py)
- **Requirements**: R7, R8
- **Files**: `src/do2screen/trace.py`
- **Details**: Parse complete source graph before selecting target. Build `VariableTrace` for target; when `follow_parents=True`, traverse direct parents depth-first in first-reference order with visited set, terminate dependency cycles, represent each variable once. With `False`, leave `ancestors` empty while retaining target ranges and global audit inventory. Compute coverage: executable lines with at least one `attributed_ranges` record / all executable physical lines across all sources. No double-counting of continued/semicolon statement lines. **Edge cases**: (a) when there are zero executable lines (file contains only comments/blank lines), coverage = `1.0` (documented sentinel: full coverage of an empty executable set); (b) when the target variable is not found in the source, `TraceResult.ranges` is empty, `ancestors` is empty, but `unresolved_blocks` and `attributed_ranges` still reflect the full parsed source graph so the no-dropped-lines invariant remains meaningful.
- **Test Scenarios**: simple lineage; recursive ancestors; shared parents; cycle termination; follow_parents=False; coverage calculation; zero-executable-lines file; target-variable-not-found
- **Tests**: `tests/test_trace.py`
- **Acceptance criteria**: Correct ancestor tree with cycle termination; accurate coverage; no ZeroDivisionError; target-not-found returns valid empty TraceResult with full audit inventory

### 9. CLI (cli.py)
- **Requirements**: R9
- **Files**: `src/do2screen/cli.py`
- **Details**: Implement `do2screen PATH VARIABLE [--no-follow-parents] [--labels] [--indent N]`. Write one `TraceResult` JSON to stdout, diagnostics to stderr. Return nonzero for: invalid paths, invalid variable arguments, unreadable files, registry incompatibility. No network, time, random, or environment-dependent behavior.
- **Test Scenarios**: valid invocation produces JSON; invalid path → nonzero exit; invalid variable → nonzero; `--no-follow-parents` flag; `--labels` flag; `--indent` formatting
- **Tests**: `tests/test_cli.py`
- **Acceptance criteria**: CLI outputs valid JSON for valid inputs, correct error codes for invalid inputs

## Phase 4: Tests & Validation

### 10. Golden file fixtures
- **Requirements**: R11, R12
- **Files**: `tests/fixtures/stata_golden/`, `tests/fixtures/` (Python-native)
- **Details**: Create Stata do file fixtures covering: simple and recursive lineage, shared parents, cycle termination, command abbreviation, labels on/off, rename, `gen()` option, drops, prefixes, strings, every comment form, delimiter mode changes, `///`, factor/qualifier exclusions, JSON round-trip. Create fixtures for each unresolved category (§R11). Document upstream provenance. Port only variables mode.
- **Test Scenarios**: each fixture produces expected trace output
- **Tests**: `tests/test_golden.py`
- **Acceptance criteria**: All fixtures produce expected traces

### 11. Invariant suite and differential scaffolding
- **Requirements**: R10, R11, R12
- **Files**: `tests/test_invariant.py`, `tests/test_unresolved.py`, `tests/differential/`, `tests/differential/snapshots/`
- **Details**: Implement reusable invariant assertion over every fixture: derive executable lines from scanner, derive terminal lines from attributed + unresolved ranges, assert equality and disjoint dispositions, assert coverage = documented numerator/denominator. Build `tests/differential/` with two modes: (a) opt-in live Stata runner located by `DO2SCREEN_STATA_BIN` that generates a temporary Stata driver, exports `r(lines)`, and compares to Python output; (b) **snapshot-based differential tests** that compare Python output against committed golden `r(lines)` snapshots (captured from a prior Stata run and stored in `tests/differential/snapshots/`). Snapshot tests run in CI without a Stata binary. Skip only the live Stata tests with a clear pytest skip reason when `DO2SCREEN_STATA_BIN` is absent; snapshot tests and all Python unit/invariant tests always run.
- **Test Scenarios**: invariant holds over all fixtures; all 7 unresolved categories covered; snapshot differential tests pass; live differential tests skip cleanly without Stata
- **Tests**: `tests/test_invariant.py`, `tests/test_unresolved.py`, `tests/differential/test_differential.py`, `tests/differential/test_snapshots.py`
- **Acceptance criteria**: `pytest` full suite passes; invariant holds; unresolved categories all represented; snapshot differential comparison exercised

## Testing Strategy

1. Unit tests for each module (model round-trip, scanner masks, statement assembly, grammar extraction, parser classification, trace construction, CLI behavior)
2. Integration tests using golden file fixtures end-to-end
3. Invariant assertion over every fixture (no-dropped-lines)
4. Unresolved block coverage for all 7 categories
5. Differential testing scaffolding (opt-in via `DO2SCREEN_STATA_BIN`)
6. CLI smoke tests (JSON output, error codes)
7. Package build and editable install validation

## Documentation Checklist

- [ ] README: project description, installation, CLI usage, API overview
- [ ] `__init__.py` docstrings for all public exports
- [ ] Model field docstrings in `models.py`
- [ ] Module-level docstrings explaining purpose and interfaces
- [ ] Known limitations documented (macro expansion, data-dependent wildcards, `find`/`range` modes out of scope)

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Upstream `stata-command-registry` lacks `variable_effect` | Classification layer incomplete | Registry adapter fails gracefully with clear error; stub tests for effect lookup |
| Generic grammar misses Stata syntax edge cases | Unresolved blocks for legitimate code | Emit `unsupported_syntax` rather than dropping; grammar extensible by adding shapes |
| `#delimit ;` edge cases (nested, mid-block) | Incorrect statement boundaries | Test-driven implementation; real-world fixtures |
| Physical line accounting for continuations/delimiters | Incorrect `LineRange` values | Scanner emits per-line masks; statement assembly tracks all contributing lines |
| Include resolution with macro-built paths | Unresolved includes that should resolve | Emit `unresolved_include` block per Step 7; document that the include body is not traversed (per AGENTS.md §3.2) |

## Out of Scope

- `do2screen (Stata)` `find` and `range` modes
- Macro expansion and condition evaluation
- Data-dependent wildcard variable resolution
- User-written `ado` program semantics
- Stata differential test runner (requires Stata binary; scaffolding only)
- Repository publishing, CI/CD, GitHub Actions
- Domain-specific vocabulary from downstream consumers

## Completion Contract

### Outcome

do2screen-py is a fully functional Python package that parses Stata do files,
traces variable lineage through recursive dependency resolution, and produces
deterministic JSON output. All tests pass including the no-dropped-lines
invariant, the CLI produces correct JSON, and the package installs cleanly.
Snapshot-based differential tests validate against committed Stata golden
output. **Note**: live exact-match differential verification against a running
Stata binary (V13) is not claimed by this plan's completion — it requires
`DO2SCREEN_STATA_BIN` and is tracked as a non-blocking follow-up.

### Verification Surface

| ID | Phase | Evidence Required | Command/Artifact | Required |
|----|-------|-------------------|------------------|----------|
| V1 | 1 | Package installs and `import do2screen` works | `pip install -e . && python -c "import do2screen"` | yes |
| V2 | 1 | Pydantic models serialize/deserialize round-trip | `pytest tests/test_models.py` | yes |
| V3 | 2 | Scanner produces correct code masks for all comment forms | `pytest tests/test_scanner.py` | yes |
| V4 | 2 | Statement assembly handles delimiters, continuations, braces | `pytest tests/test_statements.py` | yes |
| V5 | 2 | Grammar extracts variable tokens from all generic shapes | `pytest tests/test_grammar.py` | yes |
| V6 | 3 | Recursive trace produces correct ancestor tree | `pytest tests/test_trace.py` | yes |
| V7 | 3 | CLI outputs valid JSON to stdout | `do2screen tests/fixtures/sample.do income` | yes |
| V8 | 4 | No-dropped-lines invariant holds over all fixtures | `pytest tests/test_invariant.py` | yes |
| V9 | 4 | All unresolved block categories covered | `pytest tests/test_unresolved.py` | yes |
| V10 | final | Full test suite passes | `pytest` | yes |
| V11 | final | Package builds successfully | `python -m build` | yes |
| V12 | final | Snapshot-based differential tests pass (golden Stata output committed) | `pytest tests/differential/test_snapshots.py` | yes |
| V13 | final | Live differential test against Stata binary (exact line-set match) | `DO2SCREEN_STATA_BIN=... pytest tests/differential/test_differential.py` | no |

### Constraints

| ID | Phase | Constraint | Check |
|----|-------|------------|-------|
| C1 | 1-4 | No hardcoded Stata command names in codebase | `grep -rn` for inline command lists/dicts/regex alts in `src/` |
| C2 | 1-4 | TraceResult JSON round-trips without loss | `model_dump_json()` / `model_validate_json()` in tests |
| C3 | 2-4 | Every non-blank, non-comment line attributed or in unresolved_blocks | Invariant assertion in `test_invariant.py` |
| C4 | 1-4 | No network calls, randomness, or environment dependence | Static inspection + deterministic test (same input → same output) |
| C5 | 3 | CLI writes exactly one JSON document to stdout, diagnostics to stderr | CLI smoke tests in `test_cli.py` |

### Boundaries

- Allowed: `src/do2screen/`, `tests/`, `pyproject.toml`, fixture Stata do files, documentation
- Out of scope: modifying `stata-command-registry`, domain-specific variable names, CI/CD config, `find`/`range` mode support

### Iteration Policy

1. If a module design conflicts with AGENTS.md hard invariants, halt and report.
2. If `stata-command-registry` lacks `variable_effect`, implement adapter with runtime compat failure and stub tests.
3. When generic grammar cannot determine a command shape, emit `unsupported_syntax` not command-specific exceptions.
4. Each phase must complete all required verification before the next phase starts.

### Blocked-Stop Conditions

- Registry is absent — package and tests run in degraded mode (classification layer unavailable); blocked-stop only if classification tests cannot be written against the mock registry.
- Installed `stata-command-registry` has an API surface incompatible with the documented contract (P2.1) and the conformance test fails.
- No-dropped-lines invariant fails and fix would violate AGENTS.md §3.1.
- Required test fixture cannot be created without actual Stata microdata.
- Plan requires modifying AGENTS.md or charter constraints.

deviation-policy: ask
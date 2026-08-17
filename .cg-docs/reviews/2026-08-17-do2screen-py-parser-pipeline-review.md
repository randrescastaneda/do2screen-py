---
date: 2026-08-17
depth: architecture
type: standard
plan: .cg-docs/plans/2026-08-17-do2screen-py-parser-pipeline.md
findings:
  P1.1: fixed
  P1.2: fixed
  P1.3: fixed
  P1.4: fixed
  P1.5: fixed
  P1.6: fixed
  P2.1: fixed
  P2.2: fixed
  P2.3: fixed
  P2.4: fixed
  P2.5: fixed
  P2.6: fixed
  P2.7: fixed
  P2.8: skipped
  P3.1: fixed
  P3.2: fixed
  P3.3: skipped
  P3.4: fixed
  P3.5: skipped
  P3.6: fixed
  P3.7: fixed
  P3.8: fixed
  P3.9: fixed
  P3.10: fixed
  P3.11: fixed
  P3.12: fixed
  P3.13: fixed
  P3.14: fixed
  P3.15: fixed
  P3.16: fixed
---

# Review Report: do2screen-py parser pipeline (review:auto, architecture route)

**Review mode**: architecture
**Files reviewed**: src/do2screen/*.py, tests/*.py, tests/fixtures/, tests/differential/, pyproject.toml, README.md, .gitignore
**Findings**: 30 (P0: 0, P1: 6, P2: 8, P3: 16)

Agents: cg-code-quality, cg-testing, cg-documentation, cg-version-control.
(Baseline: `183 passed, 4 skipped`.)

## P0 — BLOCKING
None.

## P1 — CRITICAL (must fix before merge)

- **[P1.1]** [cg-code-quality] src/do2screen/parser.py — macro/loop covered-block bookkeeping double-books lines when a non-macro statement precedes a macro statement inside the same brace block, breaking the no-dropped-lines invariant.
  **Why**: covered_blocks claims the block only when the macro statement is reached; earlier statements in the block were already attributed, so lines exist in both attributed_lines and unresolved_lines.
  **Fix**: Pre-detect macro-bearing brace blocks before classifying statements; claim the block as one unit so members are never attributed individually.
- **[P1.2]** [cg-testing] tests/ + src/do2screen/statements.py — `#delimit ;` sharing a physical line with statements silently swallows attribution of the trailing statements.
  **Why**: the directive branch consumes the whole line; the invariant still passes because the line is resolved as a directive.
  **Fix**: after a directive, resume processing the line tail in the new delimiter mode.
- **[P1.3]** [cg-testing] src/do2screen/trace.py — recursive ancestor resolution crashes with RecursionError on long chains (>= ~1000 deep).
  **Why**: `_resolve_ancestors` is recursive.
  **Fix**: make it iterative with an explicit stack.
- **[P1.4]** [safe_auto] [cg-version-control] .gitignore — Python/build artifacts (build/, dist/, *.egg-info/, __pycache__) would be swept into the first commit.
  **Why**: .gitignore only covers Compound GPID junctions.
  **Fix**: add standard Python excludes.
- **[P1.5]** [cg-testing] tests/ — most behavior fixtures are asserted only by the line-partition invariant, so regressions in string/factor/qualifier exclusion would pass the suite.
  **Why**: only unres_* and golden_* fixtures have positive behavior assertions.
  **Fix**: add behavior assertions over the fixture corpus.
- **[P1.6]** [cg-testing] tests/differential/test_differential.py — the live differential driver is a placeholder that would fail (or syntax-error on Python <3.12 via nested f-string) when a Stata binary is present.
  **Why**: the driver never invokes the tracing entry point; the `' '.join(f'do ...')` expression is garbage and PEP 701 nesting breaks 3.10/3.11.
  **Fix**: construct the driver without nested f-strings and xfail the opt-in live test until the real variables() driver is written.

## P2 — IMPORTANT (should fix)

- **[P2.1]** [safe_auto] [cg-testing] tests/invariant.py — attributed/unresolved sets are read from parser bookkeeping, not derived from the contract records; a consistent bookkeeping/record divergence would go undetected.
  **Fix**: derive both sets from graph.attributions / graph.unresolved ranges.
- **[P2.2]** [safe_auto] [cg-testing] tests/test_parser.py — unquoted include targets (legal in Stata) are untested and currently unreported as unresolved_include.
  **Fix**: support extracting the first code token after an include when no quoted string is present; add tests.
- **[P2.3]** [cg-testing] tests/test_parser.py — creates ordered-pair and modifies-varlist branches of `_apply_effect` are never exercised.
  **Fix**: add parser tests (`clonevar a b`, `replace x y`).
- **[P2.4]** [safe_auto] [cg-testing] tests/mock_registry.py — variable_effect raises bare KeyError for include/do/run instead of behaving like the documented contract.
- **[P2.5]** [advisory] [cg-documentation] README.md — the `[registry]` extra is shown as an ordinary install although `stata-command-registry` is not on PyPI yet.
  **Fix**: document that the extra currently requires the unpublished upstream package.
- **[P2.6]** [cg-documentation] src/do2screen/cli.py — `main`/`build_parser` are public entry points without docstrings.
- **[P2.7]** [advisory] [cg-version-control] .gitignore — `.kilo/plans/` and `.kilo/.gitignore` would be committed despite the surrounding "generated, do not commit" convention.
  **Fix**: decide explicitly; ignore `.kilo/plans/` to match the convention.
- **[P2.8]** [advisory] [cg-testing] tests/differential — snapshots are regression pins derived from implementation expectations, not Stata-captured golden output.
  **Fix**: track live differential (V13) as the acceptance path; keep snapshots as CI pins.

## P3 — MINOR (nice to have)

- **[P3.1]** parses `_contains_macro`/`_contains_macro_in` DRY duplication.
- **[P3.2]** scanner `_start_line` dead state keys + unused `line_no` param.
- **[P3.3]** `VariableTrace` exported but never constructed (advisory - keep as contract reserve).
- **[P3.4]** grammar `is_variable_like` dead code.
- **[P3.5]** `Token.start` never read (advisory).
- **[P3.6]** parser.py `from do2screen import grammar` partial-init import (use `from do2screen.grammar import ...`).
- **[P3.7]** test_models inline `__import__("pytest")`; use a top-level import.
- **[P3.8]** test_snapshots import inside test body; move to module top.
- **[P3.9]** test_differential broken/unused driver params.
- **[P3.10]** conftest `public_trace_degraded` dead helper.
- **[P3.11]** 8 lines exceed 88 chars; pin `[tool.ruff] line-length`.
- **[P3.12]** test_invariant `is_relative_to(...README.md)` dead filter.
- **[P3.13]** parser `_classify_statement` too long; extract attribution helper.
- **[P3.14]** test_models frozen-assignment exception type may differ across pydantic minors.
- **[P3.15]** test_differential stub references.
- **[P3.16]** README coverage wording implies per-source sentinel.

## ✅ Passed
- cg-code-quality: module boundaries clean; no hardcoded command names in src/; frozen contract pristine.
- cg-documentation: no domain vocabulary leaks; CLI exit codes/README/help agree; LICENSE/py.typed references exist.
- cg-version-control: no secrets/credentials; no large/binary files; protected artifacts intact.
- cg-testing: partition invariant over every fixture, 7 unresolved categories, cycles, includes, delimit/continuation, JSON round-trip all covered and green.

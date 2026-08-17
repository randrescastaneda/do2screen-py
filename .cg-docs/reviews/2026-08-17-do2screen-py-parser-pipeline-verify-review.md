---
date: 2026-08-17
depth: light
parent-review: .cg-docs/reviews/2026-08-17-do2screen-py-parser-pipeline-review.md
type: verification
findings:
  P1.7: fixed
  P1.1v: fixed
  P3.17: fixed
  P3.18: fixed
  P3.19: fixed
  P3.20: fixed
  P3.1v: fixed
---

# Verify Review: do2screen-py parser pipeline (mode:verify)

**Verification mode**: light depth following fix-triage of
`.cg-docs/reviews/2026-08-17-do2screen-py-parser-pipeline-review.md`.
**Agents**: cg-code-quality, cg-testing.
**Suite**: 231 passed, 4 skipped (3 registry-conformance, 1 opt-in live
differential); ruff clean.

## Suppression context

Prior fixed findings (P1.1, P1.2, P1.3, P1.4, P1.5, P1.6, P2.1-P2.7, P3.1-P3.16)
were verified to hold; the fixed-finding scope is not re-reported below unless
a genuine new issue appeared.

## New findings from verification (all addressed this pass)

- **[P1.7]** [cg-code-quality] parser.py — unterminated structures (open
  `{` blocks, unterminated `/*` comments) could double-book already-attributed
  executable lines, violating AGENTS.md 3.1.
  **Fix applied**: unterminated brace blocks and unterminated block comments
  are now claimed as covered before members are classified; new fixtures
  `tests/fixtures/unres_openbrace_code.do` and
  `tests/fixtures/unres_midline_comment.do` gate the partition.
- **[P1.1v]** [cg-testing] trace.py/invariant.py — `TraceResult.coverage` was
  correct only for single files; physical line numbers collide across include
  files, letting a fully-attributed child mask an unattributed root line.
  **Fix applied**: coverage is now keyed by `(source, line)` across all
  traversed sources (`coverage_of`); the invariant checks each file in the
  include graph individually, and the new `tests/fixtures/include_root.do` +
  `tests/fixtures/inc/lib.do` pair is partition-checked.
- **[P3.17]** line-length: wrapped `parser.py` ternary and the long
  `UnresolvedBlock` constructor in `test_models.py`.
- **[P3.18]** parser.py import: resumed the standard partial-init form
  `from do2screen import grammar` after ruff PLR0402; import order pinned.
- **[P3.19]** hoisted `from tests.invariant import assert_no_dropped_lines` to
  module top in `test_parser.py`.
- **[P3.20]** include traversal now bounded (`_MAX_INCLUDE_DEPTH = 64`) with an
  honest `unresolved_include` `depth_exceeded` report instead of unbound
  recursion.
- **[P3.1v]** removed dead `codes()` helper in `test_statements.py`.

## Verified clean

- Fixed-finding regression tests genuinely fail faster than they pass
  (invariant sensitivity to a corrupted `RangeAttribution` confirmed
  experimentally).
- All 26 fixture files pass the per-source partition invariant and the
  source-aware coverage cross-check (now including the include pair).
- Determinism, JSON round-trip, frozen contract, CLI exit codes unchanged.

## Convergence

The standard-review findings are resolved; the only issues surfaced by the
verify pass (P1.7, coverage) were fixed in this pass and are covered by
regression tests. The fix cycle has converged.

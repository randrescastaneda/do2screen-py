---
date: 2026-08-21
depth: light
parent-review: .cg-docs/reviews/2026-08-17-do2screen-py-parser-pipeline-review.md
type: verification
plan: .cg-docs/plans/2026-08-21-project-wide-tracing-with-source-lines.md
findings:
  P1.7: fixed
  P1.8: fixed
  P1.9: fixed
  P1.10: fixed
  P2.9: fixed
  P2.10: fixed
  P2.11: fixed
  P2.12: fixed
  P2.13: fixed
  P2.14: fixed
  P3.17: fixed
  P3.18: fixed
---

# Verify Review: Project-Wide Tracing With Source Lines

**Review mode**: light verification

**Parent review**: `.cg-docs/reviews/2026-08-17-do2screen-py-parser-pipeline-review.md`

**Files reviewed**: current uncommitted implementation, tests, documentation,
canonical plan, and workflow artifacts. Generated `.cg-docs/views/**` bodies were
not read.

**Verification context**: The parent review's explicitly fixed findings were
suppressed where applicable. P0/P1 issues and cross-file breakage remain
reportable. The optional Stata differential environment remains non-required.

**Test evidence**: `380 passed, 6 skipped, 31 xfailed`; package build,
`compileall`, `git diff --check`, and canonical plan validation passed. The live
Stata differential was skipped because `DO2SCREEN_STATA_BIN` is unset.

## P0 — BLOCKING

None.

## P1 — CRITICAL

- **[P1.7]** [cg-code-quality] `src/do2screen/parser.py:619-644` — valid
  one-character commands after a registry-recognized `by` prefix can be
  misclassified as a match specification. The parser must use the registry and
  colon structure to recognize `by a: g b = 1` without treating `a` as the
  command. Add a regression test.

- **[P1.8]** [cg-code-quality, cg-testing] `src/do2screen/parser.py:580-619` —
  include target extraction scans comment-preserving statement text and can
  select a quoted path from `//` or `/* */` comments. This can traverse the
  wrong source and corrupt containment, cache, and lineage. Extract quoted and
  unquoted targets using comment-aware lexical spans. Add tests for trailing
  line/block comments and valid apostrophes inside filenames.

- **[P1.9]** [cg-code-quality, cg-testing] `src/do2screen/project.py:442-475` —
  distinct same-line include calls can be collapsed by physical range keys,
  losing a resolved, missing, or unreadable include outcome. Preserve each call
  identity and aggregate only the terminal physical-line representation needed
  to maintain the no-dropped-lines invariant. Add a resolved-plus-missing
  same-line regression.

- **[P1.10]** [cg-testing] `src/do2screen/statements.py:251-278` — delimiter
  directive tails remain lossy. `#delimit cr gen x = 1` can discard the tail,
  and semicolon-mode tails can rebuild raw text from code-only content, losing
  quoted include targets. Reprocess both delimiter modes while preserving the
  original text and masks; add same-line directive/include tests.

## P2 — IMPORTANT

- **[P2.9]** [cg-testing] `tests/test_project.py:187-206` — the helper used by
  project invariant tests fabricates every physical line as executable and
  discards actual parsed records. Assert invariants against the real
  `ProjectGraph` or recompute executable lines through the scanner.

- **[P2.10]** [cg-testing] `tests/test_tricky_harmonization.py:490-509` — the
  adversarial invariant still uses bare line-number sets, allowing collisions
  between root and included files to mask coverage failures. Use source-qualified
  `(source, line)` coordinates or the source-aware invariant helper.

- **[P2.11]** [cg-testing] `tests/test_project.py:109-125` — source-line tests
  assert only payload length, not exact decoded text. Compare every checked range
  with the physical source slice, including root, include, multiline,
  unresolved, and same-line collision cases.

- **[P2.12]** [cg-testing] `tests/test_project.py:237-248` — the project cycle
  test is a future-reference/unbound-definition case, not an actual cycle. Use
  active preceding definitions, such as `gen y = 1`, `gen x = y`, `replace y = x`,
  and assert cycle-safe termination.

- **[P2.13]** [cg-testing] `tests/test_manifest.py:18-48` — manifest tests do
  not cover malformed JSON or valid absolute entries despite the documented V1
  boundary. Add both cases and retain canonical duplicate assertions.

- **[P2.14]** [cg-testing] `tests/test_cli.py:72-77,126-171` — project-mode
  deterministic output and exact invalid-invocation exit behavior are
  underasserted. Repeat each project mode, compare serialized JSON byte-for-byte,
  and assert exit code `2` plus stdout/stderr behavior for invalid invocations.

## P3 — MINOR

- **[P3.17]** [cg-code-quality] `src/do2screen/manifest.py:7` — unused `Path`
  import.

- **[P3.18]** [cg-code-quality] `tests/test_ingest.py:5` — unused `os` import.

## Passed

- `@cg-code-quality`: prior fixed findings were not re-reported; no debug
  markers or protected-artifact violations found beyond the findings above.
- `@cg-testing`: full Python suite remains green under the repository's explicit
  strict-xfail policy; no P0 findings.
- Registry `0.4.0` source-driver conformance remains satisfied.
- The optional Stata/do2screen (Stata) differential remains correctly treated
  as skipped external evidence, not a package prerequisite.

## Incomplete Reviews

None. Both required verify reviewers returned usable output.

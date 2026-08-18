---
date: 2026-08-17
title: "Guarding a lossless static parser with a no-dropped-lines invariant"
category: "testing-patterns"
language: "Python"
tags: [parser, testing, invariant, coverage, pydantic, do2screen]
root-cause: "A static tracer's worst failure is a line silently dropped: downstream consumers cannot distinguish 'never touched' from 'parser did not understand'. Asserting behaviour against parser bookkeeping fields is circular."
severity: "P1"
---

# Guarding a lossless static parser with a no-dropped-lines invariant

## Problem

`do2screen-py` reimplements the do2screen (Stata) tracer: it reads a Stata do
file and reports the physical lines that create/modify/drop/label a variable.
The hard contract (AGENTS.md section 3.1) says **every** non-blank,
non-comment line must end up in exactly one of two places: attributed to a
variable, or recorded in `unresolved_blocks`. An empty result is ambiguous —
it can mean "the variable was never touched" (information) or "the parser did
not understand the code" (a lie).

A first implementation asserted the invariant against parser-maintained
bookkeeping fields (`attributed_lines` / `unresolved_lines`), which are
updated in the same code paths that append the contract records. That is
circular: if the bookkeeping and the records drift together, the assertion
passes while the persisted `TraceResult` is corrupted.

Two real defects were caught during review-verify:

- A macro/loop brace block claimed AFTER its non-macro members were already
  attributed double-booked lines: a line in both `attributed` and `unresolved`
  sets, invisible to the invariant because the bookkeeping moved in lockstep.
- `coverage` was computed over flattened line numbers, so in an include graph
  a fully-attributed child file (line 1, 2) masked an unattributed root line
  at line 1 → coverage reported 1.0 instead of the true fraction.

## Root Cause

Linear, order-dependent "claim a block when you reach the macro statement"
logic can never keep a partition disjoint without pre-claiming blocks before
classifying members; and treating physical line numbers as globally unique
breaks the moment a file `include`s another file with overlapping line
numbers.

## Solution

1. **Derive both terminal sets from the persisted contract records**, never
   from parser bookkeeping:
   ```python
   attributed = {ln for att in graph.attributions
                 for ln in range(att.range.start_line, att.range.end_line + 1)}
   unresolved = {ln for u in graph.unresolved
                 for ln in range(u.range.start_line, u.range.end_line + 1)}
   executable = {l.line_no for l in scan(text).lines if l.has_code()}
   assert (attributed | unresolved) & executable == executable
   assert not (attributed & unresolved) & executable
   ```
2. **Pre-claim structural blocks before classifying members.** Unterminated
   brace blocks, unterminated `/*` comments, and macro-bearing blocks are all
   claimed as covered ranges *before* any member statement is classified, so a
   member is either attributed or absorbed — never both.
3. **Key coverage by `(source, line)`**, not by bare line number, across every
   traversed include:
   ```python
   executable_pairs = {(f.path, ln) for f in graph.files for ln in f.executable_lines}
   covered_pairs = {(att.range.source, ln) for att in graph.attributions
                    for ln in range(att.range.start_line, att.range.end_line + 1)}
   coverage = len(covered_pairs & executable_pairs) / len(executable_pairs)
   ```
4. **Run the invariant per file** — including every child in an include graph —
   by re-scanning each `ParsedFile.path` independently.
5. Pin down the tricky cases as fixtures: a former-block (open brace + an
   already-attributable member line), a mid-line unterminated block comment,
   and a root + included child pair.

## Prevention

- Write the invariant against the *public contract objects*, not internal state.
- Pre-claim exclusion ranges before the pass that can attribute their members.
- Treat physical line numbers as a per-source coordinate; key any cross-file
  metric by `(source, line)`.
- Add a regression fixture for every "weird-but-legal" shape: `#delimit ;`
  sharing a line with statements, unquoted `include`, deep ancestor chains
  (run the tracer iteratively — `RecursionError` at ~1000 links is realistic
  in long data-cleaning scripts), and unterminated structures adjacent to
  executable code.

## Related

- `.cg-docs/plans/2026-08-17-do2screen-py-parser-pipeline.md` — the plan with
  the invariant as a completion gate.
- `.cg-docs/reviews/2026-08-17-do2screen-py-parser-pipeline-review.md` and
  `-verify-review.md` — findings that caught the two defects above.

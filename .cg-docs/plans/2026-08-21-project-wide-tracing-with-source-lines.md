---
date: 2026-08-21
title: "Project-wide tracing with source lines"
status: completed
completed-date: 2026-08-22
completed-phases: [1, 2, 3, 4, 5]
execution-report: .cg-docs/work-reports/2026-08-21-project-wide-tracing-with-source-lines.md
failing-steps: []
scope: "Deep"
brainstorm: null
language: "Python"
estimated-effort: "large"
deviation-policy: "ask"
artifact-schema-version: 1
tags: [parser, stata, tracing, source-lines, multi-file, manifest, cli, reviewed]
phases: 5
---

# Plan: Project-Wide Tracing With Source Lines

## Objective

Extend do2screen-py to trace a variable across an explicit ordered file list, a
versioned JSON manifest, or a directory corpus. Include the exact physical code
lines for every returned source range so JSON consumers receive the code and its
provenance together. Preserve single-file `trace()` behavior and every existing
parser invariant.

## Context

- `trace()` currently parses one root file and its resolved include graph, then
  projects a `ParsedGraph` into the frozen public `TraceResult` contract.
- `LineRange` contains source coordinates but no source text. Every attribution
  and unresolved block refers to a `LineRange`, making an optional
  `LineRange.source_lines` field the smallest consistent public extension.
  Its public representation is decoded physical-line content without `CR`,
  `LF`, or `CRLF` terminators, after the existing UTF-8 BOM removal and
  replacement-character decoding policy.
- `Parser.parse_graph()` resets its include-cycle set for each root call, and
  it currently marks repeated includes as a cycle. Project tracing therefore
  requires a physical-source parse cache plus a separate include-occurrence
  stream, not a post-parse root-level deduplication set.
- Existing source-aware coverage already uses `(source, line)` pairs; project
  coverage and no-dropped-lines checks must retain that coordinate system.
- Directory enumeration may be deterministic without being an execution-order
  claim. Only explicit file-list and manifest order permit cross-file lineage.
- A terminal `UnresolvedBlock` cannot express a missing file with no source
  range or an ambiguity on a line already attributed without fabricating or
  overlapping coordinates. Project-level uncertainty therefore needs a separate
  defaulted `project_diagnostics` public field; terminal parser disposition
  remains exclusively in `unresolved_blocks`.
- The current mock registry is test infrastructure, but the repository forbids
  local command vocabulary. The optional `[registry]` extra must obtain the
  latest available upstream `main` revision at installation or explicit
  upgrade time. Project work remains blocked until `stata-registry` `0.4.0` or
  later provides a formal source-driver contract and conformance data. The
  upstream contract must include an explicit `include_driver: bool` field for
  shipped command entries, a public `is_include(token) -> bool` lookup that
  resolves canonical names and supported abbreviations, and upstream tests
  identifying the commands that execute another Stata source file. This
  repository must not extend the mock with new command names or infer source
  drivers from `variable_effect`.
- Current live differential tests are an xfailed placeholder. An executable
  do2screen (Stata) runner remains valuable external parity evidence, but it is
  optional for local implementation and completion because do2screen-py must
  install, run, and pass its Python test suite without Stata. When a Stata
  environment or Stata MCP is available, run the reference comparison; when it
  is not available, record the skipped optional evidence and retain the
  committed snapshot and Python regression checks.
- The source-aware invariant must derive terminal coverage from persisted
  attribution and unresolved records, not parser bookkeeping. — source:
  `.cg-docs/solutions/testing-patterns/2026-08-17-no-dropped-lines-invariant-and-source-aware-coverage.md`

## Requirements

| ID | Requirement | Source |
|----|-------------|--------|
| R1 | Add defaulted `LineRange.source_lines` containing decoded physical-line content without line terminators; old `TraceResult` JSON must still validate. | user request; public contract |
| R2 | Populate source lines inclusively and in order for every parser-emitted attribution and terminal unresolved range without changing coordinates. | user request; lossless parser invariant |
| R3 | Add a defaulted `project_diagnostics` channel for non-terminal project uncertainty, with optional range/provenance facts, separate from `unresolved_blocks`. | uncertainty-reporting invariant |
| R4 | Keep `trace(path, variable, ...)` signature and existing field meanings intact; all public changes are additive defaults. | AGENTS.md public contract |
| R5 | Add `trace_directory`, `trace_files`, and `trace_manifest` entry points with exact, documented input and empty-input behavior. | supplied planning artifact |
| R6 | Support exactly manifest V1: `{"version": 1, "files": ["relative/a.do"]}`; reject unknown top-level keys, non-string entries, empty arrays, and unsupported versions. | revised plan review finding P2.2 |
| R7 | Enumerate `.do` and `.ado` files deterministically; recursion is opt-in and paths escaping the requested directory are excluded. | deterministic/offline invariant |
| R8 | Parse each canonical physical file once per project run, while replaying its immutable parsed events for every non-cyclic include occurrence at the call site. | revised plan review finding P1.1-P1.2 |
| R9 | Define complete partial-failure semantics for invalid inputs, missing/unreadable roots, and unreadable includes; never silently omit an accepted project input. | revised plan review finding P2.3 |
| R10 | Merge and project validated sources using canonical source identity, globally reindexed provenance, and `(source, line)` coverage coordinates. | no-dropped-lines invariant; P2.4 |
| R11 | Resolve cross-file lineage with occurrence-qualified definition nodes and active-definition binding, never a merged name-only parent map. | revised plan review finding P1.3 |
| R12 | In unordered directory mode, report cross-file dependency and same-name ambiguity as non-terminal `cross_file_unordered` project diagnostics and omit uncertain ancestry edges. | uncertainty-reporting invariant; P1.4 |
| R13 | Add optional project metadata without changing existing fields: input mode, project files, manifest path, variable identities/contexts, and project diagnostics. | public contract |
| R14 | Track the latest upstream registry `main` revision at installation or explicit upgrade time, record its resolved commit and package version for each verification run, and require `stata-registry` `0.4.0+` to provide explicit source-driver metadata, a public include lookup, conformance tests, and upstream-supplied test data before project implementation proceeds. | registry boundary; P1.5 |
| R15 | Extend the CLI with exact unambiguous project grammar while preserving `do2screen PATH VARIABLE` legacy grammar. | revised plan review finding P1.6 |
| R16 | Document source-line representation, API signatures, manifest schema, ordering, diagnostics, failure policy, and limitations. | documentation quality |
| R17 | Retain no-dropped-lines, deterministic output, source-aware coverage, JSON round-trip, and optional executed do2screen (Stata) line-set differential evidence when a reference environment is available. | AGENTS.md §§3.1-3.5, 5; P1.7 |

## Implementation Steps

## Phase 1: Upstream Registry Prerequisite

### 1. Establish the registry source-driver capability boundary

- **Requirements**: R14, R17
- **Files**: `pyproject.toml`, `src/do2screen/registry.py`, `tests/test_registry_conformance.py`, upstream `stata-command-registry` release notes and conformance fixture/data
- **Details**:
  - Keep the optional registry dependency pointed at the upstream Git repository's `main` branch so a fresh installation or explicit upgrade resolves its latest available revision. Record the resolved commit and installed package version in verification evidence; the installed revision, not a moving network lookup during tracing, determines deterministic output.
  - Require an upstream `0.4.0+` source-driver contract: every shipped command entry has an explicit `include_driver` boolean, source-driving commands are marked from upstream-maintained Stata evidence, and the reader exports `is_include(token) -> bool` for canonical names and supported abbreviations. The upstream API must return `False` for non-source-driving or unknown tokens rather than infer behavior from `variable_effect`.
  - Change `RegistryAdapter.is_include()` from an optional silent fallback to a conformance-checked capability for source-graph/project APIs. An absent or incompatible capability must raise `RegistryIncompatibilityError` for project tracing; existing single-file behavior remains governed by the installed supported registry contract.
  - Add an adapter conformance test for the upstream source-driver fixture and assert the installed package is `stata-registry>=0.4.0`. Do not add command names, abbreviations, effects, prefixes, or source-driver names to a local mock.
  - Document the optional do2screen (Stata) reference runner location, supported binary/version, invocation driver, ported corpus, and machine-readable line-set output format for environments that can provide external parity evidence.
- **Test Scenarios**: `stata-registry>=0.4.0` exposes explicit source-driver metadata and the required lookup; missing/old registry fails explicitly; upstream conformance data is consumed without local vocabulary; optional reference driver produces one line-set result per corpus case when available.
- **Tests**: registry source-driver conformance test; optional reference-runner smoke test on one golden fixture.
  - **Acceptance criteria**: The latest resolved upstream `main` revision is `stata-registry>=0.4.0` and satisfies the source-driver contract. An unavailable Stata executable, Stata MCP, or reference runner is recorded as skipped optional evidence and does not block this plan.

## Phase 2: Public Contract And Lossless Source Text

### 2. Add code-bearing ranges and project diagnostics

- **Requirements**: R1, R3, R4, R13
- **Files**: `src/do2screen/models.py`, `tests/test_models.py`, `src/do2screen/__init__.py`
- **Details**:
  - Extend frozen `LineRange` with `source_lines: list[str] = Field(default_factory=list)`, defined as decoded line content with terminators removed by the scanner's physical-line contract.
  - Add frozen Pydantic `VariableContext` and `VariableIdentity` models. Contexts identify a canonical source, first creation line, lifecycle ranges, and direct parents.
  - Add frozen `ProjectDiagnostic` with a diagnostic code, source/manifest facts, and an optional `LineRange`. It must be valid when no physical source range exists.
  - Keep `UnresolvedReason` limited to terminal parser disposition. Do not add missing-file or cross-file ambiguity codes to it.
  - Add only optional/defaulted `TraceResult` fields: `input_mode`, `project_files`, `variable_identities`, `manifest_path`, and `project_diagnostics`.
  - Re-export new public models and trace entry points after their implementation.
- **Test Scenarios**: legacy serialized result without new fields; source lines defaulting empty; diagnostics without a range; frozen nested models; JSON round-trip; invalid terminal unresolved reason rejected.
- **Tests**: `pytest tests/test_models.py`
- **Acceptance criteria**: Existing persisted JSON validates unchanged and new JSON re-serializes byte-identically.

### 3. Preserve decoded physical lines through parsing

- **Requirements**: R1, R2, R17
- **Files**: `src/do2screen/parser.py`, `src/do2screen/models.py`, `tests/test_parser.py`, `tests/test_trace.py`, `tests/test_invariant.py`
- **Details**:
  - Retain decoded physical lines without terminators on each parsed source record, separate from lexical masks and assembled statements. This is the exact documented JSON representation, not byte-faithful source preservation.
  - Centralize inclusive-range construction so every `LineRange` emitted by attribution or unresolved recording receives the matching raw-line slice.
  - Preserve BOM-removal and replacement-character behavior already defined by `read_source()`; add CRLF, BOM, and undecodable-byte tests that assert this contract. Do not reconstruct code from parsed statements.
  - Populate source lines for ranges created by normal statements, block claims, directives, include diagnostics, and unresolved syntax.
  - Ensure range construction never reads a different source than the range's `source` coordinate.
- **Test Scenarios**: one-line generation; `///` continuation; `#delimit ;` statement; range with preceding comments; multi-line unresolved block; included child with the same physical line number as root.
- **Tests**: `pytest tests/test_parser.py tests/test_trace.py tests/test_invariant.py`
- **Acceptance criteria**: Every parsed output range has ordered decoded source lines matching its inclusive coordinates, with existing line numbers and coverage unchanged.

### 4. Define project input specifications and ingestion

- **Requirements**: R5, R6, R7, R9
- **Files**: `src/do2screen/ingest.py`, `src/do2screen/manifest.py`, `tests/test_ingest.py`, `tests/test_manifest.py`
- **Details**:
  - Define a small typed internal ingestion specification that records mode, root paths, whether execution order is declared, optional manifest provenance, recursive discovery, and ingestion diagnostics.
  - Implement deterministic directory discovery for `.do` and `.ado` files using normalized real paths; do not use discovery order as semantic execution order.
  - Exclude hidden paths and symbolic-link targets outside the requested directory; retain a stable canonical sort order.
  - Implement exactly manifest V1: `{"version": 1, "files": ["relative/a.do"]}`. Reject unknown top-level keys, non-string entries, empty arrays, and unsupported versions. Resolve relative entries from the manifest directory; allow absolute entries only if they are normalized/canonicalized, and deduplicate canonical paths with first occurrence winning.
  - Define `trace_files(files, variable, *, follow_parents=True, include_labels=False)` to reject an empty file list with `ValueError`; define `trace_directory(directory, variable, *, recursive=False, follow_parents=True, include_labels=False)` and `trace_manifest(manifest_path, variable, *, follow_parents=True, include_labels=False)`.
  - Record missing or unreadable entries as `ProjectDiagnostic` values rather than aborting readable files or inventing a `LineRange`.
- **Test Scenarios**: flat and recursive directories; deterministic repeat enumeration; hidden/external symlink exclusion; valid relative/absolute manifest; duplicate path; unknown key; malformed JSON; non-string/empty entries; missing version; unsupported version; empty explicit list; missing listed file.
- **Tests**: `pytest tests/test_ingest.py tests/test_manifest.py`
- **Acceptance criteria**: Every valid mode produces a deterministic ingestion specification and every invalid/missing manifest condition is explicit.

## Phase 3: Cached Parsing, Occurrence Sequencing, And Invariants

### 5. Build a physical-source cache and execution-occurrence stream

- **Requirements**: R8, R9, R10, R14
- **Files**: `src/do2screen/parser.py`, `src/do2screen/project.py`, `src/do2screen/trace.py`, `tests/test_project.py`, `tests/test_registry_conformance.py`
- **Details**:
  - Refactor parser internals behind the formal registry capability so a project-owned cache parses/scans each canonical physical source once per run, including included sources.
  - Preserve immutable per-source parsed records in that cache and separately emit an occurrence stream. Each root and each resolved include call emits an occurrence with its root order, caller occurrence, call-site line range, canonical source, and monotonically increasing execution sequence.
  - Replay cached source events at every non-cyclic include occurrence; distinguish active-stack recursion cycles from legitimate repeated includes. The cache avoids rereading/reparsing while the occurrence stream preserves each execution location.
  - Catch `OSError` while resolving a root as a non-terminal project diagnostic and while resolving an include at its including statement as terminal `unresolved_include` with the OS error fact. A valid partial project result exits CLI success (`0`) when at least one root is parsed; invalid invocation/manifest stays `2`; a project with no readable roots exits `1` and emits no success JSON.
  - Canonicalize source identity at the cache/parser boundary. Rebuild project provenance with global deterministic traversal indexes from first physical-source appearance; document `TraceResult.source` as the first root source for ordered modes and the first canonical discovery source for directory mode, with no semantic precedence.
- **Test Scenarios**: two roots include one child; one root includes child twice; direct child plus included child; recursive include; include between parent create and modify; unreadable root; unreadable include; source symlink aliases; multiple roots receive globally unique provenance indices.
- **Tests**: `pytest tests/test_project.py tests/test_registry_conformance.py`
- **Acceptance criteria**: Each physical source is read/scanned once, every valid include occurrence has correctly sequenced replayed events, recursion is terminally unresolved, and all source/provenance identity is canonical and deterministic.

### 6. Project records, diagnostics, and invariant coverage

- **Requirements**: R2, R3, R9, R10, R12, R13, R17
- **Files**: `tests/invariant.py`, `tests/test_invariant.py`, `tests/fixtures/project/`, `tests/test_project.py`
- **Details**:
  - Introduce an internal project result containing cached physical sources, occurrence events, canonical provenance, terminal parser records, and separate project diagnostics. Never turn an already attributed line into an unresolved block for project-level uncertainty.
  - Add a project-level invariant helper that applies the existing persisted-record partition check independently to every cached `ParsedFile`; repeated occurrences do not multiply physical executable-line coverage.
  - Compute project coverage from source-qualified record coordinates, never flattened line numbers or parser bookkeeping fields.
  - Add realistic non-confidential fixtures covering standalone pairs, ordered chains, includes interleaved with caller statements, repeated includes, include-plus-root deduplication, empty directories, missing manifest entries, unreadable include/roots, and same-name variables.
  - Assert source-line payloads directly in representative fixture outputs, including a multi-line range and two sources sharing the same line number.
- **Test Scenarios**: terminal partition remains complete/disjoint per source; non-terminal diagnostics do not overlap terminal dispositions; coverage collision regression; source-lines exactness; project fixture corpus includes all intended files.
- **Tests**: `pytest tests/test_invariant.py tests/test_project.py`
- **Acceptance criteria**: Project support does not weaken or bypass no-dropped-lines; physical lines are counted once even when their parsed events occur multiple times.

## Phase 4: Context-Qualified Lineage And Explicit Uncertainty

### 7. Bind ordered references to active definition contexts

- **Requirements**: R10, R11, R13
- **Files**: `src/do2screen/project.py`, `src/do2screen/trace.py`, `tests/test_project.py`
- **Details**:
-  - Build context-qualified definition nodes from occurrence events instead of merging `dict[str, list[str]]` by variable name. A node includes variable name, occurrence sequence, source, statement range, lifecycle effect, and direct referenced definition-node IDs.
  - In explicitly ordered modes, bind each variable reference to the latest active preceding definition in the execution-occurrence stream. `drop` deactivates the bound definition; a later create/recreate becomes the new active definition.
  - Resolve ancestors with an iterative context-node graph walk. Project mode must not call `_resolve_ancestors()` over an aggregated name-only map for cross-file results; retain the existing resolver for single-file compatibility.
  - Carry rename-derived dependencies through the generic direct-reference graph without adding command-name-specific project parsing.
  - Build variable identities from definition contexts, and project target lifecycle in occurrence sequence order. Keep `source` as the documented non-semantic compatibility provenance and expose all sources via project metadata.
- **Test Scenarios**: manifest create/modify/drop chain; two definitions of `a` with different parents then `x = a`; reference before/after recreation; reference after drop; file-list dependency; multi-file parent cycle; cross-file generic rename-derived chain; `follow_parents=False`.
- **Tests**: `pytest tests/test_project.py -k ordered`
- **Acceptance criteria**: Explicitly ordered inputs yield deterministic occurrence-ordered lifecycles and cycle-safe ancestors tied only to active preceding definitions.

### 8. Report unordered project ambiguity without guessing

- **Requirements**: R3, R11, R12, R17
- **Files**: `src/do2screen/project.py`, `tests/test_project.py`, `tests/test_unresolved.py`
- **Details**:
  - In directory mode, identify references and same-name contexts that span source files and lack an explicit ordering contract.
  - Emit non-terminal `ProjectDiagnostic(code="cross_file_unordered")` records with optional range, variable, candidate definition sources, and ambiguity subtype facts. Do not add the code to `UnresolvedReason` and do not overlap an attributed range with an unresolved block.
  - Exclude uncertain cross-source bindings from the context-node ancestor walk while retaining the complete audit inventory and lifecycle ranges.
  - Retain within-source dependencies in unordered mode. Do not infer an order from path names, traversal order, timestamps, or code content.
  - Add fixture coverage for cross-file reference, same-name creation followed by reference, and rename-derived dependency without an ordered manifest.
- **Test Scenarios**: unordered reference; ambiguous duplicate creation; ordered equivalent succeeds; cycle terminates; expected unresolved contexts are JSON-serializable.
- **Tests**: `pytest tests/test_project.py -k unordered && pytest tests/test_unresolved.py`
- **Acceptance criteria**: All uncertain cross-file semantics are visible as unresolved blocks and no guessed ancestor is returned.

## Phase 5: API, CLI, Documentation, And Release Verification

### 9. Expose public trace modes and unambiguous CLI input selection

- **Requirements**: R4, R5, R15
- **Files**: `src/do2screen/trace.py`, `src/do2screen/__init__.py`, `src/do2screen/cli.py`, `tests/test_trace.py`, `tests/test_cli.py`
- **Details**:
  - Implement the exact documented public signatures from Step 4 as thin typed entry points over ingestion and project tracing.
  - Keep `trace()` signature, error behavior, provenance fields, and output semantics unchanged except the additive `source_lines` payload.
  - Define exact CLI grammar: legacy mode is `do2screen PATH VARIABLE`; project modes require `do2screen --variable VARIABLE --dir DIR [--recursive]`, `do2screen --variable VARIABLE --files FILE [FILE ...]`, or `do2screen --variable VARIABLE --manifest MANIFEST`. `--variable` is required iff a project input flag is present, prohibited in legacy mode, and `--recursive` is valid only with `--dir`.
  - Preserve invalid variable handling, one-JSON-document stdout contract, and exit-code categories: `2` invalid invocation or manifest schema, `0` complete/partial project result with JSON diagnostics, `1` unreadable single-file input or a project with no readable roots. Diagnostics remain on stderr.
- **Test Scenarios**: exact legacy invocation; all exact project commands; variable/input mutual-exclusion failure; missing input; invalid recursive use; partial project success JSON; no-readable-root failure; JSON contains source lines and project diagnostics; repeated output byte-identical.
- **Tests**: `pytest tests/test_cli.py tests/test_trace.py`
- **Acceptance criteria**: Existing CLI calls continue to work and every accepted new mode produces valid deterministic JSON.

### 10. Document the extended output and project semantics

- **Requirements**: R16
- **Files**: `README.md`, `docs/installation.md`, `docs/output-format.md`, `docs/examples.md`, `docs/api.md`, `docs/roadmap.md`
- **Details**:
  - Define `LineRange.source_lines` as decoded physical-line text without terminators after UTF-8 BOM removal/replacement decoding, including its inclusive relationship to `start_line` and `end_line` and availability in target, audit, and terminal unresolved records.
  - Document `ProjectDiagnostic` separately from `UnresolvedBlock`, including missing/unreadable input and `cross_file_unordered` facts.
  - Add concise API and exact CLI examples for every project input mode; add the new functions/models to `docs/api.md` MkDocs directives.
  - Publish manifest V1 schema, unknown-key policy, relative/absolute path behavior, duplicate behavior, and empty-input failures.
  - Explain deterministic-but-unordered directory discovery, explicit occurrence-based execution ordering, include/repeated-include behavior, partial-failure exit policy, and when `cross_file_unordered` appears.
  - State limitations honestly: no Stata execution, macro evaluation, inferred pipeline order, caching exposed to callers, or parallel parsing.
- **Test Scenarios**: examples correspond to exact public signatures and valid JSON fields; docs make representation/order/diagnostic boundaries explicit.
- **Tests**: documentation link/build checks already used by the repository, if available.
- **Acceptance criteria**: A consumer can select an input mode, interpret code-bearing ranges, and understand ambiguity behavior without reading implementation code.

### 11. Run complete compatibility, reference, and distribution checks

- **Requirements**: R14, R17
- **Files**: all changed implementation and test files
- **Details**:
  - Run the complete pytest suite, including existing golden and snapshot coverage.
  - If a Stata executable, Stata MCP, and completed do2screen (Stata) reference driver are available, run the driver over every ported golden corpus case and diff the returned line sets against do2screen-py. Otherwise record the optional differential evidence as skipped. Keep physical-range-specific delimiter/continuation assertions in Python tests where the reference has transformed parser-record numbering.
  - Build the distribution and run public import smoke tests for legacy and new entry points/models.
  - Compare repeated single-file `TraceResult.model_dump_json()` results to protect deterministic output after source text is added.
  - Inspect all changes for registry-boundary violations before declaring completion; do not treat optional Stata availability as a package dependency.
- **Test Scenarios**: full suite; package build; imports; repeated single-file and project output.
- **Tests**: `pytest && python -m build && python -c "from do2screen import trace, trace_directory, trace_files, trace_manifest, VariableIdentity, ProjectDiagnostic"`; run the pinned do2screen (Stata) corpus-diff command when the optional reference environment is available.
- **Acceptance criteria**: Required unit, invariant, registry, package, and import commands pass with no compatibility or parity regressions. Reference differential evidence is recorded as passed when available or skipped with a rationale when unavailable.

## Testing Strategy

| Category | Mechanism |
|---|---|
| Public JSON compatibility | Validate old JSON without added fields; round-trip source lines, identities, and diagnostics without ranges. |
| Source-line representation | Assert decoded terminator-free exactness for LF/CRLF, BOM, replacement decoding, continuation, delimiter, include, and unresolved ranges. |
| Registry prerequisite | Run source-driver/include conformance tests against the resolved upstream `main` revision and upstream-supplied data; block on absence, an old package version, or an API/data mismatch. |
| Ingestion | Use `tmp_path` projects for containment, exact V1 schema, unknown keys, duplicates, missing files, and empty explicit lists. |
| Parse cache and occurrences | Assert one physical read/parse with replay at every repeated include call site; distinguish repetition from recursion. |
| Ordered lineage | Exercise interleaved includes, replacement definitions, drops/recreation, rename-derived dependencies, active-definition binding, and cycles. |
| Unordered safety | Verify directory mode emits non-terminal `cross_file_unordered` diagnostics and never returns guessed cross-file ancestors. |
| Invariants | Derive terminal sets and coverage from persisted records per physical source; diagnostics never alter the terminal partition. |
| CLI and API | Test exact legacy/project grammar, partial/no-readable-root exit behavior, stdout/stderr discipline, imports, and deterministic JSON. |
| Differential acceptance | Execute the pinned do2screen (Stata) driver over every ported golden case and diff returned line sets when the optional reference environment is available; otherwise record the skip and use snapshots plus Python regression checks. |

## Documentation Checklist

- [x] `LineRange.source_lines` documented as inclusive decoded physical source text without terminators.
- [x] Source-line decoding, BOM, replacement, and terminator-removal semantics documented.
- [x] `TraceResult` project metadata and `ProjectDiagnostic` compatibility defaults documented.
- [x] API reference and exact signatures for the three new entry points/models documented.
- [x] CLI examples use `--variable` with `--dir`, `--files`, `--manifest`, and `--recursive` only in directory mode.
- [x] Exact manifest V1 schema, validation, duplicate, relative, and absolute path rules documented.
- [x] Explicit occurrence ordering versus deterministic-but-unordered directory discovery documented.
- [x] `cross_file_unordered`, missing input, unreadable include, partial success, and no-readable-root diagnostic/exit behavior documented.
- [x] No domain-specific vocabulary introduced.

## Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Raw source text is reconstructed from statements rather than physical files | Code payload differs from user source, especially with delimiters/comments | Store/slice decoded physical source lines at parser range-record creation. |
| Source-line representation is mistaken for byte fidelity | Consumers misinterpret CRLF/BOM/malformed inputs | Define terminator-free decoded text; test LF/CRLF/BOM/replacement behavior and document it. |
| A range receives lines from a source with colliding line numbers | Incorrect code payload or coverage | Always use the range source path and source-qualified coordinates. |
| New fields break persisted consumers | Breaking public contract | Add defaulted fields only and test old JSON validation. |
| Root-level dedup fails for later include traversal | Files parse twice in project mode | Project-owned cache consulted before every root/include read and occurrence replay. |
| File-only ordering ignores include call sites | Wrong latest-definition lineage | Record/replay include occurrences at call-site sequence positions. |
| Name-only merged parent map conflates redefinitions | Ancestors include superseded definitions | Bind references to active context-qualified definition nodes before resolution. |
| Directory order is interpreted as execution order | Guessed lineage | Mark directory input unordered and emit explicit ambiguity blocks. |
| Diagnostic overlaps terminal parser disposition | No-dropped-lines invariant fails | Use defaulted non-terminal `ProjectDiagnostic`, never `UnresolvedBlock`, for project ambiguity/missing roots. |
| Project merge hides an unparsed/missing file | Silent absence | Record structured project diagnostics and define partial-result exit policy. |
| Upstream source-driver contract is unavailable or inconsistent | Source graph cannot be guaranteed | Block on `stata-registry>=0.4.0`, explicit `include_driver` metadata, `is_include()`, and upstream conformance fixtures; never infer from `variable_effect` or add local vocabulary. |
| Parser bookkeeping and emitted records drift together | Invariant falsely passes | Compute invariant terminal sets independently from persisted records. |
| CLI file-list parsing consumes the variable | Legacy/project command ambiguity | Require `--variable` for project modes and test exact grammar. |
| Optional differential environment is unavailable | External parity evidence is delayed | Keep the runner opt-in and record the skip; retain snapshots and Python regression checks, and run the corpus diff in a Stata-capable validation environment. |

## Out of Scope

- Executing Stata, evaluating expressions, resolving macro-built variable names, or inferring data values.
- YAML manifests or additional third-party parsing dependencies.
- Heuristic execution-order inference from paths, filenames, modification times, or file contents.
- Parallel parsing, persistent caches, incremental re-parsing, and multi-variable trace calls.
- Changes to `stata-command-registry` from this repository or local command-vocabulary substitutes; upstream work is an explicit external prerequisite.
- Domain-specific data, survey, institutional, or downstream-consumer behavior.

## Completion Contract

### Outcome

do2screen-py traces variables across explicit file lists, JSON manifests, and
directory corpora while preserving `trace()` behavior for single files. Every
returned `LineRange` includes exact inclusive decoded physical-line content
without terminators, and ordered cross-file lineage binds references to active
definition contexts rather than guessing from file names or merged variable names.

### Verification Surface

| ID | Phase | Evidence Required | Command/Artifact | Required |
|----|-------|-------------------|------------------|----------|
| V1 | 1 | Resolved upstream `main` revision installs `stata-registry>=0.4.0` and provides the source-driver/include capability | upstream registry conformance test, explicit metadata, reader API, and upstream-supplied include data | yes |
| V2 | 2 | Legacy JSON validates; source-line and diagnostic models round-trip losslessly | `pytest tests/test_models.py` | yes |
| V3 | 2 | Parser returns decoded terminator-free source lines for single and multi-line ranges | `pytest tests/test_parser.py tests/test_trace.py` | yes |
| V4 | 2 | Manifest V1 validation and deterministic directory discovery work | `pytest tests/test_manifest.py tests/test_ingest.py` | yes |
| V5 | 3 | Physical sources parse once and include occurrences replay at call sites | `pytest tests/test_project.py -k "cache or include_occurrence or repeated_include"` | yes |
| V6 | 3 | Project invariants, canonical provenance, diagnostics, and source-aware coverage hold | `pytest tests/test_project.py tests/test_invariant.py` | yes |
| V7 | 4 | Ordered inputs bind active definition contexts and resolve cycle-safely | `pytest tests/test_project.py -k ordered` | yes |
| V8 | 4 | Unordered inputs report non-terminal ambiguity without guessed ancestors | `pytest tests/test_project.py -k unordered` | yes |
| V9 | 5 | Exact CLI grammar preserves legacy mode and supports project modes/source-line JSON | `pytest tests/test_cli.py` | yes |
| V10 | 5 | New API/model exports import and docs reflect signatures/diagnostics | import smoke test; documentation review | yes |
| V11 | final | Full suite, build, imports, and deterministic output checks pass | `pytest && python -m build`; import and repeat-output smoke checks | yes |
| V12 | final | Optional do2screen (Stata) corpus differential comparison passes when a reference environment is available | pinned reference-diff command; otherwise recorded skip rationale | no |

### Constraints

| ID | Phase | Constraint | Check |
|----|-------|------------|-------|
| C1 | 1 | Project source-graph behavior depends only on the resolved, conformant upstream registry revision installed for the run | registry conformance test |
| C2 | 2 | Existing public fields retain their meaning and old JSON validates | `tests/test_models.py` |
| C3 | 2 | Source lines exactly match decoded, terminator-free inclusive physical coordinates | parser and trace CRLF/BOM/replacement assertions |
| C4 | 2 | No Stata command vocabulary is added locally | source review; registry conformance tests |
| C5 | 3 | Every executable physical source line is attributed or terminally unresolved, exclusively | persisted-record project invariant |
| C6 | 3 | Project diagnostics never modify terminal parser disposition; coverage/provenance use canonical `(source, line)` | project coverage/diagnostic tests |
| C7 | 4 | Cross-file order is accepted only from explicit lists/manifests and bindings target active definition contexts | ordered/unordered/redefinition fixtures |
| C8 | 5 | Output remains deterministic, offline, and one JSON document on CLI success | repeated-output and CLI tests |

### Boundaries

- Allowed: parser, models, tracing, CLI, tests, fixtures, package exports, and user documentation.
- Allowed: an upstream registry update as a separately tracked prerequisite if fixture coverage needs unavailable vocabulary.
- Out of scope: Stata execution, order inference, YAML, caches, parallelism, and domain-specific functionality.

### Iteration Policy

1. Populate terminator-free decoded source text from physical files, never reconstructed parser tokens.
2. Keep compatibility by adding only optional public fields with defaults.
3. Cache physical parses once but preserve every valid include/root occurrence in an execution stream.
4. Bind ordered references to active definition contexts; treat unspecified cross-file order as non-terminal uncertainty.
5. Stop for upstream registry source-driver capability work rather than adding command names locally or inferring from `variable_effect`. Treat the do2screen (Stata) reference runner as optional external evidence; never add Stata as a runtime or installation dependency.
6. Under `ask`, pause for approval before any necessary deviation from this plan.

### Blocked-Stop Conditions

- The resolved upstream registry revision is below `stata-registry` `0.4.0`, lacks explicit source-driver metadata, lacks `is_include()`, or fails upstream conformance data.
- Decoded terminator-free source text cannot be added without changing existing line-range semantics.
- A needed model change renames, removes, or reinterprets a public field.
- A required fixture depends on Stata vocabulary absent from the registry.
- A project trace fails the persisted-record no-dropped-lines, canonical provenance, or source-aware coverage invariant.
- Required verification fails and a fix would require heuristic ordering, local vocabulary, or another charter violation.

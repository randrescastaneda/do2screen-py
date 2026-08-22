# Work Report: Project-Wide Tracing With Source Lines

- **Plan reference**: `.cg-docs/plans/2026-08-21-project-wide-tracing-with-source-lines.md`
- **Run started**: 2026-08-21
- **Active deviation policy**: `ask` (stored; no runtime `deviate:` override)

## Run 1 (2026-08-21)

### Preflight

- Plan artifact validation passed with `cg-render-artifact --validate-only`.
- Roadmap feature `project-wide-tracing-impl` set to `active` through `@cg-roadmap`.
- Registry dependency policy now resolves the latest available upstream `main`
  revision at installation or explicit upgrade time; runtime tracing remains
  offline.
- Resolved registry revision for this run: `342f7295791bc00aad704da916a00a55763ecf5a`.

### Phase 1: Upstream Registry Prerequisite

- **Status**: in progress; gate checks pending.
- **Required evidence**: V1 (resolved upstream include capability and executable
  do2screen (Stata) reference driver).

### Blocked Stop

- **Status**: blocked.
- Existing registry conformance: passed (`3 passed`).
- Required include capability: failed. The resolved upstream `main` revision
  `342f7295791bc00aad704da916a00a55763ecf5a` installs as `stata-registry==0.3.0`
  but `callable(stata_registry.is_include)` is `False`.
- Reference-runner smoke check: not run because the first required Phase 1 gate
  failed. Earlier preflight also found no `DO2SCREEN_STATA_BIN` and no Stata
  executable in `PATH`.
- Required upstream action: add and document a callable include/nested-do
  capability plus upstream conformance data. This repository must not add local
  include command vocabulary or emulate the missing registry API.

## Run 2 (2026-08-21)

### Approved plan deviation and resume

- User approved making the do2screen (Stata) reference runner and Stata/MCP
  execution optional. This changes V1 so only the upstream registry include
  capability is required; the optional external differential evidence is now
  tracked separately as V12 and cannot block package implementation or Python
  verification.
- The package remains Stata-free at install and runtime. The do2screen (Stata)
  repository at `randrescastaneda/do2screen` is an external parity reference,
  not a dependency.
- Phase 1 resumed after the plan validation change. The registry gate remains
  blocking because the latest upstream `main` revision still lacks the formal
  include capability.

### Phase 1 blocked stop

- **Status**: blocked on the registry prerequisite only.
- Registry conformance for the existing adapter contract: passed (`3 passed`).
- Include capability: failed. The latest upstream `main` revision
  `342f7295791bc00aad704da916a00a55763ecf5a` exposes `do` and `run` as ordinary
  `none`-effect commands, but does not expose `is_include()` and does not list
  `include` as a command. The project cannot infer or hardcode that vocabulary.
- Optional Stata differential evidence: skipped, not failed. No Stata executable
  or Stata MCP tool is required for package installation, runtime, Python tests,
  or plan completion. The do2screen (Stata) repository is retained as an
  external parity reference for a Stata-capable validation environment.
- No implementation phase may continue until the upstream registry supplies the
  formal include capability and conformance data, or the plan is explicitly
  revised with an approved alternative that does not violate the registry
  boundary.

## Run 3 (2026-08-21)

### Plan revision

- User requested a ready-to-paste prompt for updating the upstream registry and
  approved revising this plan before continuing implementation.
- The prerequisite is now specified as `stata-registry>=0.4.0` with an explicit
  upstream `include_driver: bool` command-entry field, a public
  `is_include(token) -> bool` API, upstream source-driver data for `do`, `run`,
  and `include`, and release/conformance tests.
- The adapter must make that capability required for project tracing; it must
  not infer source drivers from `variable_effect` or add local command names.
- Stata/do2screen (Stata) differential execution remains optional evidence and
  is not a package or plan prerequisite.

## Run 4 (2026-08-21)

### Phase 1 resumed after upstream release

- Upstream `main` now resolves to `3820635cc4c4319382483c4158144fc60c1ddcb1`.
- Installed package version: `stata-registry==0.4.0`.
- Source-driver capability confirmed: `is_include("do")`,
  `is_include("run")`, and `is_include("include")` all return `True`.
- Phase 1 registry gate is satisfied. Stata/do2screen (Stata) differential
  execution remains optional and is not run as a package prerequisite.

The earlier blocked records remain above for auditability. The superseding
registry state for this completion run is `stata-registry==0.4.0` at upstream
revision `3820635cc4c4319382483c4158144fc60c1ddcb1`.

## Run 5 (2026-08-22)

### Resume and corrective implementation

- Re-established the workspace after the connection reset. The implementation
  was present and the pre-existing full suite passed before the final audit.
- Preserved first-requested-source provenance for partial ordered projects even
  when that first root is unreadable; added a regression test.
- Preserved within-source ancestry in unordered directory mode while still
  reporting duplicate definitions and genuinely cross-file references as
  `cross_file_unordered` diagnostics; added regression coverage.
- Added physical source-line assertions for `///` continuation and multiline
  `#delimit ;` ranges.
- Corrected documentation for rename lineage, project examples, optional
  differential execution, and the completed plan checklist.

### Verification evidence

| ID | Evidence | Result |
|----|----------|--------|
| V1 | `pytest tests/test_registry_conformance.py tests/test_dependency_config.py tests/test_upstream_shapes.py -q` | passed: 13 |
| V2 | `pytest tests/test_models.py -q` | passed: 11 |
| V3 | `pytest tests/test_parser.py tests/test_trace.py -q` | passed: 50 |
| V4 | `pytest tests/test_manifest.py tests/test_ingest.py -q` | passed: 17 |
| V5 | `pytest tests/test_project.py -k "cache or include_occurrence or repeated_include" -q` | passed: 3; 21 deselected |
| V6 | `pytest tests/test_project.py tests/test_invariant.py -q` | passed: 85 |
| V7 | `pytest tests/test_project.py -k ordered -q` | passed: 11; 13 deselected |
| V8 | `pytest tests/test_project.py -k unordered -q`; `pytest tests/test_unresolved.py -q` | passed: 5 + 11 |
| V9 | `pytest tests/test_cli.py -q` | passed: 17 |
| V10 | `cg-render-artifact --validate-only`; `cg-render-artifact --check`; `mkdocs build --strict` | passed; current plan view; docs built |
| V11 | full `pytest -q`; `python -m build`; compileall; `git diff --check`; public smoke | passed: 380; build, compile, diff, and smoke passed |
| V12 | `pytest tests/differential/test_differential.py tests/differential/test_snapshots.py -q` | snapshots passed; optional live differential skipped because `DO2SCREEN_STATA_BIN` is unset |

The final full-suite result was `380 passed, 6 skipped, 31 xfailed`. The skips
are the documented optional Stata differential and answer-key cases without
ancestor expectations. The strict xfails identify vocabulary or legacy-contract
gaps in the local mock without adding forbidden local Stata command vocabulary.

### Constraints check

- C1: passed against `stata-registry==0.4.0` and the recorded upstream revision.
- C2: passed; legacy JSON and defaulted public fields remain compatible.
- C3: passed; physical source lines are decoded, terminator-free, inclusive, and
  source-qualified.
- C4: passed; no local production command vocabulary was added.
- C5: passed by the persisted-record project invariant across the fixture corpus.
- C6: passed; project diagnostics remain separate from terminal dispositions and
  coverage uses canonical `(source, line)` pairs.
- C7: passed; ordered binding uses active contexts and unordered mode does not
  guess cross-file ancestry.
- C8: passed; output is deterministic, offline, and CLI success emits one JSON
  document.

### Optional differential and roadmap handoff

- **V12** is explicitly non-required optional evidence. No Stata executable,
  Stata MCP, or completed external do2screen (Stata) reference driver is present
  in this workspace; the Python suite and committed snapshots are the local
  parity evidence. Stata differential execution remains optional as requested.
- `roadmap.json` was already modified by the preceding workflow and remains a
  protected artifact. It was not edited directly in this run; reconcile its
  active feature status through `@cg-roadmap` in the later workflow.

### Final status

- **Status**: implementation and verification completed. All five plan phases and
  all required verification rows are complete; the optional Stata differential
  remains explicitly skipped. The plan and report are ready for review and the
  protected roadmap status is a separate workflow handoff.

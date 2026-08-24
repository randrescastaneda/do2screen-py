# Roadmap

## Current Status

**v0.1.0 Alpha** -- Core parsing, project tracing, CLI, and website are
implemented and tested.

## Completed

- [x] Core parsing pipeline (scanner, statements, grammar, parser, trace)
- [x] Differential testing infrastructure with golden files
- [x] CLI and Python API
- [x] `#delimit ;` mode switching
- [x] `///` line continuation
- [x] Include graph traversal
- [x] Recursive ancestor resolution with cycle termination
- [x] Unresolved block reporting (7 categories)
- [x] Coverage metrics
- [x] Label tracking (opt-in)
- [x] Project-wide tracing with source lines (ordered files, manifests, and
  deterministic directory discovery)

## Planned

### Cross-cutting Infrastructure

- [ ] **Publish `stata-command-registry` to PyPI with `variable_effect` support**
    The package currently installs the latest available `main` commit through
    the optional `[registry]` extra. A published compatible release would make
    normal dependency resolution possible while preserving the registry
    boundary.

- [ ] **Stata output snapshot infrastructure for CI differential testing**
    Automate running do2screen (Stata) over the test corpus and comparing
    output against do2screen-py. Offline golden/snapshot tests already exist;
    live reference execution currently requires manual Stata execution.

## Known Limitations

- **Static structural tracer only** -- no macro expansion, condition evaluation,
  or data-dependent wildcard resolution. Macro-built variable targets are
  reported as `macro_or_loop` unresolved blocks rather than guessed.

- **User-written `ado` programs** are reported as `unknown_command` unresolved
  blocks.

- **do2screen (Stata)'s `find` and `range` modes** are out of scope.

- **Delimiter/continuation output** reports physical source lines; do2screen
  (Stata) reports transformed parser-record lines there by design.

## Future Directions

- Macro expansion for variable name construction
- Data-dependent resolution (evaluating expressions to determine variable names)
- `find` and `range` modes matching do2screen (Stata) behaviour
- Improved handling of complex `if`/`else` control flow
- Support for more `#delimit` edge cases

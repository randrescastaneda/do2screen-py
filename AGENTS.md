# AGENTS.md

Operating contract for any AI agent working in this repository.

Read this file at the start of every session. If a task conflicts with anything
in the **Hard invariants** section, stop and say so rather than proceeding.

---

## 0. Naming, read this before anything else

Two projects share the name `do2screen`. Confusing them will produce wrong work.

| Refer to it as | What it is | Where |
| --- | --- | --- |
| **do2screen (Stata)** | The original Stata package. The behavioural reference. | `randrescastaneda/do2screen` |
| **do2screen-py** | This repository. The Python reimplementation. | `randrescastaneda/do2screen-py` |

Conventions inside this repository:

* PyPI distribution name: `do2screen-py`
* Python import name: `do2screen`, so `import do2screen` reads the same as the
  Stata command it mirrors
* In prose, code comments, commit messages, and issues, always write either
  "do2screen (Stata)" or "do2screen-py". Never bare `do2screen` when the
  distinction could matter.

The names are deliberately close because the two tools are meant to behave
identically. A different name would imply a different tool, and the acceptance
criterion for this package is exact agreement with the Stata original.

## 1. What this package is

`do2screen-py` traces how a variable is built inside a Stata do file. Given a
file path and a variable name, it returns the lines that create, modify, drop,
or label that variable, plus the ancestor variables it depends on, recursively.

It is a Python reimplementation of the tracing logic in do2screen (Stata), by
the same author. The reimplementation exists because the target production
environment cannot run Stata.

**This is a general purpose Stata tool.** Any Stata user should find it useful.
It has one downstream consumer today, but that consumer's domain must never
leak into this package.

## 2. What this package is not

It is not a Stata interpreter. It does not execute code, evaluate expressions,
or reason about data values. It reads text and reports structure.

It is not a semantic analyser. It does not explain what a transformation
*means*. That is a downstream concern handled by a language model outside this
package.

It knows nothing about survey harmonization, the Global Monitoring Database, the
World Bank, poverty measurement, or any specific variable name. If a proposed
change introduces vocabulary from that domain, the change belongs in a different
repository.

---

## 3. Hard invariants

These are not preferences. A change that breaks one of them is a defect
regardless of what else it improves.

### 3.1 No line is ever silently dropped

Every non blank, non comment line in a parsed file must end up in exactly one of
two places: attributed to a variable, or recorded in `unresolved_blocks`.

Silent absence is the worst possible failure of this tool. A downstream consumer
that receives an empty result cannot distinguish "this variable was never
touched" from "the parser did not understand the code." The first is
information. The second is a lie.

There is a test enforcing this invariant. Do not weaken it, do not skip it, and
do not add exemptions to it.

### 3.2 Uncertainty is reported, never guessed

When the parser cannot resolve something, it says so explicitly. Cases that must
produce an `unresolved_block` rather than a guess or an omission:

* A variable name constructed from a macro or loop index, for example
  `gen educat\`x'` inside `foreach x in 4 5 7`. A literal search for `educat4`
  will not match that line, and the parser must not conclude the variable is
  absent.
* A token that the command registry does not recognize, which usually means a
  user written `ado` program.
* A known command whose effect on the dataset this package does not model.
* An `include` or nested `do` call whose target path does not resolve.

Each unresolved block carries its line range and enough surrounding context for
a downstream consumer to interpret it.

### 3.3 The package is deterministic and offline

No network calls. No language model calls. No randomness. No wall clock or
environment dependent behaviour.

The same input file and the same registry version always produce byte identical
output. This is what makes the package testable and what makes downstream
results reproducible and auditable.

### 3.4 No hardcoded Stata command names

Command vocabulary comes from the `stata-command-registry` dependency. Do not
add a list, dict, set, or regex alternation of Stata command names anywhere in
this codebase.

If a command is missing from the registry, or its `variable_effect` annotation
is wrong, the fix is a pull request to the registry. Say so and stop. Do not
work around it locally, not even temporarily, and not even inside a test.

### 3.5 `TraceResult` is a public contract

Downstream consumers embed `TraceResult` in their own persisted records. Its
stability matters more than its convenience.

Adding an optional field is fine. Renaming, removing, or changing the meaning of
an existing field is a breaking change requiring a major version bump and an
explicit note in the changelog.

`TraceResult` must contain no vocabulary outside Stata and file structure. No
survey identifiers, no domain variable names, no institutional concepts.

---

## 4. The registry boundary

This is the most commonly misunderstood part of the design, so it is stated
explicitly.

**The registry supplies vocabulary. This package supplies grammar.**

The registry answers questions of the form "what is this word":

* Is `g` a command, and if so which one? Stata abbreviation rules are irregular
  and per command. `generate` abbreviates to `g`; `replace` cannot be
  abbreviated at all. There is no rule, only a table.
* Is `bysort` a prefix that must be stripped before classifying the statement?
* Is `foreach` control flow?
* Does this command create, modify, rename, remove, label, restructure, or leave
  the dataset alone?

This package answers questions of the form "what is the shape of this text":

* Where does a statement begin and end?
* Is this text a comment? All forms: `*`, `//`, `///`, `/* */`, inline and
  multiline.
* Is this token inside a string literal? A variable name inside quotes is not a
  reference to that variable.
* Is `#delimit ;` in effect, and where does it end?
* Does this line continue onto the next via `///`?
* Which side of an assignment is this token on?
* Is this factor variable notation, an `if` qualifier, an `in` range?

All of the second list is implemented here as parsing logic and must never
consult the registry. All of the first list is looked up and must never be
reimplemented here.

---

## 5. Testing

### 5.1 Differential testing is the primary acceptance criterion

The reference implementation exists and runs. The `tests/` directory in the
do2screen (Stata) repository contains golden file regression tests.

The strongest available check is to run do2screen (Stata) and do2screen-py over
the same corpus of do files and diff the returned line numbers. Exact match on
line sets is the pass condition. This is a rare situation where correctness can
be demonstrated rather than estimated. Use it.

Port the existing golden files before writing new ones.

### 5.2 Test cases that must exist

Beyond the ported golden files:

* The no dropped lines invariant, asserted over every fixture.
* Every unresolved block category listed in section 3.2.
* Abbreviation resolution, including commands that cannot be abbreviated.
* `#delimit ;` blocks, including a file that switches modes more than once.
* `///` continuation, including a continued line inside a `#delimit ;` block.
* All comment forms, including a `/* */` block opened and closed on the same
  line, and one spanning many lines.
* Variable names appearing inside string literals, which must not be counted.
* Prefix commands wrapping a creating command.
* Recursive ancestor resolution, including a cycle, which must terminate.
* An `include` chain, and an `include` whose target does not exist.

### 5.3 Fixtures

Prefer real Stata code over invented code. Real harmonization scripts are messier
than anything written to illustrate a point, and the messiness is the thing being
tested. Fixtures must contain no confidential data and no survey microdata.

---

## 6. Working practices

**Propose before building.** For any non trivial change, describe the parsing
approach and the Stata constructs you expect to be hardest before writing code.
The author knows Stata deeply and can catch a wrong assumption in a sentence
that would take an afternoon to catch in code.

**Prefer explicit over clever.** A long readable branch beats a compact regex.
Someone will need to reason about this code against Stata's actual behaviour, and
Stata's actual behaviour is already complicated enough.

**Small commits with a stated invariant.** Each commit message should say which
behaviour is now guaranteed that was not guaranteed before.

**Report parser limitations honestly in documentation.** A documented limitation
is a known quantity. An undocumented one is a silent failure waiting to reach
production.

**When Stata's behaviour is genuinely ambiguous, ask.** Do not pick an
interpretation and proceed. Stata has many decades of accumulated syntax
irregularities and the author is a better oracle than inference from examples.

---

## 7. Terms used in this repository

**Trace** the operation of finding all lines relevant to one variable in one
file, including its ancestors.

**Slice** the set of line ranges returned by a trace for one variable.

**Ancestor** a variable that the traced variable depends on, found by recursion.
If `income` is built from `wages` and `transfers`, both are ancestors.

**Unresolved block** a region of code the parser recognized as meaningful but
could not attribute to a specific variable, reported explicitly rather than
dropped.

**Coverage** the fraction of non blank, non comment lines in a file that were
attributed to some variable. A diagnostic, not a quality score.

**Registry** the `stata-command-registry` dependency, the single source of truth
for Stata command vocabulary, shared with `stataGlow`.

**`variable_effect`** the registry annotation describing how a command changes
the dataset: `creates`, `modifies`, `renames`, `removes`, `labels`,
`restructures`, or `none`.

---

## 8. Related repositories

| Repository | Relationship |
|---|---|
| `do2screen` (Stata) | The reference implementation. The behavioural specification for this package. |
| `stata-command-registry` | Upstream dependency. Command vocabulary. |
| `stataGlow` | Sibling consumer of the registry. Not a dependency of this package. |

Downstream consumers exist but are deliberately not named here. This package
must remain useful and testable without any of them.
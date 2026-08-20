# Examples

All examples use the test fixtures shipped with the package. The Stata code is
real and intentionally unpolished -- real harmonization scripts are messier than
toy examples, and the messiness is what the parser must handle.

---

## 1. Basic Variable Trace

Trace `income` through `sample.do`, which builds income from wage and transfer
components and then renames it.

**Stata code** (`tests/fixtures/sample.do`):

```stata
* Sample: build total income from wage and transfer components.
gen wages = 1200
gen transfers = 300
gen income = wages + transfers
rename income total_income
replace total_income = total_income * 1.05
label variable total_income "Total household income"
```

=== "CLI"

    ```sh
    do2screen tests/fixtures/sample.do income
    ```

=== "Python"

    ```python
    from do2screen import trace

    result = trace("tests/fixtures/sample.do", "income")
    print(result.model_dump_json(indent=2))
    ```

**Result:**

- `ranges`: line 4 (where `income` is created by `gen income = wages + transfers`)
- `ancestors`: `["wages", "transfers"]` -- the two variables `income` depends on
- `coverage`: 1.0 -- every executable line is attributed to some variable
- The `rename` on line 5 is attributed to `income` (the variable is renamed, not
  dropped and re-created)

---

## 2. Rename Chain Tracking

Trace `new_name` through `rename.do`, which creates `old_name`, modifies it,
renames it to `new_name`, then uses it.

**Stata code** (`tests/fixtures/rename.do`):

```stata
* Rename target and source bookkeeping.
gen old_name = 5
replace old_name = old_name + 1
rename old_name new_name
gen out = new_name * 2
```

=== "CLI"

    ```sh
    do2screen tests/fixtures/rename.do new_name
    ```

=== "Python"

    ```python
    from do2screen import trace

    result = trace("tests/fixtures/rename.do", "new_name")
    print(result.ancestors)
    ```

**Result:**

- `ranges`: line 2 (created as `old_name`), line 3 (modified as `old_name`),
  line 4 (renamed to `new_name`)
- `ancestors`: `[]` -- `new_name` has no upstream dependencies beyond `old_name`,
  which *is* `new_name` after the rename

The rename is tracked as a single lineage: `old_name` becomes `new_name`, so all
prior lifecycle events belong to the same variable.

---

## 3. Include Graph Traversal

Trace `income` through `include_root.do`, which includes `inc/lib.do` and then
uses a variable defined there.

**Stata code** (`tests/fixtures/include_root.do`):

```stata
* Include chain: the child file supplies bonus, the root consumes it.
include "inc/lib.do"
gen income = bonus + 1
```

**Child file** (`tests/fixtures/inc/lib.do`):

```stata
* Child file included by include_root.do.
gen bonus = 100
replace bonus = bonus * 2
```

=== "CLI"

    ```sh
    do2screen tests/fixtures/include_root.do income
    ```

=== "Python"

    ```python
    from do2screen import trace

    result = trace("tests/fixtures/include_root.do", "income")
    print(result.sources)
    ```

**Result:**

- `ranges`: line 3 of the root file (where `income` is created)
- `ancestors`: `["bonus"]` -- defined in the included file
- `sources`: two `SourceProvenance` entries, one per file, in traversal order
- `attributed_ranges` includes ranges from both files

The parser resolves the include path relative to the root file and attributes
code in `inc/lib.do` to its own source, not the root.

---

## 4. Handling Unresolved Blocks (Macros)

Trace `educat4` through `unres_macro.do`, which builds variable names from a
macro inside a `foreach` loop.

**Stata code** (`tests/fixtures/unres_macro.do`):

```stata
* Macro-built variable in an enclosing loop: the whole block is unresolved.
foreach x in 4 5 7 {
    gen educat`x' = 1
    replace educat`x' = educat`x' * 2
}
```

=== "CLI"

    ```sh
    do2screen tests/fixtures/unres_macro.do educat4
    ```

=== "Python"

    ```python
    from do2screen import trace

    result = trace("tests/fixtures/unres_macro.do", "educat4")
    print(result.ranges)         # empty -- variable not found
    print(result.unresolved_blocks)
    ```

**Result:**

- `ranges`: `[]` -- the literal string `educat4` never appears; the macro
  `` `x' `` constructs it at runtime
- `unresolved_blocks`: one block with reason `macro_or_loop`, covering the
  entire `foreach` block
- `coverage`: 0.0 -- the executable lines are in an unresolved block and
  cannot be attributed

This is the correct behaviour: the parser reports what it could not resolve
rather than guessing or silently dropping the code.

---

## 5. Prefix Commands

Trace `rank` through `prefixes.do`, which uses `bysort` as a command prefix.

**Stata code** (`tests/fixtures/prefixes.do`):

```stata
* Prefix commands wrap a creating command.
gen region = 1
bysort region: gen rank = 1
sort region
replace rank = rank + 1
```

=== "CLI"

    ```sh
    do2screen tests/fixtures/prefixes.do rank
    ```

=== "Python"

    ```python
    from do2screen import trace

    result = trace("tests/fixtures/prefixes.do", "rank")
    print(result.ranges)
    ```

**Result:**

- `ranges`: line 3 (`gen rank = 1` with `bysort` prefix), line 5 (`replace rank`)
- The `bysort region:` prefix is stripped before classifying the inner statement
  as a `gen` (creates). The `sort` on line 4 is classified as `none` (does not
  create, modify, or remove any variable).

---

## 6. Delimiter Switching

Trace `d1` through `delimit.do`, which switches between `#delimit cr` and
`#delimit ;` multiple times.

**Stata code** (`tests/fixtures/delimit.do`):

```stata
* Delimiter mode switching, including multiple switches.
gen d1 = 1
#delimit ;
gen d2 = 2;
replace d2 = d2 + 1;
#delimit cr
gen d3 = 3
#delimit ;
replace d3 = 4;
#delimit clear
gen d4 = d3 + 1
```

=== "CLI"

    ```sh
    do2screen tests/fixtures/delimit.do d1
    ```

=== "Python"

    ```python
    from do2screen import trace

    result = trace("tests/fixtures/delimit.do", "d1")
    print(result.ranges)
    ```

**Result:**

- `ranges`: line 2 (`gen d1 = 1`)
- The `#delimit ;` blocks are parsed correctly: statements inside the block are
  terminated by `;` until `#delimit cr` or `#delimit clear` resets the mode
- The file switches delimiter mode twice; the parser handles all transitions

---

## 7. No-Follow-Parents Mode

Disable ancestor resolution to see only the traced variable's own ranges.

**Stata code** (`tests/fixtures/lineage.do`):

```stata
* Recursive lineage: primary <- adult <- person
gen person = 1
gen adult = person
gen primary = adult
replace primary = primary * 2
```

=== "CLI"

    ```sh
    do2screen tests/fixtures/lineage.do primary --no-follow-parents
    ```

=== "Python"

    ```python
    from do2screen import trace

    result = trace("tests/fixtures/lineage.do", "primary", follow_parents=False)
    print(result.ancestors)  # []
    ```

**Result:**

- `ancestors`: `[]` -- ancestor resolution is disabled
- `ranges`: lines 4 and 5 (the `gen` and `replace` for `primary`)
- `attributed_ranges`: still contains the full audit inventory for all variables
  in the file

Use `--no-follow-parents` when you want the line ranges without the dependency
graph, for example when the downstream consumer only needs the source lines.

---

## 8. Label Tracking

Include `label variable` events in the trace by enabling the `--labels` flag.

**Stata code** (`tests/fixtures/labels.do`):

```stata
* Label events: label variable (value labels attach a label name, not a
* data variable, so label value is excluded from this fixture).
gen income = 1
label variable income "Monthly income"
gen other = income * 2
```

=== "CLI"

    ```sh
    do2screen tests/fixtures/labels.do income --labels
    ```

=== "Python"

    ```python
    from do2screen import trace

    result = trace("tests/fixtures/labels.do", "income", include_labels=True)
    print(result.ranges)
    ```

**Result:**

- `ranges`: line 2 (`gen income = 1`), line 3 (`label variable income`)
- Without `--labels`, the label event on line 3 is excluded from the traced
  ranges (but still present in `attributed_ranges` as a `labelled` kind)

!!! note
    By default, label events are excluded from lifecycle ranges to match the
    behaviour of do2screen (Stata). Use `--labels` / `include_labels=True` when
    you need them.

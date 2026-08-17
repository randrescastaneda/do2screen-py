* Macro-built variable in an enclosing loop: the whole block is unresolved.
foreach x in 4 5 7 {
    gen educat`x' = 1
    replace educat`x' = educat`x' * 2
}
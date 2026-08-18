* Unterminated structures run through EOF.
foreach x in 1 2 {
    replace v`x' = 1
* no closing brace
/* unterminated block comment from here...
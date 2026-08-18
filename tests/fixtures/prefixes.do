* Prefix commands wrap a creating command.
gen region = 1
bysort region: gen rank = 1
sort region
replace rank = rank + 1
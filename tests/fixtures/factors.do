* Factor variables and if/in qualifiers are excluded from parents.
gen age = 30
gen region = 1
gen wi = 10
gen weight = 20
replace age = age + 1 if region == 1
gen adj = age in 1/2
gen rate = 2 * wi[1]
replace rate = L.weight + F.weight
gen out = age * 2
gen factorsum = i.age + c.age#i.region
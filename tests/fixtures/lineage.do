* Recursive lineage: primary <- adult <- person
gen person = 1
gen adult = person
gen primary = adult
replace primary = primary * 2
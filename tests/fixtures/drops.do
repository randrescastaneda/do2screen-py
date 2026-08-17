* Drop varlists and drop _all.
gen keepme = 1
gen dropme = 2
gen also_drop = 3
drop dropme also_drop
drop _all
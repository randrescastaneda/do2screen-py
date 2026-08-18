* Rename target and source bookkeeping.
gen old_name = 5
replace old_name = old_name + 1
rename old_name new_name
gen out = new_name * 2
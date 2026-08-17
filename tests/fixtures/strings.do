* Variable names inside strings and compound strings must be ignored.
gen inc = 1
label variable inc "total income including transfers"
gen note = "wages are excluded"
gen cmd = `"the sum of inc and wages"'
gen out = inc * 2
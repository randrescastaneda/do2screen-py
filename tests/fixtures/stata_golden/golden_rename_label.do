* Golden: rename and label events in variables mode.
* (Ported from do2screen (Stata) fixture patterns; upstream commit
*  8ac7de8c7e8e33d73c05ac0cca29861312fdc640.)
gen household_size = 4
rename household_size hhsize
replace hhsize = hhsize + 1
label variable hhsize "Persons in household"
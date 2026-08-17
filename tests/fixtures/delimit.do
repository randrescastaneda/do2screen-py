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
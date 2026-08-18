* Golden: variables-mode lineage, one-to-one physical source lines.
* (Ported from do2screen (Stata) fixture patterns; upstream commit
*  8ac7de8c7e8e33d73c05ac0cca29861312fdc640.)
gen wages = 1500
gen transfers = 400
gen income = wages + transfers
replace income = income * 1.1
drop wages
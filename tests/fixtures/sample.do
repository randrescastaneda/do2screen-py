* Sample: build total income from wage and transfer components.
gen wages = 1200
gen transfers = 300
gen income = wages + transfers
rename income total_income
replace total_income = total_income * 1.05
label variable total_income "Total household income"
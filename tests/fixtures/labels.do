* Label events: label variable (value labels attach a label name, not a
* data variable, so label value is excluded from this fixture).
gen income = 1
label variable income "Monthly income"
gen other = income * 2
* gen(identifier) option: the option variable is the created target and the
* pre-option variable list supplies the inputs.
generate groupmean, gen(avg_wage)
replace groupmean = 1
gen mean = avg_wage * 1
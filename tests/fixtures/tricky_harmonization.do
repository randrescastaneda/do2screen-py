*==============================================================================
* Adversarial test fixture for do2screen-py
*
* Every construct here is deliberate. This file is NOT valid harmonization
* logic and must never be run against data. Its only purpose is to exercise
* parser edge cases where the correct answer is known in advance.
*
* Companion answer key: tricky_harmonization_expected.yaml
*==============================================================================

clear all
set more off

use "raw/hh_survey_2019.dta", clear


*------------------------------------------------------------------------------
* SECTION 1. Substring hazard
* A trace of "educ" must match ONLY educ. Not educat, educat4, educat7,
* educat7_orig. This is the single most common false positive in naive
* implementations.
*------------------------------------------------------------------------------

gen byte educ = p301a
gen byte educat = .
generate byte educat4 = .
g byte educat5 = .
gen byte educat7 = .
gen byte educat7_orig = p301a


*------------------------------------------------------------------------------
* SECTION 2. Abbreviation resolution
* g, gen, generate are the same command. replace cannot be abbreviated in
* Stata, so "rep" below is NOT a command and must not be read as one.
*------------------------------------------------------------------------------

replace educat7 = 1 if p301a == 1
replace educat7 = 2 if inlist(p301a, 2, 3) & p301b < 6
replace educat7 = 3 if inlist(p301a, 2, 3) & p301b >= 6


*------------------------------------------------------------------------------
* SECTION 3. Comment forms
* The * below is a comment only because it starts the line. The * inside the
* expression on the following line is multiplication.
*------------------------------------------------------------------------------

* educat7 is mentioned here but this line must not be attributed to it
gen double wage_hourly = wage_monthly / (hours_week * 4.33)
gen double wage_daily = wage_hourly * 8   // educat7 mentioned in trailing comment
/* educat7 mentioned inside a block comment on one line */
gen byte urban = .
/*
   educat7 mentioned inside a multiline block comment
   spanning several lines
*/
replace urban = 1 if strata == 1


*------------------------------------------------------------------------------
* SECTION 4. String literals
* Variable names inside quotes are not references.
*------------------------------------------------------------------------------

label var educat7 "educat7: highest level attained"
di "now building educat4 and educat5"
gen str8 source_note = "derived from educat7"


*------------------------------------------------------------------------------
* SECTION 5. Line continuation
*------------------------------------------------------------------------------

gen byte educat4 = ///
    1 if educat7 <= 2

replace educat4 = 2 ///
    if inrange(educat7, 3, 4) ///
    & age >= 15


*------------------------------------------------------------------------------
* SECTION 6. Prefix commands
* The creating command is not the first token on the line.
*------------------------------------------------------------------------------

bysort hhid: gen byte hhsize = _N
bys hhid: egen byte n_children = total(age < 15)
quietly gen byte head = (relationharm == 1)
capture drop hhsize_check
qui replace head = 0 if missing(relationharm)
by hhid: replace hhsize = . if hhsize > 30


*------------------------------------------------------------------------------
* SECTION 7. Macro built variable names
* A literal search for educat_lev4 finds nothing. The parser must report an
* unresolved block, never absence.
*------------------------------------------------------------------------------

foreach x in 4 5 7 {
    gen byte educat_lev`x' = .
    replace educat_lev`x' = educat`x'
}

local targets "male female"
foreach v of local targets {
    gen byte flag_`v' = 0
}

forvalues i = 1/5 {
    gen byte quintile_`i' = (welfare_q == `i')
}

local newvar = "computed_income"
gen double `newvar' = wage_monthly + transfers


*------------------------------------------------------------------------------
* SECTION 8. Rename chains and ancestry
* final_educ traces back through educat7 to p301a and p301b.
*------------------------------------------------------------------------------

gen byte tmp_educ = educat7
rename tmp_educ educ_stage1
replace educ_stage1 = 9 if missing(educ_stage1)
rename educ_stage1 final_educ
replace final_educ = final_educ + 0


*------------------------------------------------------------------------------
* SECTION 9. Self reference and cycles
* The recursion must terminate.
*------------------------------------------------------------------------------

gen double income_total = wage_monthly
replace income_total = income_total + transfers
replace income_total = income_total * 12


*------------------------------------------------------------------------------
* SECTION 10. recode, with and without generate()
* Without generate() recode modifies in place. With it, recode creates.
*------------------------------------------------------------------------------

recode educat7 (4 5 = 4) (6 7 = 5)
recode educat7 (1 2 = 1) (3 4 = 2), generate(educat5_alt)


*------------------------------------------------------------------------------
* SECTION 11. egen, destring, encode, labels
*------------------------------------------------------------------------------

egen double hh_income = total(income_total), by(hhid)
egen byte max_educ = max(educat7), by(hhid)
destring region_str, generate(region_num)
encode province_str, gen(province_code)
label define lbl_urban 0 "Rural" 1 "Urban"
label values urban lbl_urban


*------------------------------------------------------------------------------
* SECTION 12. Restructuring commands
*------------------------------------------------------------------------------

merge m:1 hhid using "raw/hh_roster.dta", keep(master match) nogen
merge 1:1 hhid pid using "raw/labor_module.dta"
drop if _merge == 2
drop _merge


*------------------------------------------------------------------------------
* SECTION 13. Factor variable notation and references
* i.educat7 is a reference, not a modification.
*------------------------------------------------------------------------------

regress lnwelfare i.educat7 age i.urban
summarize educat7 if urban == 1
su educat4, detail
tabulate educat7 urban, row


*------------------------------------------------------------------------------
* SECTION 14. Unknown commands
* gmd_apply_labels is a team written ado not in the registry. It may or may
* not touch variables. The parser cannot know, so it must flag, not guess.
*------------------------------------------------------------------------------

gmd_apply_labels educat7 urban male
gmd_validate_ranges, varlist(age educat7)


*------------------------------------------------------------------------------
* SECTION 15. Delimiter switching
*------------------------------------------------------------------------------

#delimit ;

gen byte male =
    (sex == 1) ;

replace male = .
    if missing(sex) ;

gen byte age_group = 1 ; replace age_group = 2 if age >= 15 ;

#delimit cr

gen byte back_to_cr = 1


*------------------------------------------------------------------------------
* SECTION 16. Includes
*------------------------------------------------------------------------------

include "shared/common_labels.do"
do "shared/does_not_exist.do"


*------------------------------------------------------------------------------
* SECTION 17. Drop and keep
*------------------------------------------------------------------------------

drop educat7_orig tmp_flag
keep hhid pid age male urban educat7 educat4 final_educ

save "harmonized/hh_2019_gmd.dta", replace

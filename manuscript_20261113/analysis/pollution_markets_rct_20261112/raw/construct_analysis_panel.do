/*******************************************************************************
	   Authors: Dipika Gawande
	   Project: ETS
	   Purpose: Construct the analysis panel data set

	   Date created: 25 November 2020
	   Version:      STATA 15 MP

	   Last edited: 2 June 2022
	   Edited by:   Jeanne, Vineet, Kaixin
   ****************************************************************************/

set more off
clear matrix
clear all
pause on

local RuleNo "`1'"
// local RuleNo "0"
// local RuleNo "A"
// local RuleNo "B"

********************************************************************************
********** [1] MERGE DATA SETS TO CONSOLIDATE DEP VARS AND COVARIATES **********
********************************************************************************

** MERGE IN THE DEPENDENT VARIABLE (PLANT-MONTH KG) FROM MEAN IMPUTATION RULE
use "$IMPUTATION_DATA_OUT/PlantMonthPMMassRule`RuleNo'.dta", clear

** MERGE IN BASELINE COVARIATES
sort industry_id
** 26/7034 unmatched coming from Baseline
merge m:1 industry_id using "$BASELINE_DATA_OUT/BaselineCovariates.dta"
tab _m
keep if _m == 3
drop _m

** RESTRICT THE SAMPLE TO START 16 APR 2019
drop if month16 < date("2019apr16", "YMD")

if "`RuleNo'" != "M" {
	
	forvalues i=0(1)9{	
		
		rename ind_month_mass_val_rule`i' Y_rule`i'
		label var Y_rule`i' "Plant Month Mass (kg) - trunc rule `i'"
		
	}
}
else {
	
	forvalues i=0(1)9{	
		
		foreach imprule in mkt p50 p55 p60 p65 p70 p75 p80 p85 p90 p95 {
		
			rename ind_month_mass_val_rule_`imprule'_`i' Y_rule_`imprule'_`i'
			label var Y_rule_`imprule'_`i' "Plant Month Mass (kg) - trunc rule `i'"
		
		}
		
	}
	
}


sort gpcb_id month16

********************************************************************************
******************** [2] MAKE INTERREGNUM AND POST DUMMIES *********************
********************************************************************************

** Generate interregnum dummy for period 16-Mar-2020 to 15-Oct-2020, 
** and month of 16-Nov-2020 (market was off for 2 weeks for Diwali in Nov 2020).
gen D_interregnum = (month16 >= date("2020mar16", "YMD") & month16 <= date("2020sep16", "YMD")) | /// 
	month16 == date("2020nov16", "YMD")
label var D_interregnum "Interregnum"

** Generate Mock 1: 16-Jul-2019 to 15-Sep-2019
gen Mock1 = (month16 == date("2019jul16", "YMD") | month16 == date("2019aug16", "YMD") )
label var Mock1 "Mock Trading 1 (pre-Covid)"

** Generate Mock 2: 16-Oct-2020 to 15-Nov-2020
gen Mock2 = month16 == date("2020oct16", "YMD")
label var Mock2 "Mock Trading 2 (post-Covid)"	

** Post1 is pre-interregnum only. 
** 16-Jul-2019 to 15-Mar-2020.
gen post_mock1 = month16 >= date("2019jul16", "YMD") & month16 <= date("2020feb16", "YMD")
label var post_mock1 "Post 1 (pre-Interregnum only)"

** Post2 is post-interregnum only. 
** 16-Oct-2020 to 15-Nov-2020 & 16-Dec-2020 to 15-Feb-2021
gen post_mock2 = month16 == date("2020oct16", "YMD") | month16 >= date("2020dec16", "YMD")
label var post_mock2 "Post 2 (post-Interregnum only)"

tab month16 post_mock1
tab month16 post_mock2

********************************************************************************
************************ [3] MAKE MONTH CAP & LOG VARS *************************
********************************************************************************

gen month_cap = 280000 if month16 >= td(16jul2019)
replace month_cap = 200000 if month16 >= td(16oct2019)
replace month_cap = 180000 if month16 >= td(16nov2019)
replace month_cap = 170000 if month16 >= td(01jan2020)
label var month_cap "Month Cap (per Treatment Group)"

** GENERATE LOG DEPENDENT VAR AND LOG COVARIATES

** 10 rules: truncate at 99perc and 99.5perc at the monthly level for each of
** 5 sample restrictions (full, first 100, online by june, first 90, online by july)
** Code generating this: ETS/Data/ETS Analysis - 2020/2. Updated Version (June 2021)/2. Essential CEMS Working Data/0. Code/2b. 337 Stacks - Calibrated Stack-day Balanced STEM_v7.do
if "`RuleNo'" != "M" {
	
	forvalues i=0(1)9{
		
		gen lnY_rule`i' = ln(Y_rule`i')
		label var lnY_rule`i' "Y=Ln(Plant Month PM Mass (kg) - trunc rule `i')"
		
	}
}
else {
	
	forvalues i=0(1)9{	
		
		foreach imprule in mkt p50 p55 p60 p65 p70 p75 p80 p85 p90 p95 {
		
			gen lnY_rule_`imprule'_`i' = ln(Y_rule_`imprule'_`i')
			label var lnY_rule_`imprule'_`i' "Y=Ln(Plant Month PM Mass (kg) - trunc rule `i')"

		
		}
		
	}
	
}



********************************************************************************
********************** [4] CHECK DATA SET AND LABEL VARS ***********************
********************************************************************************

** CHECKING DATA SET

** Used gpcb_id instead of industry_id because it's numeric. 
** gpcb_id and industry_id are uniquely identified 1-to-1; use them interchangeably.
duplicates r gpcb_id month16 	
tab D_treatment treatmentstatus

** LABELING VARS
order industry_id, a(gpcb_id)
order industry_name, a(industry_id)
label var industry_id "Industry ID (str)"
label var gpcb_id "GPCB ID (num)"
label var D_treatment "ETS Treatment"
cap: label var Y_rule0 "PM/Month"
cap: label var Y_rule1 "PM/Month"
cap: label var lnY_rule0 "log(PM/Month)"
cap: label var lnY_rule1 "log(PM/Month)"

sort gpcb_id month16
save "$EMISSIONS_DATA_OUT/Rule`RuleNo'_Panel.dta", replace

********************************************************************************
***************************** [5] CREATES WEIGHTS ******************************
********************************************************************************

if "`RuleNo'" == "0" {

	** GENERATE CEMS PHASE INDICATOR
	encode cems_phase, gen(cems_phase_factor)
	gen CEMS_3_4 = (cems_phase_factor == 3 | cems_phase_factor == 4)
	label var CEMS_3_4 "CEMS Phase 3 or 4"

	** Foreach month create a reporting dummy
	local levels "apr2019 jul2019 oct2019 jan2020"
	foreach l of local levels {
		gen online_16`l' = (month16 == td("16`l'") & !missing(Y_rule0))
		bysort gpcb_id: egen online_16`l'_ind = max(online_16`l')
	}
	label var online_16apr2019_ind "Online Apr 2019"
	label var online_16jul2019_ind "Online Jul 2019"
	label var online_16oct2019_ind "Online Oct 2019"
	label var online_16jan2020_ind "Online Jan 2020"

	** Collapse at the plant level (292 observations)
	keep gpcb_id industry_id D_treatment online_*_ind CEMS_3_4 
	duplicates drop
	global cov_interest_weight = "CEMS_3_4"	
	global months_subset "online_16jul2019_ind online_16oct2019_ind online_16jan2020_ind"

	foreach yvar of varlist $months_subset { 

		tab `yvar'

		* Compute probit
		eststo reg_`yvar': probit `yvar' $cov_interest_weight
		estadd local missingcov "Yes"
		estadd local model "Probit"

		* predict
		predict `yvar'_hat

		* construct weight
		qui sum `yvar'
		local S_unc = r(mean)
		gen newweight1_`yvar' = `S_unc' / `yvar'_hat 

		* generate new var with coef
		gen coef_CEMS_`yvar' = _b[CEMS_3_4]

	}

	keep gpcb_id *_hat newweight1_*
	tempfile weights_file
	save `weights_file'

	** MERGE TO FULL DATA
	use "$EMISSIONS_DATA_OUT/Rule`RuleNo'_Panel.dta", clear
	merge m:1 gpcb_id using `weights_file'
	gen newweight = newweight1_online_16oct2019
	replace newweight = newweight1_online_16jul2019 if month16 <= date("October 1 2019","MDY")
	replace newweight = newweight1_online_16jan2020 if month16 >= date("January 1 2020","MDY")
	bysort month16: egen sum_newweight = sum(newweight)
	gen newweight_normalized = newweight / sum_newweight
	bysort month16: egen sum_newweight_nom = sum(newweight_normalized)
	assert sum_newweight_nom == 1
	drop _merge sum_newweight sum_newweight_nom
	sort gpcb_id month16

	save "$EMISSIONS_DATA_OUT/Rule`RuleNo'_Panel.dta", replace

}

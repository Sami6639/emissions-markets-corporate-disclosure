/*******************************************************************************
Purpose: Create the main regression table
****************************************************************************/

set more off 
clear matrix
clear all
pause on

local yvar "lnY_rule0"

** Construct monthly DA for use in DA regression versions
use "$EMISSIONS_DATA_IN/CEMS_2018-12-31 to 2021-04-03_StackDay_Balanced_HistCFs_Master337s_3sample2trunc.dta", clear
collapse stack_DA_day, by(gpcb_id month16)
replace stack_DA_day = 0 if missing(stack_DA_day)
tempfile month_ind_da
save `month_ind_da'

foreach include_DA_cov in 0 1 {
	local table_name Table_3
	local cov_interest "ln_capex D_ln_capex_missing boi_year D_boi_year_missing bh_ope_cost D_bh_ope_cost_missing ln_plant_total_heatoutput"
	use "$EMISSIONS_DATA_OUT/Rule0_Panel.dta", clear
	keep if D_interregnum == 0
	keep if post_mock1 == 1 | post_mock2 == 1
	sum `yvar' if D_treatment == 1

	if `include_DA_cov' == 1 {
		local table_name Table_F5
		local cov_interest "`cov_interest' stack_DA_day"
		merge 1:1 gpcb_id month16 using `month_ind_da'
		keep if _merge!=2
		drop _merge
		}

********************************************************************************
**************************** Panel 0 - Unweighted ******************************
********************************************************************************
*use "$EMISSIONS_DATA_OUT/Rule0_Panel.dta", clear
*keep if D_interregnum == 0
*keep if post_mock1 == 1 | post_mock2 == 1

** Column 1: treatment dummy & plant covariates
	eststo reg_1: reg `yvar' 1.D_treatment `cov_interest', clus(gpcb_id)
	estadd local Month_FE ""
	estadd local Reweighted ""
	estadd local Imp_Rule ""
	estadd local N_Plants = e(N_clust)
	sum `yvar' if D_treatment == 0
	estadd local Ctrl_Mean = string(r(mean), "%15.2f")
	estadd local space ""

** Column 2: treatment dummy & plant covariates & month FE
	eststo reg_2: reghdfe `yvar' 1.D_treatment `cov_interest', a(i.month16) clus(gpcb_id)
	estadd local Month_FE "Yes"
	estadd local Reweighted ""
	estadd local Imp_Rule ""
	estadd local N_Plants = e(N_clust)
	sum `yvar' if D_treatment == 0
	estadd local Ctrl_Mean = string(r(mean), "%15.2f")
	estadd local space ""

********************************************************************************
**************************** Panel 0 - Reweighted ******************************
********************************************************************************

** Column 3: treatment dummy & plant covariates
	eststo reg_3: reg `yvar' 1.D_treatment `cov_interest' [pw=newweight_normalized], clus(gpcb_id)
	estadd local Month_FE ""
	estadd local Reweighted "Yes"
	estadd local Imp_Rule ""
	estadd local N_Plants = e(N_clust)
	sum `yvar' [aw=newweight_normalized] if D_treatment == 0
	estadd local Ctrl_Mean = string(r(mean), "%15.2f")
	estadd local space ""

** Column 4: treatment dummy & plant covariates & month FE
	eststo reg_4: reghdfe `yvar' 1.D_treatment `cov_interest' [pw=newweight_normalized], a(i.month16) clus(gpcb_id)
	estadd local Month_FE "Yes"
	estadd local Reweighted "Yes"
	estadd local Imp_Rule ""
	estadd local N_Plants = e(N_clust)
	sum `yvar' [aw=newweight_normalized] if D_treatment == 0
	estadd local Ctrl_Mean = string(r(mean), "%15.2f")
	estadd local space ""

********************************************************************************
*********************************** Panel A ************************************
********************************************************************************

	use "$EMISSIONS_DATA_OUT/RuleA_Panel.dta", clear
	keep if D_interregnum == 0
	keep if post_mock1 == 1 | post_mock2 == 1
	sum `yvar' if D_treatment == 1
	if `include_DA_cov' == 1 {
		merge 1:1 gpcb_id month16 using `month_ind_da'
		keep if _merge!=2
		drop _merge
		}
		
	preserve
	rename `yvar' `yvar'_RuleA
	tempfile RuleA_Panel
	save `RuleA_Panel'
	restore

** Column 5: treatment dummy & plant covariates
	eststo reg_5: reg `yvar' 1.D_treatment `cov_interest', clus(gpcb_id)
	estadd local Month_FE ""
	estadd local Reweighted ""
	estadd local Imp_Rule "Rule A"
	estadd local N_Plants = e(N_clust)
	sum `yvar' if D_treatment == 0
	estadd local Ctrl_Mean = string(r(mean), "%15.2f")
	estadd local space ""

** Column 6: treatment dummy & plant covariates & month FE
	eststo reg_6: reghdfe `yvar' 1.D_treatment `cov_interest', a(i.month16) clus(gpcb_id)
	estadd local Month_FE "Yes"
	estadd local Reweighted ""
	estadd local Imp_Rule "Rule A"
	estadd local N_Plants = e(N_clust)
	sum `yvar' if D_treatment == 0
	estadd local Ctrl_Mean = string(r(mean), "%15.2f")
	estadd local space ""

********************************************************************************
*********************************** Panel B ************************************
********************************************************************************

	use "$EMISSIONS_DATA_OUT/RuleB_Panel.dta", clear
	keep if D_interregnum == 0
	keep if post_mock1 == 1 | post_mock2 == 1
	sum `yvar' if D_treatment == 1
	if `include_DA_cov' == 1 {
		merge 1:1 gpcb_id month16 using `month_ind_da'
		keep if _merge!=2
		drop _merge
		}

** Column 7: treatment dummy & plant covariates
	eststo reg_7: reg `yvar' 1.D_treatment `cov_interest', clus(gpcb_id)
	estadd local Month_FE ""
	estadd local Reweighted ""
	estadd local Imp_Rule "Rule B"
	estadd local N_Plants = e(N_clust)
	sum `yvar' if D_treatment == 0
	estadd local Ctrl_Mean = string(r(mean), "%15.2f")
	estadd local space ""

** Column 8: treatment dummy & plant covariates & month FE
	eststo reg_8: reghdfe `yvar' 1.D_treatment `cov_interest', a(i.month16) clus(gpcb_id)
	estadd local Month_FE "Yes"
	estadd local Reweighted ""
	estadd local Imp_Rule "Rule B"
	estadd local N_Plants = e(N_clust)
	sum `yvar' if D_treatment == 0
	estadd local Ctrl_Mean = string(r(mean), "%15.2f")
	estadd local space ""
	
********************************************************************************
************************************ Output ************************************
********************************************************************************

	if `include_DA_cov' == 1 {

	esttab reg_* ///
	  using "$EMISSIONS_TABS/`table_name'.tex", replace ///
	  se(3) ar2 booktabs varwidth(32) ///
	  keep(1.D_treatment stack_DA_day) coeflabel(1.D_treatment "ETS Treatment (=1)" stack_DA_day "Share of Day Reporting") ///
	  mgroups("\shortstack{No Imputed Months}" "\shortstack{Imputed Months}", pattern(1 0 0 0 1 0 0 0) ///
		  prefix(\multicolumn{@span}{c}{) suffix(}) span erepeat(\cmidrule(lr){@span})) ///
	  nomtitles ///
	  stats(Month_FE space Imp_Rule Reweighted Ctrl_Mean r2 N_Plants N, ///
		  label("Year-Month FE" " " "Imputation rule" "Reweighted" "Mean dep. var (control)" "R\textsuperscript{2}" "Plants" "Observations" ) ///
		  fmt(%1s %1s %1s %1s %9.2f %9.2f 0 0)) ///
	  prefoot(" ") ///
	  star(* 0.10 ** 0.05 *** 0.01) nonotes
	  
	  /*
	  esttab reg_* MOC_* ///
	  using "$EMISSIONS_TABS/MOC_`table_name'.tex", replace ///
	  se(3) ar2 booktabs varwidth(32) ///
	  keep(1.D_treatment stack_DA_day) coeflabel(1.D_treatment "ETS Treatment (=1)" stack_DA_day "Share of Day Reporting") ///
	  mgroups("\shortstack{No Imputed Months}" "\shortstack{Imputed Months}", pattern(1 0 0 0 1 0 0 0 0 ) ///
		  prefix(\multicolumn{@span}{c}{) suffix(}) span erepeat(\cmidrule(lr){@span})) ///
	  nomtitles ///
	  stats(Month_FE space Imp_Rule Reweighted Ctrl_Mean r2 N_Plants N, ///
		  label("Month FE" " " "Imputation rule" "Reweighted" "Mean dep. var (control)" "R\textsuperscript{2}" "Plants" "Observations" ) ///
		  fmt(%1s %1s %1s %1s %9.2f %9.2f 0 0)) ///
	  prefoot(" ") ///
	  star(* 0.10 ** 0.05 *** 0.01) nonotes
	  */

		}
	else {

	esttab reg_* ///
	  using "$EMISSIONS_TABS/`table_name'.tex", replace ///
	  se(3) ar2 booktabs varwidth(32) ///
	  keep(1.D_treatment) coeflabel(1.D_treatment "ETS Treatment (=1)") ///
	  mgroups("\shortstack{No Imputed Months}" "\shortstack{Imputed Months}", pattern(1 0 0 0 1 0 0 0) ///
		  prefix(\multicolumn{@span}{c}{) suffix(}) span erepeat(\cmidrule(lr){@span})) ///
	  nomtitles ///
	  stats(Month_FE space Imp_Rule Reweighted Ctrl_Mean r2 N_Plants N, ///
		  label("Year-Month FE" " " "Imputation rule" "Reweighted" "Mean dep. var (control)" "R\textsuperscript{2}" "Plants" "Observations" ) ///
		  fmt(%1s %1s %1s %1s %9.2f %9.2f 0 0)) ///
	  prefoot(" ") ///
	  star(* 0.10 ** 0.05 *** 0.01) nonotes
	  
	  /*
	esttab reg_* MOC_* ///
	  using "$EMISSIONS_TABS/MOC_`table_name'.tex", replace ///
	  se(3) ar2 booktabs varwidth(32) ///
	  keep(1.D_treatment) coeflabel(1.D_treatment "ETS Treatment (=1)") ///
	  mgroups("\shortstack{No Imputed Months}" "\shortstack{Imputed Months}", pattern(1 0 0 0 1 0 0 0 0) ///
		  prefix(\multicolumn{@span}{c}{) suffix(}) span erepeat(\cmidrule(lr){@span})) ///
	  nomtitles ///
	  stats(Month_FE space Imp_Rule Reweighted Ctrl_Mean r2 N_Plants N, ///
		  label("Month FE" " " "Imputation rule" "Reweighted" "Mean dep. var (control)" "R\textsuperscript{2}" "Plants" "Observations" ) ///
		  fmt(%1s %1s %1s %1s %9.2f %9.2f 0 0)) ///
	  prefoot(" ") ///
	  star(* 0.10 ** 0.05 *** 0.01) nonotes
*/
		}
		

}

/*******************************************************************************
Purpose: Create Emissions regression table with post-covid interaction
****************************************************************************/

set more off
clear matrix
clear all
pause on

local yvar "lnY_rule0"
* When we have month dummies the dummy for post covid gets absorbed, so don't include it
local regvar_full "1.D_treatment##1.post_covid"
local regvar_sep "1.D_treatment#1.post_covid 1.D_treatment"

local cov_interest "ln_capex D_ln_capex_missing boi_year D_boi_year_missing bh_ope_cost D_bh_ope_cost_missing ln_plant_total_heatoutput"

********************************************************************************
**************************** Panel 0 - Unweighted ******************************
********************************************************************************
use "$EMISSIONS_DATA_OUT/Rule0_Panel.dta", clear
keep if D_interregnum == 0
keep if post_mock1 == 1 | post_mock2 == 1
sum `yvar' if D_treatment == 1
local table_name tab_treatment_effect_PM
gen post_covid = month16 > date("2020mar16", "YMD")

** Column 1: treatment dummy & plant covariates
eststo reg_1: reg `yvar' `regvar_full' `cov_interest', clus(gpcb_id)
estadd local Month_FE ""
estadd local Reweighted ""
estadd local Imp_Rule ""
estadd local N_Plants = e(N_clust)
sum `yvar' if D_treatment == 0
estadd local Ctrl_Mean = string(r(mean), "%15.2f")
estadd local space ""

** Column 2: treatment dummy & plant covariates & month FE
eststo reg_2: reghdfe `yvar' `regvar_sep'  `cov_interest', a(i.month16) clus(gpcb_id)
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
eststo reg_3: reg `yvar' `regvar_full'  `cov_interest' [pw=newweight_normalized], clus(gpcb_id)
estadd local Month_FE ""
estadd local Reweighted "Yes"
estadd local Imp_Rule ""
estadd local N_Plants = e(N_clust)
sum `yvar' [aw=newweight_normalized] if D_treatment == 0
estadd local Ctrl_Mean = string(r(mean), "%15.2f")
estadd local space ""

** Column 4: treatment dummy & plant covariates & month FE
eststo reg_4: reghdfe `yvar' `regvar_sep'  `cov_interest' [pw=newweight_normalized], a(i.month16) clus(gpcb_id)
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
gen post_covid = month16 > date("2020mar16", "YMD")

** Column 5: treatment dummy & plant covariates
eststo reg_5: reg `yvar' `regvar_full'  `cov_interest', clus(gpcb_id)
estadd local Month_FE ""
estadd local Reweighted ""
estadd local Imp_Rule "Rule A"
estadd local N_Plants = e(N_clust)
sum `yvar' if D_treatment == 0
estadd local Ctrl_Mean = string(r(mean), "%15.2f")
estadd local space ""

** Column 6: treatment dummy & plant covariates & month FE
eststo reg_6: reghdfe `yvar' `regvar_sep' `cov_interest', a(i.month16) clus(gpcb_id)
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
gen post_covid = month16 > date("2020mar16", "YMD")

** Column 7: treatment dummy & plant covariates
eststo reg_7: reg `yvar' `regvar_full' `cov_interest', clus(gpcb_id)
estadd local Month_FE ""
estadd local Reweighted ""
estadd local Imp_Rule "Rule B"
estadd local N_Plants = e(N_clust)
sum `yvar' if D_treatment == 0
estadd local Ctrl_Mean = string(r(mean), "%15.2f")
estadd local space ""

** Column 8: treatment dummy & plant covariates & month FE
eststo reg_8: reghdfe `yvar' `regvar_sep' `cov_interest', a(i.month16) clus(gpcb_id)
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

esttab reg_* ///
  using "$EMISSIONS_TABS/Table_F6.tex", replace ///
  se(3) ar2 booktabs varwidth(32) ///
  keep(1.D_treatment 1.post_covid 1.D_treatment#1.post_covid) ///
  coeflabel(1.D_treatment "ETS Treatment (=1)" 1.post_covid "Post-Covid (=1)" 1.D_treatment#1.post_covid "Treatment $\times$ Post-Covid") ///
  mgroups("\shortstack{No Imputation}" "\shortstack{With Imputation}", pattern(1 0 0 0 1 0 0 0) ///
	  prefix(\multicolumn{@span}{c}{) suffix(}) span erepeat(\cmidrule(lr){@span})) ///
  nomtitles ///
  stats(Month_FE space Imp_Rule Reweighted Ctrl_Mean r2 N_Plants N, ///
	  label("Year-Month FE" " " "Imputation rule" "Reweighted" "Mean dep. var (control)" "R\textsuperscript{2}" "Plants" "Observations" ) ///
	  fmt(%1s %1s %1s %1s %9.2f %9.2f 0 0)) ///
  prefoot(" ") ///
  star(* 0.10 ** 0.05 *** 0.01) nonotes

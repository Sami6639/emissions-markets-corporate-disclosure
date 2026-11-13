/*******************************************************************************
	   Purpose: Produce a table of mean of log(PM emissions) by imputation rules
				and kernel density plots of emissions by treatment status.
   ****************************************************************************/

set more off
clear all
pause on

use "$IMPUTATION_DATA_OUT/PlantMonthPMMassNoRule.dta", clear
keep gpcb_id treatmentstatus month16 ind_month_mass_val_rule0
rename ind_month_mass_val_rule0 Y

merge 1:1 gpcb_id month16 using "$IMPUTATION_DATA_OUT/PlantMonthPMMassRule0.dta"
keep gpcb_id treatmentstatus month16 Y ind_month_mass_val_rule0
rename ind_month_mass_val_rule0 Y_0

merge 1:1 gpcb_id month16 using "$IMPUTATION_DATA_OUT/PlantMonthPMMassRuleA.dta"
keep gpcb_id treatmentstatus month16 Y* ind_month_mass_val_rule0
rename ind_month_mass_val_rule0 Y_A

merge 1:1 gpcb_id month16 using "$IMPUTATION_DATA_OUT/PlantMonthPMMassRuleB.dta"
keep gpcb_id treatmentstatus month16 Y* ind_month_mass_val_rule0
rename ind_month_mass_val_rule0 Y_B

gen lnY = ln(Y)
gen lnY_0 = ln(Y_0)
gen lnY_A = ln(Y_A)
gen lnY_B = ln(Y_B)

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

keep if D_interregnum == 0
keep if post_mock1 == 1 | post_mock2 == 1

********************************************************************************
* Table: Mean of the log(PM emissions) by imputation rules
********************************************************************************

matrix data = J(6, 3, 0)
local counter = 0
foreach var in lnY_0 lnY_A lnY_B {

	local counter = `counter' + 1
	
	sum `var' if treatmentstatus == "Control"
	matrix data[2*`counter' -1, 1] = r(mean)
	matrix data[2*`counter' , 1] = r(N)

	sum `var' if treatmentstatus == "Treatment"
	matrix data[2*`counter' -1, 2] = r(mean)
	matrix data[2*`counter', 2] = r(N)

	sum `var'
	matrix data[2*`counter' -1, 3] = r(mean)
	matrix data[2*`counter', 3] = r(N)

}
preserve
clear 

svmat double data, names(col)
* Cleanup vars
foreach v of varlist * {
	gen `v'_str = string(round(`v', 0.01), "%9.2f")
	replace `v'_str = regexr(`v'_str, "\..*", "") if mod(_n, 2) == 0
	replace `v'_str = "[" + `v'_str + "]" if mod(_n, 2) == 0
	replace `v'_str = "\multicolumn{1}{c}{" + `v'_str + "}"
	drop `v'
	rename `v'_str `v'
}


gen rname = "", before("c1")
replace rname = "No Imputation" if _n == 1
replace rname = "Rule A: Stack-Experiment" if _n == 3
replace rname = "Rule B: Treatment-Month" if _n == 5

	
listtex using "$EMISSIONS_TABS/Table_C1.tex", rstyle(tabular) replace ///
headlines("\begin{tabular}{@{\extracolsep{2pt}}lD{.}{.}{-1}D{.}{.}{-1}D{.}{.}{-1}} \\[-1.8ex]\toprule \\[-1.8ex] & \multicolumn{1}{ >{\centering\arraybackslash}m{2cm} }{Control} & \multicolumn{1}{ >{\centering\arraybackslash}m{2cm} }{Treatment} & \multicolumn{1}{ >{\centering\arraybackslash}m{2cm} }{All}  \\ \\[-1.8ex] \hline \\[-1.8ex]") ///
footlines("\bottomrule \\[-1.8ex]\end{tabular}")


restore


********************************************************************************
* Figure: Kernel density of PM emissions by treatment status
********************************************************************************

kdensity Y if treatmentstatus=="Treatment" & Y < 10000, lcolor("0 72 112") ///
	addplot(kdensity Y_0 if treatmentstatus=="Treatment" & Y_0 < 10000, lcolor("163 43 58") || /// 
			kdensity Y_A if treatmentstatus=="Treatment" & Y_A < 10000, lcolor("71 118 41") || /// 
			kdensity Y_B if treatmentstatus=="Treatment" & Y_B < 10000, lcolor("252 118 0") ) ///
	legend(cols(2) size(medsmall) region(lstyle(none)) position(6)) ///
	legend(on order(1 "Stack-Week (N=1604)" 2 "Stack-Month (N=1899)" 3 "Stack-Experiment (N=2028)" 4 "Treatment-Month (N=2028)")) ///
	title("Treatment", size(medium)) ///
	xtitle("PM mass (kg / month)") ///
	plotregion(color(white)) bgcolor(white) graphregion(color(white))
graph export "$EMISSIONS_FIGS/Figure_C4_A_1.png", replace


kdensity Y if treatmentstatus=="Control" & Y < 10000, lcolor("0 72 112") ///
	addplot(kdensity Y_0 if treatmentstatus=="Control" & Y_0 < 10000, lcolor("163 43 58") || /// \
			kdensity Y_A if treatmentstatus=="Control" & Y_A < 10000, lcolor("71 118 41") || /// 
			kdensity Y_B if treatmentstatus=="Control" & Y_B < 10000, lcolor("252 118 0"))	///
	legend(cols(2) size(medsmall) region(lstyle(none)) position(6)) ///
	legend(on order(1 "Stack-Week (N=997)" 2 "Stack-Month (N=1336)" 3 "Stack-Experiment (N=1768)" 4 "Treatment-Month (N=1768)")) ///
	title("Control", size(medium)) ///
	xtitle("PM mass (kg / month)") ///
	plotregion(color(white)) bgcolor(white) graphregion(color(white))
graph export "$EMISSIONS_FIGS/Figure_C4_A_2.png", replace

********************************************************************************
* Figure: Kernel density of log(PM emissions) by treatment status
********************************************************************************

kdensity lnY if treatmentstatus=="Treatment", lcolor("0 72 112") ///
	addplot(kdensity lnY_0 if treatmentstatus=="Treatment", lcolor("163 43 58") || /// 
			kdensity lnY_A if treatmentstatus=="Treatment", lcolor("71 118 41") || /// 
			kdensity lnY_B if treatmentstatus=="Treatment", lcolor("252 118 0"))	///
	legend(cols(2) size(medsmall) region(lstyle(none)) position(6)) ///
	legend(on order(1 "Stack-Week (N=1604)" 2 "Stack-Month (N=1899)" 3 "Stack-Experiment (N=2028)" 4 "Treatment-Month (N=2028)")) ///
	title("Treatment", size(medium)) ///
	xtitle("log[PM mass (kg / month)]") ///
	plotregion(color(white)) bgcolor(white) graphregion(color(white))
graph export "$EMISSIONS_FIGS/Figure_C4_B_1.png", replace

kdensity lnY if treatmentstatus=="Control", lcolor("0 72 112") ///
	addplot(kdensity lnY_0 if treatmentstatus=="Control", lcolor("163 43 58")|| /// 
			kdensity lnY_A if treatmentstatus=="Control", lcolor("71 118 41") || /// 
			kdensity lnY_B if treatmentstatus=="Control", lcolor("252 118 0"))	///
	legend(cols(2) size(medsmall) region(lstyle(none)) position(6)) ///
	legend(on order(1 "Stack-Week (N=997)" 2 "Stack-Month (N=1336)" 3 "Stack-Experiment (N=1768)" 4 "Treatment-Month (N=1768)")) ///
	title("Control", size(medium)) ///
	xtitle("log[PM mass (kg / month)]") ///
	plotregion(color(white)) bgcolor(white) graphregion(color(white))
graph export "$EMISSIONS_FIGS/Figure_C4_B_2.png", replace

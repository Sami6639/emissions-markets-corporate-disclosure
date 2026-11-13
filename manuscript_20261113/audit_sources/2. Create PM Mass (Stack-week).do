/*******************************************************************************
	   Project: ETS
	   Purpose: Create the dependent variable for regression, PLANT-MONTH KG 
	   EMISSIONS (KG/MONTH), without further imputation than within-stack, week
	   
	   Note: Imputationis executed as follows:

	   1) Missing values of Stack day kg/hr are imputed with the stack's 
	   own week mean kg/hr.
   ****************************************************************************/

set more off
clear all
pause on

*-------------------------------------------------------------------------------

use "$EMISSIONS_DATA_IN/CEMS_2018-12-31 to 2021-04-03_StackDay_Balanced_HistCFs_Master337s_3sample2trunc.dta", clear
drop if date < date("2019jan16", "YMD")
format date %tddd-Mon-YY
sort date composite_id
tab date
** 242,303 Observations. 337 Stacks. 719 Days from 16-Apr-19 to 03-Apr-21.

** Generate a week variable
drop week
gen int week = floor((date-td(31dec2018))/7)+1
la var week "Week"

** Generate a month variable which goes from the 16th of each month to the 15th of the next month. 
** This definition of month aligns with the implementation of ETS market in its initial Stages. 
** Nick Cox's code:
drop month16
gen month16 = date if day(date) == 16
// 	replace month16 = mdy(1, 16, 2019) in 1
replace month16 = month16[_n-1] if missing(month16)
la var month16 "Month, defined as 16th of this month to 15th of next month"
gen month16_sif = month16
format month16 %tddd-Mon-YY
la var month16_sif "[SIF] Month-year. For convenience."
order month16_sif, a(month16)
sort composite_id date
** Check days in each month for one device. Looks good.
*tab month16 if composite_id == "GJSRT100740111"

** Generate Dummy for Interregnum period of market
** Covid lockdown -- 23 March 2020 to 11 October 2021. 
** Mock-III started on 12 October 2021.
gen D_interregnum_week = week >= 65 & week <= 93
replace D_interregnum_week =1 if week == 99 | week == 100
la var D_interregnum_week ///
	"[Week-level] =1 if Interregnum due to Covid-19 lockdown, zero otherwise."

drop extinct_with_assignment removed_from_sample comment

** Remove plants that have no observation from 16-Apr-19 to 03-Apr-21.
bysort gpcb_id: egen pct_report = mean(!missing(pm_mass_rule0)) if ///
	month16 >= date("2019jul16", "YMD") & D_interregnum_week == 0
sort composite_id date
bysort gpcb_id: egen pct_report_1 = mean(pct_report)
drop if pct_report_1 == 0
drop pct_report pct_report_1
sort composite_id date  
tab date
** 222,890 Observations. 310 Stacks. 719 Days from 16-Apr-19 to 03-Apr-21.

********************************************************************************
********************* [1] CALCULATE ACTUAL STACK DAY MASS **********************
********************************************************************************

forvalues i=0(1)9{

	** Replace tot_report_hrs to zero 
	** if the stack was not sending a valid caliberated stack-day kg/hr that day
	gen tot_report_hrs_rule`i' = tot_report_hrs
	replace tot_report_hrs_rule`i' = 0 if D_vctransmitting_rule`i' == 0
	label var tot_report_hrs_rule`i' ///
		"[RE-LABELED] Stack-day VALID CALIBRATED Reporting Hours from CEMS - rule `i'"

	** Calculate DAILY actual mass emissions using CEMA Day Reporting Hours
	gen stack_daily_mass_actual_rule`i' = pm_mass_rule`i' * tot_report_hrs_rule`i'
	la var stack_daily_mass_actual_rule`i' ///
		"Stack Day Actual Mass Emissions (kg) from CEMS Reported Hours - rule `i'"

}

********************************************************************************
***************** [2] DAILY NON-REPORTING HOURS FOR IMPUTATION *****************
********************************************************************************

forvalues i=0(1)9{

	** Calculate DAILY non-reporting hours for imputation
	gen daily_nonreport_hrs_rule`i' = 24 - tot_report_hrs_rule`i'
	order daily_nonreport_hrs_rule`i', a(tot_report_hrs_rule`i')
	la var daily_nonreport_hrs_rule`i' ///
		"Stack Day NON-Reporting Hours - CEMS - rule `i'"

}

********************************************************************************
********* [3] For Imp: GENERATE STACK'S OWN WEEK and MONTH MEAN KG/HR **********
********************************************************************************

forvalues i=0(1)9{

	** Calculate stack's own week mean kg/hr for missing pm mass values
	bysort composite_id week: egen week_mean_mass_rule`i' = mean(pm_mass_rule`i')
	label var week_mean_mass_rule`i' "Stack Week Mean kg/hr - rule `i'"

// 	** Calculate stack's own month mean kg/hr for stacks missing entire week of pm mass
// 	bysort composite_id month16: egen month_mean_mass_rule`i' = mean(pm_mass_rule`i')
// 	label var month_mean_mass_rule`i' "Stack Month Mean kg/hr - rule `i'"

}

/*******************************************************************************
	   NOW READY FOR IMPUTATION RULE 0a.
	   THE IMPLEMENTATION OF THIS RULE WILL BE:

	   1) 	IMPUTE STACK'S OWN WEEK MEAN PM_MASS (KG/HR) FOR ALL MISSING VALUES
	   OF STACK DAY PM_MASS (KG/HR). 
	   2) 	IF WEEK MEAN KG/HR IS MISSING, IMPUTE MONTH MEAN PM_MASS (KG/HR)
	   3) 	THE FINAL EMISSION QUANTITY IS:

	   VALIDATED STACK MASS (KG) = 
	   ACTUAL STACK MASS (KG) USING CEMS REPORTED HOURS +
	   IMPUTED STACK MASS (KG) USING CEMS NON-REPORTED HOURS
   ****************************************************************************/



********************************************************************************
******************** [4] CALCULATE DAILY STACK IMPUTED MASS ********************
********************************************************************************

forvalues i=0(1)9{	

	** Calculate PER DAY imputed emissions
	gen stack_daily_mass_imp_rule`i' = daily_nonreport_hrs_rule`i' * week_mean_mass_rule`i'
// 	replace stack_daily_mass_imp_rule`i' = daily_nonreport_hrs_rule`i' * month_mean_mass_rule`i' ///
// 		if week_mean_mass_rule`i' == .
	la var stack_daily_mass_imp_rule`i' ///
		"Stack-day Imputed Mass Emissions (kg) from CEMS Non-Reported Hours - rule`i'"

	** Correct for week of Diwali 2019 when imputation should be zero.
	replace stack_daily_mass_imp_rule`i' = 0 if ///
		date >= date("2019oct26", "YMD") & ///
		date <= date("2019nov03", "YMD") & ///
		stack_daily_mass_imp_rule`i' != .

}

********************************************************************************
******************* [5] CALCULATE DAILY STACK VALIDATED MASS *******************
********************************************************************************

forvalues i=0(1)9{	

	** Calculate validated DAY emissions per stack
	gen stack_daily_mass_val_rule`i' = stack_daily_mass_actual_rule`i' + stack_daily_mass_imp_rule`i'
	replace stack_daily_mass_val_rule`i' = stack_daily_mass_imp_rule`i' ///
		if stack_daily_mass_val_rule`i' == .
	la var stack_daily_mass_val_rule`i' ///
		"Stack Day Validated Mass Emissions (kg) (=Stack-day Actual + Stack-day Imp) - rule `i'"

}

/*******************************************************************************
	   NOW READY TO MAKE THE DEPENDENT VARIABLE FOR REGRESSIONS IN PART 6 
	   (6. TREATMENT EFFECT ANALYSIS). THIS VAR IS PLANT MONTH MASS (KG).

	   STEPS TO CREATE THIS VARIABLE WILL BE:

	   6.1) CALCULATE STACK WEEK MASS (KG), AND THEN PLANT WEEK MASS (KG).
	   FIRST GENERATE THESE VARIABLES IN THE STACK-DAY LEVEL DATA SET.
	   AND SAVE IT FOR FUTURE USE IF NEEDED ("_StackDayLevel.dta").

	   6.2) THEN, COLLAPSE THE STACK-DAY LEVEL DATA SET TO KEEP ONE DATA POINT 
	   PER PLANT PER WEEK ("_PlantWeekLevel.dta"). 

	   CONTAINS THE DEPENDENT VARIABLE: PLANT-WEEK MASS (KG) EMISSIONS 
	   USING IMPUTATION RULE 0a.
   ****************************************************************************/

preserve

********************************************************************************
********************* [6.1] GENERATE STACK-MONTH MASS (KG) *********************
********************************************************************************

forvalues i=0(1)9{

	** Calculate MONTHLY validated emissions PER STACK
	bysort composite_id month16: egen stack_month_mass_val_rule`i' = sum(stack_daily_mass_val_rule`i')
	bysort composite_id month16: egen miss_stack_month_mass_val = max(missing(stack_daily_mass_val_rule`i'))
	replace stack_month_mass_val_rule`i' = . if miss_stack_month_mass_val == 1
	la var stack_month_mass_val_rule`i' ///
		"Stack-month Validated Mass Emissions (kg) - rule `i'"
	drop miss_stack_month_mass_val

}

** Keep one monthly data point for each STACK
bysort composite_id month16: gen dump=_n
bysort composite_id month16: keep if _n==_N 	
keep composite_id industry_id gpcb_id month16 treatmentstatus stack_month_mass_val* 
** 7,440 observations. 310 stacks. 24 months from April 2019 to March 2021.

********************************************************************************
******************** [6.2] COLLAPSE TO PLANT-LEVEL DATA SET ********************
********************************************************************************

/**	AS PER NICK'S INSTRUCTION ON WEEKLY CALL 01 DEC 2020: FOR PLANTS WITH >1 STACK, 
	   WE WILL ONLY CALCULATE THEIR PLANT MASS (KG) SUM IF ALL STACKS ARE CONNECTED. 
	   IF STACKS ARE PARTIALLY CONNECTED (i.e., ONLY 1 OF 3 STACKS CONNECTED), 
   THE ENTIRE PLANT SUM WILL BE MISSING. 	**/

forvalues i=0(1)9{

	** Calculate MONTHLY validated emissions PER PLANT
	bysort gpcb_id month16: egen ind_month_mass_val_rule`i' = sum(stack_month_mass_val_rule`i')
	bysort gpcb_id month16: egen miss_ind_month_mass_val = max(missing(stack_month_mass_val_rule`i'))
	replace ind_month_mass_val_rule`i' = . if miss_ind_month_mass_val == 1
	la var stack_month_mass_val_rule`i' ///
		"Plant-month Validated Mass Emissions (kg) - rule `i'"
	drop miss_ind_month_mass_val

}

** Keep one monthly data point for each PLANT
bysort gpcb_id month16: gen dump=_n
bysort gpcb_id month16: keep if _n==_N
keep industry_id gpcb_id month16 treatmentstatus ind_month_mass_val* 
** 7,008 observations. 292 plants. 24 months from April 2019 to March 2021.

save "$IMPUTATION_DATA_OUT/PlantMonthPMMassNoRule.dta", replace

restore

/*******************************************************************************
	   NOW WE MAKE THE DEPENDENT VARIABLE FOR PLOTTING TIME SERIES 
	   THIS VAR IS PLANT WEEK MASS (KG).
   ****************************************************************************/

preserve

********************************************************************************
********************* [7.1] GENERATE STACK-WEEK MASS (KG) **********************
********************************************************************************

forvalues i=0(1)9{

	** Calculate WEEKLY validated emissions PER STACK
	bysort composite_id week: egen stack_week_mass_val_rule`i' = sum(stack_daily_mass_val_rule`i')
	bysort composite_id week: egen miss_stack_week_mass_val = max(missing(stack_daily_mass_val_rule`i'))
	replace stack_week_mass_val_rule`i' = . if miss_stack_week_mass_val == 1
	la var stack_week_mass_val_rule`i' ///
		"Stack-week Validated Mass Emissions (kg) - rule `i'"
	drop miss_stack_week_mass_val

}

** Keep one monthly data point for each STACK
bysort composite_id week: gen dump=_n
bysort composite_id week: keep if _n==_N 	
keep composite_id industry_id gpcb_id week treatmentstatus stack_week_mass_val*
** 31,930 Observations. 310 Stacks. 103 weeks from April 2019 to March 2021.

********************************************************************************
******************** [7.2] COLLAPSE TO PLANT-LEVEL DATA SET ********************
********************************************************************************

forvalues i=0(1)9{

	** Calculate WEEKLY validated emissions PER PLANT
	bysort gpcb_id week: egen ind_week_mass_val_rule`i' = sum(stack_week_mass_val_rule`i')
	bysort gpcb_id week: egen miss_ind_week_mass_val = max(missing(stack_week_mass_val_rule`i'))
	replace ind_week_mass_val_rule`i' = . if miss_ind_week_mass_val == 1
	la var stack_week_mass_val_rule`i' ///
		"Plant-week Validated Mass Emissions (kg) - rule `i'"
	drop miss_ind_week_mass_val

}

** Keep one monthly data point for each PLANT
bysort gpcb_id week: gen dump=_n
bysort gpcb_id week: keep if _n==_N
keep industry_id gpcb_id week treatmentstatus ind_week_mass_val* 
** 30,076 Observations. 292 Plants. 103 weeks from April 2019 to March 2021.

save "$IMPUTATION_DATA_OUT/PlantWeekPMMassNoRule.dta", replace

restore


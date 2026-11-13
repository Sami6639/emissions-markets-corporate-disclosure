/*******************************************************************************
	   Purpose: Compile baseline covariates.
   ****************************************************************************/
   
set more off
clear matrix
clear all
pause on

use "$BASELINE_DATA_IN/Master ETS In-sample - Plants (318i).dta", clear

** MERGE IN BASELINE COVARIATES
merge m:1 industry_id using "$BASELINE_DATA_IN/BaselineCovariates_318i.dta"
tab _merge // All matched
keep if _merge == 3
drop _merge

** D_treatment, official_ets_assignment, treatmentstatus all coincide
tab D_treatment official_ets_assignment
tab treatmentstatus official_ets_assignment
tab treatmentstatus D_treatment

drop treatmentstatus
rename official_ets_assignment treatmentstatus
order treatmentstatus, a(gpcb_id)
order D_treatment, a(treatmentstatus)
label var treatmentstatus "'T'=Treatment, 'C'=Control" 

sort gpcb_id
drop comment

********************************************************************************
***************** [1] DUMMIES FOR MISSING VALUES OF COVARIATES *****************
********************************************************************************

gen D_plant_boi_cap_missing = plant_boi_cap == .
order D_plant_boi_cap, a(plant_boi_cap)
label var D_plant_boi_cap "1=Plant Boiler Capacity missing"

gen D_bh_total_capex_missing = bh_total_capex == .
order D_bh_total_capex_missing, a(bh_total_capex)
label var D_bh_total_capex_missing "1=Boiler House CapEx missing"

gen D_bh_total_workers_missing = bh_total_workers == .
order D_bh_total_workers_missing, a(bh_total_workers)
label var D_bh_total_workers_missing "1=Boiler Employment missing"

rename mean_boiler_year boi_year
gen D_boi_year_missing = boi_year == .
order D_boi_year_missing, a(boi_year)
label var D_boi_year_missing "1=Mean Boiler Year missing"

rename bh_annu_ope_cost_lakh bh_ope_cost
gen D_bh_ope_cost_missing = bh_ope_cost == .	
order D_bh_ope_cost_missing, a(bh_ope_cost)
label var D_bh_ope_cost_missing "1=2018 BH Operating Cost missing"

** Having made the dummies for missing values,
** now replace missing values in control vars to zero (per Nick's instruction).

replace plant_boi_cap = 0 if plant_boi_cap == .
replace bh_total_capex = 0 if bh_total_capex == .
replace bh_total_workers = 0 if bh_total_workers == .
replace boi_year = 0 if boi_year == .
replace bh_ope_cost = 0 if bh_ope_cost == .

********************************************************************************
******************************* [2] MAKE LOG VARS ******************************
********************************************************************************

gen ln_capex = ln(bh_total_capex)
gen D_ln_capex_missing = ln_capex == .
replace ln_capex = 0 if ln_capex == .
label var ln_capex "Ln(Boiler House CapEx)"
label var D_ln_capex_missing "1=Ln(Boiler House CapEx) missing"

gen ln_boicap = ln(plant_boi_cap)
gen D_ln_boicap_missing = ln_boicap == .
replace ln_boicap = 0 if ln_boicap == .
label var ln_boicap "Ln(Plant Boiler Capacity)"
label var D_ln_boicap_missing "1=Ln(Plant Total Boiler Capacity) missing"

gen ln_plant_total_heatoutput = ln(plant_total_heatoutput) 	// None missing.
label var ln_plant_total_heatoutput "Ln(Plant Total Heat Output)"
order ln_plant_total_heatoutput, a(plant_total_heatoutput)

gen ln_opecost = ln(bh_ope_cost)
gen D_ln_opecost_missing = ln_opecost == .
replace ln_opecost = 0 if ln_opecost == .
label var ln_opecost "Ln(2018 BH Operating Cost)"
label var D_ln_opecost_missing "1=Ln(2018 BH Operating Cost) missing"

********************************************************************************
***************************** [3] CONVERT CURRENCY *****************************
********************************************************************************

gen grossrev_17_18_clean_USD = grossrev_17_18_clean * 10000000 / $USD2INR
label var grossrev_17_18_clean_USD "2017 Gross Sales Revenue (USD)"

gen bh_total_capex_USD = bh_total_capex * 100000 / $USD2INR
label var bh_total_capex_USD "Boiler House CapEx (USD)"

gen bh_ope_cost_USD = bh_ope_cost * 100000 / $USD2INR
label var bh_ope_cost_USD "2018 Boiler House Operating Cost (USD)"

gen elecbill_2017_clean_USD = elecbill_2017_clean * 100000 / $USD2INR
label var elecbill_2017_clean_USD "2017 Plant Total Electricity Cost (USD)"

********************************************************************************
***************** [4] GENERATE "MAXIMAL" ABATEMENT TECHNOLOGY ******************
********************************************************************************

* Assuming cyclone < bag filter < scrubbers / esps
gen cyc_max = (D_cyc == 1) & (D_bf == 0) & (D_scr == 0) & (D_esp == 0)
gen bf_max = (D_bf == 1) & (D_scr == 0) & (D_esp == 0)
gen scr_esp_max = (D_scr == 1) | (D_esp == 1)
label var cyc_max "=1 if maximal abatement = cyclone"
label var bf_max "=1 if maximal abatement = bag filter"
label var scr_esp_max "=1 if maximal abatement = scrubbers / esps"

********************************************************************************
***************************** [5] LABEL VARIABLES ******************************
********************************************************************************

label var ratio_rev_17to16 "= grossrev_17_18_clean / grossrev_16_17_clean"
label var ratio_elec_17to16 "= elecbill_2017_clean / elecbill_2016_clean"
label var pm_mass_etsbl "ETS Baseline Plant Total PM Mass Rate (kg/hr)"
label var pm_conc_etsbl "ETS baseline plant mean PM concentration (mg/Nm{superscript:3})"
label var pm_conc_cemsbl "CEMS Baseline Mean PM Concentration (mg/Nm{superscript:3})"
label var mean_ring_premock "Mean pre-treatment Ringelmann score"

save "$BASELINE_DATA_OUT/BaselineCovariates.dta", replace

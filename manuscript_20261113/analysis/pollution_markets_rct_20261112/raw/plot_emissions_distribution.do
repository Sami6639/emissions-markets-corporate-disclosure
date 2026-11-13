/*******************************************************************************
	   Purpose: Plot ETS Baseline PM Concentration
   ****************************************************************************/

set more off
clear matrix
clear all
pause on

use "$BASELINE_DATA_OUT/BaselineCovariates.dta", clear

label define newlabel 0 "Control" 1 "Treatment", modify
label val D_treatment newlabel

// Show relative frequencies of over regulatory level
gen over_sq_reg_ind = pm_conc_etsbl>150
tabulate over_sq_reg_ind D_treatment, co

centile pm_conc_etsbl, c(95)
local high = r(c_1)
di `high'
replace pm_conc_etsbl = . if pm_conc_etsbl > `high'
sum pm_conc_etsbl

// Show relative frequencies of over regulatory level
replace over_sq_reg_ind = . if pm_conc_etsbl==.
tabulate over_sq_reg_ind D_treatment, co

hist pm_conc_etsbl, by(D_treatment, note("") legend(off) ///
	graphregion(color(white)) plotregion(color(white)) bgcolor(white)) /// 
	subtitle(,bcolor(white)) ///
	addplot(pci 0 150 0.015 150) color(midblue*0.6) lcolor(midblue) /// 
	width(30) start(0) xscale(range(0 500)) ///
	text(0.015 175 "150 mg/Nm{superscript:3}", orientation(vertical) place(sw) size(medsmall) color(red)) ///
	xlab(,labsize(medlarge)) ylab(,labsize(medlarge)) ///
	xsize(10) ysize(5)
graph export "$EMISSIONS_FIGS/Figure_B1.pdf", replace

****************************************************
* FigS6 climate placebo distributions
* Based on: DiDAnalysis/S6_placebo_test_climate_final.do
*
* Output: SI_results/FigS6_Climate.csv
****************************************************

clear all
set more off
version 16.0

****************************************************
* 1. Paths and settings
****************************************************
local datafile "PanelResults/dd.dta"
local outfile  "SI_results/FigS6_Climate.csv"

local reps 1000
local seed 12345

local outcomes y11 y12 y23 y24 y33 y34
local xvars Xcli1 Xcli2 Xcli3 Xtime1 Xtime2 Xdq1 Xmeanload

capture confirm file "`datafile'"
if _rc {
    display as error "Cannot find input data: `datafile'"
    exit 601
}

capture mkdir "SI_results"

****************************************************
* 2. Helper: outcome labels
****************************************************
capture program drop get_outcome_label
program define get_outcome_label, rclass
    syntax varname

    if "`varlist'" == "y11" return local label "Workload"
    if "`varlist'" == "y12" return local label "Overload"
    if "`varlist'" == "y23" return local label "Heatstroke"
    if "`varlist'" == "y24" return local label "Severe heatstroke"
    if "`varlist'" == "y33" return local label "Mild cold hypothermia"
    if "`varlist'" == "y34" return local label "Moderate cold hypothermia"
end

****************************************************
* 3. Baseline regressions
****************************************************
tempname results
tempfile results_dta
postfile `results' str8 type int rep str40 outcome str10 yvar double coef using `results_dta', replace

use "`datafile'", clear

foreach y of local outcomes {
    quietly reg `y' i.Grade##i.Climate ///
        `xvars', robust

    scalar beta_`y' = _b[1.Grade#1.Climate]

    quietly get_outcome_label `y'
    local label "`r(label)'"

    post `results' ("true") (0) ("`label'") ("`y'") (beta_`y')
}

****************************************************
* 4. Prepare original climate series
****************************************************
preserve

keep date Climate
duplicates drop date, force

sort date
gen id = _n

tempfile base
save `base', replace

restore

****************************************************
* 5. Permutation loop
****************************************************
set seed `seed'

forvalues rep = 1/`reps' {

    preserve

    ************************************************
    * Step 1: randomly shuffle climate timing
    ************************************************
    use `base', clear

    gen u = runiform()
    sort u

    gen id_perm = _n

    keep id_perm Climate
    rename Climate Climate_perm

    tempfile shuffled
    save `shuffled', replace

    ************************************************
    * Step 2: restore original date order
    ************************************************
    use `base', clear

    sort id
    gen id_perm = _n

    merge 1:1 id_perm using `shuffled', nogen

    keep date Climate_perm

    tempfile map
    save `map', replace

    ************************************************
    * Step 3: merge randomized timing back to data
    ************************************************
    use "`datafile'", clear

    merge m:1 date using `map', nogen

    ************************************************
    * Step 4: placebo regressions
    ************************************************
    foreach y of local outcomes {
        capture quietly reg `y' i.Grade##i.Climate_perm ///
            `xvars', robust
        local reg_rc = _rc

        quietly get_outcome_label `y'
        local label "`r(label)'"

        if `reg_rc' {
            post `results' ("placebo") (`rep') ("`label'") ("`y'") (.)
        }
        else {
            capture scalar b_tmp = _b[1.Grade#1.Climate_perm]
            if _rc post `results' ("placebo") (`rep') ("`label'") ("`y'") (.)
            else {
                local b = b_tmp
                post `results' ("placebo") (`rep') ("`label'") ("`y'") (`b')
            }
        }
    }

    restore
}

postclose `results'

****************************************************
* 6. Save CSV
****************************************************
use `results_dta', clear
order type rep outcome yvar coef
format coef %12.6f
export delimited using "`outfile'", replace

display as text "Saved climate placebo CSV: `outfile'"
display as text "Climate repetitions: `reps'"

****************************************************
* End
****************************************************

clear all
set more off
version 16.0

capture which reghdfe
if _rc {
    display as error "reghdfe is required. Install it with: ssc install reghdfe"
    exit 111
}

local datafile "PanelResults/dd.dta"
local outcsv "SI_results/TableS5.csv"
local outmd "SI_results/TableS5.md"

use "`datafile'", clear

capture confirm numeric variable alpha
if _rc {
    tempvar alpha_fe
    egen `alpha_fe' = group(alpha)
    local worker_fe `alpha_fe'
}
else {
    local worker_fe alpha
}

local yvars y11 y12 y21 y22 y23 y24 y31 y33 y34
local units "Hours pp degC pp pp pp degC pp pp Hours Orders"
local controls Xcli1 Xcli2 Xcli3 Xdq1 Xtime1 Xtime2 Xtime3 Xmeanload

local header "Variables"
local unitrow "Unit"
local climaterow "Climate"
local climatese " "
local interrow "Climate x Tier"
local interse " "
local cashrow "Cash-burning wars (Xtime3)"
local cashse " "
local ctrlrow "Controls"
local ferow "Individual FEs"
local monthrow "Year-Month FEs"
local obsrow "Worker-Day level obs."
local r2row "Adj R-squared"

local model_count : word count `yvars'

forvalues i = 1/`model_count' {
    local y : word `i' of `yvars'
    local unit : word `i' of `units'

    capture drop _reghdfe_resid
    quietly reghdfe `y' i.Grade##i.Climate `controls', absorb(month `worker_fe') cluster(`worker_fe') resid

    local c1 = _b[1.Climate]
    local s1 = _se[1.Climate]
    local p1 = 2 * ttail(e(df_r), abs(`c1' / `s1'))

    local c2 = _b[1.Grade#1.Climate]
    local s2 = _se[1.Grade#1.Climate]
    local p2 = 2 * ttail(e(df_r), abs(`c2' / `s2'))

    local c3 = _b[Xtime3]
    local s3 = _se[Xtime3]
    local p3 = 2 * ttail(e(df_r), abs(`c3' / `s3'))

    local star1 = cond(`p1' < 0.01, "***", cond(`p1' < 0.05, "**", cond(`p1' < 0.1, "*", "")))
    local star2 = cond(`p2' < 0.01, "***", cond(`p2' < 0.05, "**", cond(`p2' < 0.1, "*", "")))
    local star3 = cond(`p3' < 0.01, "***", cond(`p3' < 0.05, "**", cond(`p3' < 0.1, "*", "")))

    local v1 : display %9.3f `c1'
    local e1 : display %9.3f `s1'
    local v2 : display %9.3f `c2'
    local e2 : display %9.3f `s2'
    local v3 : display %9.3f `c3'
    local e3 : display %9.3f `s3'
    local obs : display %12.0f e(N)
    local r2 : display %9.3f e(r2_a)

    local v1 = strtrim("`v1'")
    local e1 = strtrim("`e1'")
    local v2 = strtrim("`v2'")
    local e2 = strtrim("`e2'")
    local v3 = strtrim("`v3'")
    local e3 = strtrim("`e3'")
    local obs = strtrim("`obs'")
    local r2 = strtrim("`r2'")

    local header "`header',`y'"
    local unitrow "`unitrow',`unit'"
    local climaterow "`climaterow',`v1'`star1'"
    local climatese "`climatese',(`e1')"
    local interrow "`interrow',`v2'`star2'"
    local interse "`interse',(`e2')"
    local cashrow "`cashrow',`v3'`star3'"
    local cashse "`cashse',(`e3')"
    local ctrlrow "`ctrlrow',Yes"
    local ferow "`ferow',Yes"
    local monthrow "`monthrow',Yes"
    local obsrow "`obsrow',`obs'"
    local r2row "`r2row',`r2'"
}

capture file close csvout
file open csvout using "`outcsv'", write replace text
foreach row in header unitrow climaterow climatese interrow interse cashrow cashse ctrlrow ferow monthrow obsrow r2row {
    local line "``row''"
    file write csvout `"`line'"' _n
}
file close csvout

capture file close mdout
file open mdout using "`outmd'", write replace text
file write mdout "| Variables"
foreach y of local yvars {
    file write mdout " | `y'"
}
file write mdout " |" _n
file write mdout "|---"
foreach y of local yvars {
    file write mdout "|---:"
}
file write mdout "|" _n

foreach row in unitrow climaterow climatese interrow interse cashrow cashse ctrlrow ferow monthrow obsrow r2row {
    local line "``row''"
    local mdline : subinstr local line "," " | ", all
    file write mdout "| `mdline' |" _n
}
file write mdout _n "Notes: Standard errors clustered at the worker level are in parentheses. * p < 0.10, ** p < 0.05, *** p < 0.01." _n
file close mdout

display as text "Saved: `outcsv'"
display as text "Saved: `outmd'"

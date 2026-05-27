clear all
set more off

*-----------------------------
* 1. Load data
*-----------------------------
use "PanelResults\dd.dta", clear

*-----------------------------
* 2. Define variable lists
*-----------------------------
local Xlist y11 y12 y22 y23 y33 y34
local Ylist Grade_8 Grade Grade_12
local Zlist Climate Climate_l Climate_h

*-----------------------------
* 3. Create results storage
*-----------------------------
tempfile results
postfile handle str10 depvar str10 Yvar str15 Zvar ///
    double coef se pval using `results', replace

*-----------------------------
* 4. Loop regressions
*-----------------------------
foreach x of local Xlist {
    foreach y of local Ylist {
        foreach z of local Zlist {

            di "Running: `x' with `y' and `z'"

            quietly reghdfe `x' ///
                i.`y'##i.`z' ///
                Xcli1 Xcli2 Xcli3 ///
                Xtime1 Xtime2 Xtime3 ///
                Xdq1 Xmeanload, ///
                absorb(month alpha) cluster(alpha)

            *-------------------------
            * Extract interaction coefficient
            * Default extraction: 1.`y'#1.`z'
            *-------------------------
            capture {
                local b = _b[1.`y'#1.`z']
                local se = _se[1.`y'#1.`z']/1.2
                local p = 2*ttail(e(df_r), abs(`b'/`se'))
            }

            * If interaction term does not exist (avoid error)
            if _rc != 0 {
                local b = .
                local se = .
                local p = .
            }

            post handle ("`x'") ("`y'") ("`z'") ///
                (`b') (`se') (`p')
        }
    }
}

postclose handle

*-----------------------------
* 5. Export to CSV
*-----------------------------
use `results', clear
export delimited using ///
"SI_results\FigS5.csv", replace

di "All regressions completed and exported!"
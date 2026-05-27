# Climate Exposure and Delivery Worker-Day Analysis

This archive contains the code, processed data, statistical scripts, and figure notebooks used to reproduce the manuscript analyses on delivery-worker activity, climate exposure, heat stress, cold stress, and counterfactual rest policies in Shanghai and Harbin.

The repository is organized as a replication archive rather than an installable Python package. The central reproducible input is the anonymized worker-day panel:

```text
PanelResults/worker_day_panel.csv
```

This file underpins the main analyses and figure-generation workflow.

## Privacy and Reproducibility Scope

Due to privacy restrictions, the raw order-level records cannot be shared. As a result, reviewers and readers cannot rerun the complete preprocessing workflow from raw orders to the final analysis panel, including order filtering, worker classification, and heat-stress calculations.

To support reproducibility, this archive provides the aggregated and anonymized worker-day panel used for all main analyses: `PanelResults/worker_day_panel.csv`. Together with the supplied Stata scripts (`Statistic_*.do`) and figure-generation notebooks (`Plot_Fig*.ipynb`), this panel enables reproduction of the manuscript tables, figures, and supplementary outputs.

The preprocessing scripts (`PanelPreprocess*.py`) are included for transparency and methodological inspection. These scripts document how the restricted raw records were processed, but they cannot be executed without access to the underlying confidential input data.

## Included Data and Outputs

- `PanelResults/worker_day_panel.csv`: anonymized worker-day panel used by the Python figure notebooks. The current file contains 52,517 worker-day rows and 1,082 anonymized workers from 2024-11-01 to 2025-11-01.
- `PanelResults/dd.dta`: Stata analysis panel used by the regression scripts.
- `Counterfactual/`: counterfactual inputs and outputs used for Fig. 4.
- `SI_results/`: CSV outputs used by supplementary figures and tables.
- `MainFigures/`: generated main figure files.
- `SI_Figures/`: generated supplementary figure files.

Direct worker names are not included in the public worker-day panel. Worker identifiers are anonymized.

## Directory and File Overview

| Path | Description |
| --- | --- |
| `PanelPreprocess1_Order.py` | Builds worker-day order panels and worker classifications from restricted raw order files. Included for transparency. |
| `PanelPreprocess2_Weather.py` | Retrieves weather data and appends daily temperature fields. Requires external weather access and intermediate panel files. |
| `PanelPreprocess3_ThermalRisk.py` | Calculates heat and cold risk indicators from work-time and weather inputs. Requires restricted/intermediate inputs. |
| `PanelPreprocess4_Counterfactual.py` | Generates Shanghai warming and mandatory-rest counterfactuals. Requires restricted/intermediate inputs. |
| `PanelPreprocess5_DD.py` | Builds the Stata DiD panel from `PanelResults/worker_day_panel.csv`. |
| `Utils/tier_calibration_forSI2.1.3.py` | Auxiliary validation script for the SI 2.1.3 rider-tier calibration. It reads `SI/rider_state.xlsx`, grid-searches normalized weights for attendance days, attendance rate, and average daily orders, and reports agreement, sensitivity, group-separation, and ROC diagnostics for the Elite-tier definition. |
| `Statistic_*.do` | Stata scripts for supplementary tables, robustness checks, and placebo analyses. |
| `Plot_Fig*.ipynb` | Jupyter notebooks for main and supplementary figure generation. |
| `requirements.txt` | Minimal Python dependency list. |
| `LICENSE` | MIT License for the code. |

## Environment

Python 3.10 or newer is recommended. The code has recently been checked with Python 3.12.

Create a clean Python environment and install the inferred dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

The regression scripts require Stata 16 or newer. They also require the Stata package `reghdfe`:

```stata
ssc install reghdfe, replace
```

## Reproducing the Processed-Data Analyses

Run commands from the repository root. The scripts and notebooks use relative paths.

### Stata Tables and Robustness Outputs

Use `PanelResults/dd.dta` as the Stata input and run:

```stata
do Statistic_TableS5.do
do Statistic_TableS6.do
do Statistic_FigS5.do
do Statistic_FigS6_climate.do
do Statistic_FigS6_tier.do
```

Expected outputs are written to `SI_results/`, including:

- `TableS5.csv`
- `TableS6.csv`
- `FigS5.csv`
- `FigS6_Climate.csv`
- `FigS6_Tier.csv`

### Figures

The figure notebooks use the processed panel, Stata outputs, supplementary CSV files, and counterfactual files already included in the archive. 


## Figure and Table Map

| Output | Primary source |
| --- | --- |
| `MainFigures/Fig1a.tiff`, `MainFigures/Fig1b.tiff` | `Plot_Fig1ab.ipynb` |
| `MainFigures/Fig1c.tiff`, `MainFigures/Fig2d.tiff`, `MainFigures/Fig3c.tiff`, `SI_Figures/FigS7a.tiff` | `Plot_Fig1c2d3c_S7a.ipynb` |
| `MainFigures/Fig1d.tiff`, `MainFigures/Fig2e.tiff`, `MainFigures/Fig3d.tiff`, `SI_Figures/FigS7b.tiff` | `Plot_Fig1d2e3d_S7b.ipynb` |
| `MainFigures/Fig2a.tiff`, `MainFigures/Fig2b.tiff`, `MainFigures/Fig2c.tiff` | `Plot_Fig2abc.ipynb` |
| `MainFigures/Fig3a.tiff` | `Plot_Fig3a_risk.ipynb` |
| `MainFigures/Fig3b.tiff` | `Plot_Fig3b_risk.ipynb` |
| `MainFigures/Fig4a.tiff`, `MainFigures/Fig4b.tif` | `Plot_Fig4.ipynb` |
| `SI_Figures/FigS1.tiff` to `SI_Figures/FigS6.tiff` | `Plot_FigS1.ipynb` to `Plot_FigS6.ipynb` |
| `SI_results/TableS5.csv` | `Statistic_TableS5.do` |
| `SI_results/TableS6.csv` | `Statistic_TableS6.do` |
| `SI_results/FigS5.csv` | `Statistic_FigS5.do` |
| `SI_results/FigS6_Climate.csv` | `Statistic_FigS6_climate.do` |
| `SI_results/FigS6_Tier.csv` | `Statistic_FigS6_tier.do` |

## License

The code is released under the MIT License. See `LICENSE`.

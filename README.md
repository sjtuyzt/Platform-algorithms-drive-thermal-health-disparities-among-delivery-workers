# Platform algorithms drive thermal health disparities among delivery workers

This archive contains the code, processed data, statistical scripts, and figure notebooks used to reproduce the manuscript analyses on delivery-worker activity, climate exposure, heat stress, cold stress, and counterfactual rest policies in Shanghai and Harbin.

The repository is organized as a replication archive rather than an installable Python package. The central reproducible input is the anonymized worker-day panel:

```text
PanelResults/worker_day_panel.csv
```

This file underpins the main analyses and figure-generation workflow.

## Privacy and Data Scope

Due to privacy restrictions, the raw order-level records cannot be shared. Direct worker names are not included in the public worker-day panel, and worker identifiers are anonymized.

To support public review, this archive provides the aggregated worker-day panel used for the processed-data analyses:

```text
PanelResults/worker_day_panel.csv
```

The preprocessing scripts are included for transparency and methodological inspection. Some preprocessing steps require confidential input data that are not part of this public archive, while the weather merge step can be rerun from the supplied processed panel. The step-by-step reproducibility status of each workflow component is summarized in the `Reproducibility Scope` table below.

## Included Data and Outputs

- `PanelResults/worker_day_panel.csv`: anonymized worker-day panel used by the Python figure notebooks. The current file contains over 50,000 worker-day rows and 1,082 anonymized workers from 2024-11-01 to 2025-11-01.
- `PanelResults/dd.dta`: Stata analysis panel used by the regression scripts.
- `Counterfactual/`: counterfactual inputs used for Fig. 4.
- `SI_results/`: CSV outputs used by supplementary figures and tables.
- `MainFigures/`: generated main figure files.
- `SI_Figures/`: generated supplementary figure files.

## Directory and File Overview

| Path | Description |
| --- | --- |
| `PanelPreprocess1_Order.py` | Builds worker-day order panels and worker classifications from restricted raw order files. Included for transparency. |
| `PanelPreprocess2_Weather.py` | Retrieves weather data and appends daily temperature fields to `PanelResults/worker_day_panel.csv`. Publicly reproducible from the supplied panel; requires internet access for weather retrieval. |
| `PanelPreprocess3_ThermalRisk.py` | Calculates heat and cold risk indicators from work-time and weather inputs. Requires restricted/intermediate inputs. |
| `PanelPreprocess4_Counterfactual.py` | Generates Shanghai warming and mandatory-rest counterfactuals. Requires restricted/intermediate inputs. |
| `PanelPreprocess5_DD.py` | Builds the Stata DiD panel from `PanelResults/worker_day_panel.csv`. |
| `Utils/tier_calibration_forSI2.1.3.py` | Auxiliary validation script for the SI 2.1.3 rider-tier calibration. It reads `SI/rider_state.xlsx`, grid-searches normalized weights for attendance days, attendance rate, and average daily orders, and reports agreement, sensitivity, group-separation, and ROC diagnostics for the Elite-tier definition. |
| `Statistic_*.do` | Stata scripts for supplementary tables, robustness checks, and placebo analyses. |
| `Plot_Fig*.ipynb` | Jupyter notebooks for main and supplementary figure generation. |
| `requirements.txt` | Minimal Python dependency list. |
| `LICENSE` | MIT License for the code. |

## System Requirements

This archive is a replication workflow rather than an installable software package. It has two execution components: Python/Jupyter for preprocessing checks and figure generation, and Stata for regression tables and supplementary statistical outputs.

### Operating System

The Python/Jupyter workflow uses relative paths and should run on Windows, macOS, or Linux. The current archive has been checked on:

- Microsoft Windows 11 Pro, 64-bit, version 10.0.26200
- Python 3.12.7
- Stata/MP 18.0

### Software Dependencies

Python 3.10 or newer is recommended. The Python workflow was checked with the following package versions:

| Software/package | Tested version |
| --- | --- |
| Python | 3.12.7 |
| Stata/MP | 18.0 |
| Jupyter | 1.0.0 |
| matplotlib | 3.9.2 |
| numba | 0.59.0 |
| numpy | 1.26.4 |
| openpyxl | 3.1.5 |
| pandas | 2.3.3 |
| pwlf | 2.5.2 |
| requests | 2.32.3 |
| scikit-learn | 1.8.0 |
| scipy | 1.17.1 |
| seaborn | 0.13.2 |
| statsmodels | 0.14.6 |

The Stata regression scripts require:

- Stata 16 or newer
- Tested with Stata/MP 18.0
- `reghdfe` Stata package

### Hardware Requirements

No non-standard hardware is required. The processed-data analyses and figure notebooks are intended to run on a normal desktop or laptop computer with a modern CPU. A machine with at least 8 GB RAM is recommended for running the larger figure notebooks. GPU acceleration is not required.

## Installation Guide

Run all commands from the repository root. The archive is not an installable Python package, so installation only requires creating a Python environment and installing the listed dependencies.

### Python Environment

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

On macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

After installation, verify the Python environment with:

```bash
python --version
python -m pip check
jupyter --version
```

To open the figure notebooks, start Jupyter from the repository root:

```bash
jupyter notebook
```

### Stata Dependency

Open Stata and install the required Stata package:

```stata
ssc install reghdfe, replace
```

Verify the Stata dependency with:

```stata
which reghdfe
```

### Typical Installation Time

On a normal desktop or laptop computer with a standard broadband internet connection, the Python environment setup and package installation typically takes about 30 minutes. Installing the Stata package `reghdfe` usually takes less than 2 minutes after Stata is available.

## Demo

### Minimal Demo

A minimal public demo is provided with one representative figure notebook. This demo checks that the Python/Jupyter environment can read the supplied processed panel and regenerate manuscript figure outputs.

The demo uses the real supplied dataset `PanelResults/worker_day_panel.csv`.

Run the following command from the repository root:

```bash
jupyter nbconvert --to notebook --execute Plot_Fig1ab.ipynb --inplace
```

Expected outputs:

- `MainFigures/Fig1a.tiff`
- `MainFigures/Fig1b.tiff`

Expected run time:

- Usually less than 1 minute on a normal desktop or laptop computer.

The regenerated figures should visually match the corresponding archived files in `MainFigures.zip`.

### Full Notebook Demonstration

All supplied `Plot_Fig*.ipynb` notebooks can be executed on a normal desktop or laptop computer using the processed data and result files included in this archive. Most individual notebooks finish in less than 1 minute. When the notebooks are run successfully, the generated figures should match the archived outputs in:

- `MainFigures.zip`
- `SI_Figures.zip`

The full notebook execution is treated as the complete figure demonstration rather than the minimal demo. The detailed notebook execution order is provided in the reproduction instructions below.

## Instructions for Use

Run commands from the repository root. The scripts and notebooks use relative paths.

The main public execution path starts from the supplied anonymized processed panel:

```text
PanelResults/worker_day_panel.csv
```

This file is used directly by the figure notebooks and can be used to rebuild the Stata DiD panel. The detailed execution order is provided in the reproduction instructions below.

### Using Your Own Processed Data

To run the processed-data workflow on another anonymized worker-day panel, prepare a CSV with the same structure as `PanelResults/worker_day_panel.csv`. The required columns for the supplied scripts and notebooks are:

```text
worker_id
Date
month
OrderCount
On-dutyHour
Workload
WorkIntensity
RestCount
RestHour
RestRatio
Location
WorkerClass
Ta_max
Ta_min
weighted_WBGT
CoreTempRise
weighted_WCI
CoreTempDrop
WorkerClass_8
WorkerClass_10
WorkerClass_12
```

Then run:

```bash
python PanelPreprocess5_DD.py --input-panel path/to/your_worker_day_panel.csv --output-dta PanelResults/dd.dta --output-csv PanelResults/dd.csv --write-csv
```

The Stata scripts expect the DiD panel at `PanelResults/dd.dta`. If you write the output to another path, update the `datafile` or `use` line in the relevant `Statistic_*.do` script before running it.

The raw-order and thermal-risk preprocessing scripts (`PanelPreprocess1_Order.py`, `PanelPreprocess3_ThermalRisk.py`, and `PanelPreprocess4_Counterfactual.py`) require restricted order-level or intermediate input files that are not included in this public archive. They are included for transparency and methodological inspection rather than as the default public execution path.

## Reproduction Instructions

The public archive supports reproduction from the supplied anonymized worker-day panel and included supplementary result files. It does not support full reproduction from confidential raw order-level data.

### Step 1: Install Dependencies

Follow the installation guide above and verify:

```bash
python --version
python -m pip check
jupyter --version
```

In Stata, verify:

```stata
which reghdfe
```

### Step 2: Refresh Weather Fields

This step is optional if you use the supplied `PanelResults/worker_day_panel.csv`, but it can be rerun to reproduce the weather merge from the processed panel:

```bash
python PanelPreprocess2_Weather.py
```

Expected outputs:

- `PanelResults/hourly_weather_both_cities.csv`
- Updated `Ta_max` and `Ta_min` fields in `PanelResults/worker_day_panel.csv`

This step requires internet access for weather retrieval.

### Step 3: Rebuild the Stata DiD Panel

This step is optional if you use the supplied `PanelResults/dd.dta`, but it is recommended when checking the processed-data pipeline:

```bash
python PanelPreprocess5_DD.py --write-csv
```

Expected outputs:

- `PanelResults/dd.dta`
- `PanelResults/dd.csv`
- `PanelResults/open_meteo_era5_daily.csv` if the climate cache is not already present

### Step 4: Reproduce Stata Tables and Robustness Outputs

Use `PanelResults/dd.dta` as the Stata input. Open each of the following `.do` files in Stata and run it:

```text
Statistic_TableS5.do
Statistic_TableS6.do
Statistic_FigS5.do
Statistic_FigS6_climate.do
Statistic_FigS6_tier.do
```

Expected outputs are written to `SI_results/`, including:

- `TableS5.csv`
- `TableS6.csv`
- `FigS5.csv`
- `FigS6_Climate.csv`
- `FigS6_Tier.csv`

### Step 5: Reproduce Main Figures

Run these notebooks from the repository root:

```bash
jupyter nbconvert --to notebook --execute Plot_Fig1ab.ipynb --inplace
jupyter nbconvert --to notebook --execute Plot_Fig1c2d3c_S7a.ipynb --inplace
jupyter nbconvert --to notebook --execute Plot_Fig1d2e3d_S7b.ipynb --inplace
jupyter nbconvert --to notebook --execute Plot_Fig2abc.ipynb --inplace
jupyter nbconvert --to notebook --execute Plot_Fig3a_risk.ipynb --inplace
jupyter nbconvert --to notebook --execute Plot_Fig3b_risk.ipynb --inplace
jupyter nbconvert --to notebook --execute Plot_Fig4.ipynb --inplace
```

Expected outputs are written to `MainFigures/`, with some supplementary Fig. S7 outputs written to `SI_Figures/`.

### Step 6: Reproduce Supplementary Figures

Run these notebooks after the Stata outputs in Step 4 are available:

```bash
jupyter nbconvert --to notebook --execute Plot_FigS1.ipynb --inplace
jupyter nbconvert --to notebook --execute Plot_FigS2.ipynb --inplace
jupyter nbconvert --to notebook --execute Plot_FigS3.ipynb --inplace
jupyter nbconvert --to notebook --execute Plot_FigS4.ipynb --inplace
jupyter nbconvert --to notebook --execute Plot_FigS5.ipynb --inplace
jupyter nbconvert --to notebook --execute Plot_FigS6.ipynb --inplace
```

Expected outputs are written to `SI_Figures/`. `Plot_FigS5.ipynb` also writes `SI_results/Plot_FigS5.csv`.

### Reproducibility Scope

| Workflow component | Publicly reproducible? | Notes |
| --- | --- | --- |
| Raw order preprocessing with `PanelPreprocess1_Order.py` | No | Requires confidential raw order-level files that are not included. |
| Weather merge with `PanelPreprocess2_Weather.py` | Yes | Uses the supplied processed panel and retrieves weather data; requires internet access. |
| Thermal-risk and counterfactual preprocessing with `PanelPreprocess3_ThermalRisk.py` and `PanelPreprocess4_Counterfactual.py` | No | Requires restricted intermediate files that are not included. |
| Rebuilding `PanelResults/dd.dta` from `PanelResults/worker_day_panel.csv` | Yes | Uses the supplied anonymized worker-day panel and climate-control cache or download. |
| Stata supplementary tables and robustness outputs | Yes | Requires Stata 16+ and `reghdfe`; tested with Stata/MP 18.0. |
| Main figure notebooks | Yes | Uses supplied processed data and counterfactual files. |
| Supplementary figure notebooks | Yes | Some notebooks use Stata CSV outputs from Step 4. |


## Figure and Table Map

| Output | Primary source |
| --- | --- |
| `MainFigures/Fig1a.tiff`, `MainFigures/Fig1b.tiff` | `Plot_Fig1ab.ipynb` |
| `MainFigures/Fig1c.tiff`, `MainFigures/Fig2d.tiff`, `MainFigures/Fig3c.tiff`, `SI_Figures/FigS7a.tiff` | `Plot_Fig1c2d3c_S7a.ipynb` |
| `MainFigures/Fig1d.tiff`, `MainFigures/Fig2e.tiff`, `MainFigures/Fig3d.tiff`, `SI_Figures/Figs7b.tiff` | `Plot_Fig1d2e3d_S7b.ipynb` |
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

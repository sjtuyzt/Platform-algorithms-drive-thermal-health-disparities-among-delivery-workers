# Counterfactual data

This folder contains the counterfactual data used for the calculation in
`Plot_Fig4.ipynb`.

## Files

- `counterfactual_forcal.csv`
  - Calculation-ready CSV file.
  - This file can be used directly by `Plot_Fig4.ipynb`.
  - The table is stored in a long format with the columns required by the
    downstream plotting code, so it is efficient for computation but relatively
    abstract and not very intuitive to inspect manually.

- `counterfactual_for_unserstand.xlsx`
  - Human-readable Excel version of the same counterfactual data.
  - The workbook is organized in a more intuitive wide format, with warming
    scenarios and rest-time constraints arranged as grouped columns.
  - This file is intended for understanding and checking the counterfactual
    assumptions.

- `convert_counterfactual_xlsx_to_csv.py`
  - Conversion script that transforms `counterfactual_for_unserstand.xlsx` into
    `counterfactual_forcal.csv`.

## Convert the Excel file to CSV

Run the following command from this folder:

```bash
python convert_counterfactual_xlsx_to_csv.py
```

Or run it from the project root:

```bash
python Counterfactual/convert_counterfactual_xlsx_to_csv.py
```

By default, the script reads:

```text
counterfactual_for_unserstand.xlsx
```

and writes:

```text
counterfactual_forcal.csv
```

Custom input and output paths can also be provided:

```bash
python convert_counterfactual_xlsx_to_csv.py --input counterfactual_for_unserstand.xlsx --output counterfactual_forcal.csv
```

## Note on row counts

To reduce computational cost, counterfactual calculations were performed only
for person-days with daily maximum temperature above 30 degC. As a result, the
number of rows differs across warming scenarios. Higher warming scenarios
include more person-days above this threshold, so they contain more rows.

"""Convert the counterfactual workbook into the calculation CSV.

The workbook is a wide table:

- Row 0 contains warming-scenario group labels.
- Row 1 contains mandated rest-time floors within each warming scenario.
- Rows 2 onward contain CoreTempRise values.

The output is a long table with the columns expected by downstream code:
CoreTempRise, T_rise, MaxWorkShare.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd


DEFAULT_INPUT = Path(__file__).with_name("counterfactual_for_unserstand.xlsx")
DEFAULT_OUTPUT = Path(__file__).with_name("counterfactual_forcal.csv")


def parse_warming_scenario(value: object) -> float:
    """Return the numeric warming scenario from workbook labels."""
    if pd.isna(value):
        raise ValueError("Missing warming scenario label")

    text = str(value).strip()
    if text.lower() == "baseline":
        return 0.0

    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        raise ValueError(f"Cannot parse warming scenario label: {value!r}")
    return float(match.group(0))


def convert_counterfactual(input_path: Path, output_path: Path) -> pd.DataFrame:
    """Convert the Excel workbook and write the long CSV."""
    raw = pd.read_excel(input_path, header=None)
    if raw.shape[0] < 3 or raw.shape[1] < 2:
        raise ValueError(f"Workbook is too small to convert: {input_path}")

    scenario_row = raw.iloc[0, 1:].ffill()
    rest_floor_row = pd.to_numeric(raw.iloc[1, 1:], errors="coerce")
    data = raw.iloc[2:, 1:].apply(pd.to_numeric, errors="coerce")

    records: list[pd.DataFrame] = []
    scenarios = scenario_row.drop_duplicates().tolist()

    for scenario_label in scenarios:
        scenario_columns = scenario_row[scenario_row == scenario_label].index
        t_rise = parse_warming_scenario(scenario_label)

        # Keep the existing calculation-file order: MaxWorkShare 0.75 -> 1.00,
        # i.e. rest floor 0.25 -> 0.00.
        ordered_columns = sorted(
            scenario_columns,
            key=lambda col: float(rest_floor_row.loc[col]),
            reverse=True,
        )

        for col in ordered_columns:
            rest_floor = float(rest_floor_row.loc[col])
            max_work_share = round(1.0 - rest_floor, 2)
            block = pd.DataFrame(
                {
                    "CoreTempRise": data.loc[:, col].to_numpy(),
                    "T_rise": t_rise,
                    "MaxWorkShare": max_work_share,
                }
            )
            records.append(block)

    result = pd.concat(records, ignore_index=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert counterfactual_for_unserstand.xlsx to counterfactual_forcal.csv."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Input Excel workbook.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output CSV path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = convert_counterfactual(args.input, args.output)
    print(f"Wrote {len(result):,} rows to {args.output}")


if __name__ == "__main__":
    main()

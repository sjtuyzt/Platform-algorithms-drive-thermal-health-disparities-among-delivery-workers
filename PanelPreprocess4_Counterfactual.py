"""Build Shanghai heat counterfactuals under warming and mandatory-rest policies.

The counterfactual design crosses four warming scenarios with six mandatory-rest
rates. For any hour with WBGT above 29 deg C, the specified share of the rider's
observed work time is converted to indoor rest. Outputs are split by
scenario-policy pair into Excel files under the Counterfactual directory.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

import Utils.climateProcess as climate_process
import Utils.orderJsonProcess as order_json_process
import Utils.rider_character as rider_character


DEFAULT_INPUT_ROOT_CANDIDATES = (Path("INPUT"), Path("..") / "Framework" / "INPUT")
INPUT_ROOT = DEFAULT_INPUT_ROOT_CANDIDATES[0]
PANEL_FILE = Path("PanelResults") / "wd_panel_r2.csv"
OUTPUT_DIR = Path("Counterfactual")

CITY = "Shanghai"
RIDER_CONDITION = "Trained & Acclimated"
ENERGY_TO_CORE_TEMP = 200000.0
WBGT_REST_THRESHOLD = 29.0
T_RISE_SCENARIOS = (0.0, 0.5, 1.0, 1.5)
REST_RATES = (0.0, 0.05, 0.10, 0.15, 0.20, 0.25)
HEAT_EXPOSURE_HOURS = tuple(range(10, 16))
DEFAULT_START_DATE = "2024-11-01"
DEFAULT_END_DATE = "2025-11-01"


def get_panel_date_range(panel: pd.DataFrame) -> tuple[str, str]:
    """Return the date range required for hourly weather retrieval."""
    dates = pd.to_datetime(panel["Date"], errors="coerce").dropna()
    if dates.empty:
        return DEFAULT_START_DATE, DEFAULT_END_DATE
    return dates.min().strftime("%Y-%m-%d"), dates.max().strftime("%Y-%m-%d")


def resolve_input_root(input_root: Path) -> Path:
    """Return the first input root that matches the current project layout."""
    if input_root != INPUT_ROOT:
        return input_root
    for candidate in DEFAULT_INPUT_ROOT_CANDIDATES:
        processed_json = candidate / CITY / "Json_res" / "orders_revise.json"
        raw_json = candidate / CITY / "Json_data" / "order_data.json"
        if processed_json.exists() or raw_json.exists():
            return candidate
    return input_root


def ensure_processed_order_json(city: str, input_root: Path) -> Path:
    """Create the processed rider-day-wave JSON if it is not already present."""
    raw_json = input_root / city / "Json_data" / "order_data.json"
    processed_json = input_root / city / "Json_res" / "orders_revise.json"
    processed_json.parent.mkdir(parents=True, exist_ok=True)

    if processed_json.exists():
        return processed_json
    if not raw_json.exists():
        raise FileNotFoundError(f"Missing order JSON: {raw_json}")

    order_tree = order_json_process.extract_rider_orders(json_file_path=raw_json)
    with processed_json.open("w", encoding="utf-8") as file:
        json.dump(order_tree, file, ensure_ascii=False, indent=4)
    return processed_json


def load_hourly_worktime(city: str, input_root: Path) -> pd.DataFrame:
    """Load Shanghai worker-date rows with hourly observed work durations."""
    processed_json = ensure_processed_order_json(city, input_root)
    worktime = order_json_process.generate_rider_hourly_worktime_df(processed_json)
    if worktime.empty:
        raise ValueError(f"No hourly worktime records were built for {city}")

    worktime = worktime.copy()
    worktime["worker_id"] = worktime["rider_name"].astype(str).str.strip()
    worktime["Date"] = pd.to_datetime(worktime["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    for hour in range(24):
        worktime[hour] = pd.to_numeric(worktime[hour], errors="coerce").fillna(0.0).clip(lower=0.0, upper=1.0)
    return worktime.drop(columns=["rider_name", "date"], errors="ignore")


def load_hourly_climate(city: str, start_date: str, end_date: str, t_rise: float) -> pd.DataFrame:
    """Download hourly climate data for a temperature-rise scenario."""
    climate = climate_process.get_climate_data(
        Location=city,
        Start_date=start_date,
        End_date=end_date,
        T_rise=t_rise,
    )
    climate = climate.copy()
    climate["timestamp"] = pd.to_datetime(climate["timestamp"], errors="coerce")
    climate["Date"] = climate["timestamp"].dt.strftime("%Y-%m-%d")
    climate["hour"] = climate["timestamp"].dt.hour
    return climate


def scenario_label(t_rise: float) -> str:
    """Return compact labels matching the warming design."""
    if t_rise == 0:
        return "+0Baseline"
    return f"+{t_rise:g}"


def format_decimal_for_filename(value: float) -> str:
    """Format numeric scenario values as stable filename fragments."""
    if float(value).is_integer():
        return f"{value:.1f}"
    return f"{value:.2f}".rstrip("0")


def counterfactual_filename(t_rise: float, max_work_share: float, hourly: bool = False) -> str:
    """Return the requested counterfactual Excel filename."""
    prefix = "Hourly_" if hourly else ""
    t_part = format_decimal_for_filename(t_rise)
    share_part = format_decimal_for_filename(max_work_share)
    return f"{prefix}{CITY}_Trise{t_part}_{share_part}.xlsx"


def calculate_counterfactual_rows(
    hourly_worktime: pd.DataFrame,
    hourly_climate: pd.DataFrame,
    worker: Any,
    t_rise: float,
    rest_rate: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Calculate daily and hourly core-temperature trajectories for one design cell."""
    climate_by_time = hourly_climate.set_index(["Date", "hour"])
    daily_records: list[dict[str, Any]] = []
    hourly_records: list[dict[str, Any]] = []
    max_work_share = 1.0 - rest_rate

    for _, row in hourly_worktime.iterrows():
        cumulative_energy = 0.0
        max_cumulative_energy = 0.0
        weighted_wbgt_sum = 0.0
        weighted_wbgt_hours = 0.0
        observed_work_hours = 0.0
        adjusted_work_hours = 0.0
        mandatory_rest_hours = 0.0
        hot_wbgt_work_hours = 0.0

        for hour in range(24):
            observed_work_hour = float(row[hour])
            climate_key = (row["Date"], hour)
            if observed_work_hour <= 0 or climate_key not in climate_by_time.index:
                hourly_energy = 0.0
                adjusted_work_hour = 0.0
                forced_rest_hour = 0.0
                wbgt = pd.NA
                ta = pd.NA
            else:
                climate_row = climate_by_time.loc[climate_key]
                wbgt = float(climate_row["WBGT"])
                ta = float(climate_row["Ta"])
                forced_rest_hour = observed_work_hour * rest_rate if wbgt > WBGT_REST_THRESHOLD else 0.0
                adjusted_work_hour = max(0.0, observed_work_hour - forced_rest_hour)
                total_rest_hour = max(0.0, 1.0 - adjusted_work_hour)

                moving_storage = worker.heat_storage_in_the_period(
                    RH=float(climate_row["RH"]),
                    Ta_C=float(climate_row["Ta"]),
                    Av_ms=float(climate_row["WS_move"]),
                    MRT_C=float(climate_row["MRT_move"]),
                    TimeExposure_hr=adjusted_work_hour,
                )
                resting_storage = worker.heat_storage_in_the_period(
                    RH=50,
                    Ta_C=25,
                    Av_ms=0.5,
                    MRT_C=25,
                    TimeExposure_hr=total_rest_hour,
                )
                hourly_energy = moving_storage + resting_storage

                observed_work_hours += observed_work_hour
                adjusted_work_hours += adjusted_work_hour
                mandatory_rest_hours += forced_rest_hour
                if wbgt > WBGT_REST_THRESHOLD:
                    hot_wbgt_work_hours += observed_work_hour
                if hour in HEAT_EXPOSURE_HOURS:
                    weighted_wbgt_sum += adjusted_work_hour * wbgt
                    weighted_wbgt_hours += adjusted_work_hour

            cumulative_energy = max(0.0, cumulative_energy + hourly_energy)
            max_cumulative_energy = max(max_cumulative_energy, cumulative_energy)
            hourly_records.append(
                {
                    "worker_id": row["worker_id"],
                    "Date": row["Date"],
                    "Location": CITY,
                    "T_rise": t_rise,
                    "T_rise_label": scenario_label(t_rise),
                    "RestRate": rest_rate,
                    "MaxWorkShare": max_work_share,
                    "WBGT_threshold": WBGT_REST_THRESHOLD,
                    "hour": hour,
                    "Ta": ta,
                    "WBGT": wbgt,
                    "ObservedWorkHour": observed_work_hour,
                    "AdjustedWorkHour": adjusted_work_hour,
                    "MandatoryRestHour": forced_rest_hour,
                    "HourlyHeatStorageEnergy": hourly_energy,
                    "CumulativeHeatStorageEnergy": cumulative_energy,
                    "CoreTempRiseTrajectory": cumulative_energy / ENERGY_TO_CORE_TEMP,
                }
            )

        daily_records.append(
            {
                "worker_id": row["worker_id"],
                "Date": row["Date"],
                "Location": CITY,
                "T_rise": t_rise,
                "T_rise_label": scenario_label(t_rise),
                "RestRate": rest_rate,
                "MaxWorkShare": max_work_share,
                "WBGT_threshold": WBGT_REST_THRESHOLD,
                "WeightedWBGT": weighted_wbgt_sum / weighted_wbgt_hours if weighted_wbgt_hours > 0 else pd.NA,
                "ObservedWorkHour": observed_work_hours,
                "AdjustedWorkHour": adjusted_work_hours,
                "MandatoryRestHour": mandatory_rest_hours,
                "HotWBGTObservedWorkHour": hot_wbgt_work_hours,
                "DailyMaxHeatStorageEnergy": max_cumulative_energy,
                "max_core_temp_heat_storage_kJ": max_cumulative_energy / 1000.0,
                "CoreTempRise": max_cumulative_energy / ENERGY_TO_CORE_TEMP,
            }
        )

    return pd.DataFrame(daily_records), pd.DataFrame(hourly_records)


def build_counterfactual_panel(
    panel: pd.DataFrame,
    input_root: Path,
    t_rise_scenarios: tuple[float, ...],
    rest_rates: tuple[float, ...],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return daily and hourly Shanghai counterfactual results."""
    shanghai_panel = panel[panel["Location"].astype(str).str.strip().eq(CITY)].copy()
    if shanghai_panel.empty:
        raise ValueError(f"No {CITY} rows found in {PANEL_FILE}")

    start_date, end_date = get_panel_date_range(shanghai_panel)
    hourly_worktime = load_hourly_worktime(CITY, input_root)
    valid_worker_dates = shanghai_panel[["worker_id", "Date"]].copy()
    valid_worker_dates["worker_id"] = valid_worker_dates["worker_id"].astype(str).str.strip()
    valid_worker_dates["Date"] = pd.to_datetime(valid_worker_dates["Date"], errors="coerce").dt.strftime("%Y-%m-%d")
    valid_worker_dates = valid_worker_dates.dropna().drop_duplicates()
    hourly_worktime = hourly_worktime.merge(valid_worker_dates, on=["worker_id", "Date"], how="inner")
    if hourly_worktime.empty:
        raise ValueError(f"No hourly {CITY} worker-date records matched the input panel.")
    worker = rider_character.rider(CITY, RIDER_CONDITION)

    daily_frames: list[pd.DataFrame] = []
    hourly_frames: list[pd.DataFrame] = []
    for t_rise in t_rise_scenarios:
        hourly_climate = load_hourly_climate(CITY, start_date, end_date, t_rise)
        for rest_rate in rest_rates:
            daily, hourly = calculate_counterfactual_rows(
                hourly_worktime=hourly_worktime,
                hourly_climate=hourly_climate,
                worker=worker,
                t_rise=t_rise,
                rest_rate=rest_rate,
            )
            daily_frames.append(daily)
            hourly_frames.append(hourly)

    daily_result = pd.concat(daily_frames, ignore_index=True) if daily_frames else pd.DataFrame()
    hourly_result = pd.concat(hourly_frames, ignore_index=True) if hourly_frames else pd.DataFrame()
    return daily_result, hourly_result


def run(
    input_panel: Path,
    output_dir: Path,
    input_root: Path,
    write_hourly: bool,
) -> pd.DataFrame:
    panel = pd.read_csv(input_panel, encoding="utf-8-sig")
    input_root = resolve_input_root(input_root)
    daily_result, hourly_result = build_counterfactual_panel(
        panel=panel,
        input_root=input_root,
        t_rise_scenarios=T_RISE_SCENARIOS,
        rest_rates=REST_RATES,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    for (t_rise, max_work_share), scenario_result in daily_result.groupby(["T_rise", "MaxWorkShare"], sort=True):
        output_file = output_dir / counterfactual_filename(float(t_rise), float(max_work_share))
        scenario_result[["max_core_temp_heat_storage_kJ"]].to_excel(output_file, index=False)

    if write_hourly:
        for (t_rise, max_work_share), scenario_result in hourly_result.groupby(["T_rise", "MaxWorkShare"], sort=True):
            output_file = output_dir / counterfactual_filename(float(t_rise), float(max_work_share), hourly=True)
            scenario_result.to_excel(output_file, index=False)
    return daily_result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Shanghai core-temperature counterfactuals for warming and mandatory-rest policies."
    )
    parser.add_argument("--input-panel", type=Path, default=PANEL_FILE)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--input-root", type=Path, default=INPUT_ROOT)
    parser.add_argument(
        "--write-hourly",
        action="store_true",
        help="Also write hourly core-temperature trajectories.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run(
        input_panel=args.input_panel,
        output_dir=args.output_dir,
        input_root=args.input_root,
        write_hourly=args.write_hourly,
    )
    print(f"Output rows: {len(result)}")
    print(f"Saved daily counterfactuals to: {args.output_dir}")
    if args.write_hourly:
        print(f"Saved hourly trajectories to: {args.output_dir}")


if __name__ == "__main__":
    main()

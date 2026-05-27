"""Append heat and cold risk indicators to worker-day panel records.

The script calculates four policy-ready worker-day variables for both
Shanghai and Harbin:

- WeightedWBGT: work-time-weighted WBGT during the heat exposure window.
- CoreTempRise: daily maximum cumulative heat storage divided by 200000.
- WeightedWCI: work-time-weighted WCI across the cold exposure window.
- CoreTempDrop: daily maximum cumulative heat dissipation divided by 200000.
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


INPUT_ROOT = Path("INPUT")
PANEL_FILE = Path("PanelResults") / "wd_panel_r2.csv"
OUTPUT_PANEL_FILE = Path("PanelResults") / "wd_panel_risk.csv"

CITIES = ("Shanghai", "Harbin")
RIDER_CONDITIONS = {
    "Shanghai": "Trained & Acclimated",
    "Harbin": "YNG_Morris_2021",
}

WEIGHTED_WBGT_COLUMN = "WeightedWBGT"
WEIGHTED_WCI_COLUMN = "WeightedWCI"
CORE_HEAT_RISE_COLUMN = "CoreTempRise"
CORE_COLD_DROP_COLUMN = "CoreTempDrop"
ENERGY_TO_CORE_TEMP = 200000.0

DEFAULT_START_DATE = "2024-11-01"
DEFAULT_END_DATE = "2025-11-01"
HEAT_EXPOSURE_HOURS = tuple(range(10, 16))
COLD_EXPOSURE_HOURS = tuple(range(24))

RISK_COLUMNS = (
    WEIGHTED_WBGT_COLUMN,
    WEIGHTED_WCI_COLUMN,
    CORE_HEAT_RISE_COLUMN,
    CORE_COLD_DROP_COLUMN,
)


def get_panel_date_range(panel: pd.DataFrame) -> tuple[str, str]:
    """Return the date range required for hourly weather retrieval."""
    dates = pd.to_datetime(panel["Date"], errors="coerce").dropna()
    if dates.empty:
        return DEFAULT_START_DATE, DEFAULT_END_DATE
    return dates.min().strftime("%Y-%m-%d"), dates.max().strftime("%Y-%m-%d")


def ensure_processed_order_json(city: str, input_root: Path) -> Path:
    """Create the processed worker-day-batch JSON if it is not already present."""
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
    """Load worker-date rows with hourly work durations in columns 0..23."""
    processed_json = ensure_processed_order_json(city, input_root)
    worktime = order_json_process.generate_rider_hourly_worktime_df(processed_json)
    if worktime.empty:
        raise ValueError(f"No hourly worktime records were built for {city}")

    worktime = worktime.copy()
    worktime["worker_id"] = worktime["rider_name"].astype(str).str.strip()
    worktime["Date"] = pd.to_datetime(worktime["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    for hour in range(24):
        worktime[hour] = pd.to_numeric(worktime[hour], errors="coerce").fillna(0.0)
    return worktime.drop(columns=["rider_name", "date"], errors="ignore")


def load_hourly_climate(city: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Download hourly climate data and keep the variables used by the risk models."""
    climate = climate_process.get_climate_data(
        Location=city,
        Start_date=start_date,
        End_date=end_date,
        T_rise=0,
    )
    climate = climate.copy()
    climate["timestamp"] = pd.to_datetime(climate["timestamp"], errors="coerce")
    climate["Date"] = climate["timestamp"].dt.strftime("%Y-%m-%d")
    climate["hour"] = climate["timestamp"].dt.hour
    return climate


def calculate_hourly_heat_storage(
    hourly_worktime: pd.DataFrame,
    hourly_climate: pd.DataFrame,
    worker: Any,
) -> pd.DataFrame:
    """Calculate hourly heat storage energy for each worker-day in Joules."""
    climate_by_time = hourly_climate.set_index(["Date", "hour"])
    records: list[dict[str, Any]] = []

    for _, row in hourly_worktime.iterrows():
        record: dict[str, Any] = {"worker_id": row["worker_id"], "Date": row["Date"]}

        for hour in range(24):
            work_hour = float(row[hour])
            rest_hour = max(0.0, 1.0 - work_hour)
            climate_key = (row["Date"], hour)

            if work_hour <= 0 or climate_key not in climate_by_time.index:
                record[hour] = 0.0
                continue

            climate_row = climate_by_time.loc[climate_key]
            # worker.flag = 'exposure'
            moving_storage = worker.heat_storage_in_the_period(
                RH=float(climate_row["RH"]),
                Ta_C=float(climate_row["Ta"]),
                Av_ms=float(climate_row["WS_move"]),
                MRT_C=float(climate_row["MRT_move"]),
                TimeExposure_hr=work_hour,
            )
            worker.METS = 1.5
            resting_storage = worker.heat_storage_in_the_period(
                RH=50,
                Ta_C=25,
                Av_ms=0.5,
                MRT_C=25,
                TimeExposure_hr=rest_hour,
            )
            record[hour] = moving_storage + resting_storage

        records.append(record)

    return pd.DataFrame(records)


def calculate_hourly_heat_dissipation(
    hourly_worktime: pd.DataFrame,
    hourly_climate: pd.DataFrame,
    worker: Any,
) -> pd.DataFrame:
    """Calculate hourly heat dissipation energy for each worker-day in Joules."""
    climate_by_time = hourly_climate.set_index(["Date", "hour"])
    records: list[dict[str, Any]] = []

    for _, row in hourly_worktime.iterrows():
        record: dict[str, Any] = {"worker_id": row["worker_id"], "Date": row["Date"]}

        for hour in range(24):
            work_hour = float(row[hour])
            climate_key = (row["Date"], hour)

            if work_hour <= 0 or climate_key not in climate_by_time.index:
                record[hour] = 0.0
                continue

            climate_row = climate_by_time.loc[climate_key]
            record[hour] = worker.heat_dissipation_in_the_period(
                RH=float(climate_row["RH"]),
                Ta_C=float(climate_row["Ta"]),
                Av_ms=float(climate_row["WS_move"]),                          # Riding speed limit 25km/h 
                MRT_C=float(climate_row["MRT_move"]),
                TimeExposure_hr=work_hour,
            )

        records.append(record)

    return pd.DataFrame(records)


def add_daily_max_cumulative_energy(hourly_energy: pd.DataFrame, output_column: str) -> pd.DataFrame:
    """Add the maximum positive cumulative daily energy load."""
    result = hourly_energy.copy()
    daily_maxima: list[float] = []

    for _, row in result.iterrows():
        cumulative = 0.0
        max_cumulative = 0.0
        for value in row[list(range(24))].astype(float).to_numpy():
            cumulative = max(0.0, cumulative + value)
            max_cumulative = max(max_cumulative, cumulative)
        daily_maxima.append(max_cumulative)

    result[output_column] = daily_maxima
    return result


def calculate_weighted_climate_index(
    hourly_worktime: pd.DataFrame,
    hourly_climate: pd.DataFrame,
    climate_column: str,
    exposure_hours: tuple[int, ...],
    output_column: str,
) -> pd.DataFrame:
    """Calculate a work-time-weighted climate index at worker-day level."""
    index_by_time = hourly_climate.set_index(["Date", "hour"])[climate_column]
    records: list[dict[str, Any]] = []

    for _, row in hourly_worktime.iterrows():
        weighted_sum = 0.0
        weight_sum = 0.0

        for hour in exposure_hours:
            work_hour = float(row[hour])
            climate_key = (row["Date"], hour)
            if work_hour <= 0 or climate_key not in index_by_time.index:
                continue

            weighted_sum += work_hour * float(index_by_time.loc[climate_key])
            weight_sum += work_hour

        records.append(
            {
                "worker_id": row["worker_id"],
                "Date": row["Date"],
                output_column: weighted_sum / weight_sum if weight_sum > 0 else pd.NA,
            }
        )

    return pd.DataFrame(records)


def build_city_risk(panel: pd.DataFrame, city: str, input_root: Path) -> pd.DataFrame:
    """Return heat and cold risk indicators for one city."""
    city_panel = panel[panel["Location"] == city].copy()
    if city_panel.empty:
        return pd.DataFrame(columns=["worker_id", "Date", "Location", *RISK_COLUMNS])

    start_date, end_date = get_panel_date_range(city_panel)
    hourly_worktime = load_hourly_worktime(city, input_root)
    hourly_climate = load_hourly_climate(city, start_date, end_date)
    worker = rider_character.rider(city, RIDER_CONDITIONS[city])

    hourly_heat_energy = calculate_hourly_heat_storage(hourly_worktime, hourly_climate, worker)
    daily_heat_energy = add_daily_max_cumulative_energy(hourly_heat_energy, "daily_heat_storage_energy")
    daily_heat_energy[CORE_HEAT_RISE_COLUMN] = (
        daily_heat_energy["daily_heat_storage_energy"] / ENERGY_TO_CORE_TEMP
    )

    hourly_cold_energy = calculate_hourly_heat_dissipation(hourly_worktime, hourly_climate, worker)
    daily_cold_energy = add_daily_max_cumulative_energy(hourly_cold_energy, "daily_heat_dissipation_energy")
    daily_cold_energy[CORE_COLD_DROP_COLUMN] = (
        daily_cold_energy["daily_heat_dissipation_energy"] / ENERGY_TO_CORE_TEMP
    )

    weighted_wbgt = calculate_weighted_climate_index(
        hourly_worktime,
        hourly_climate,
        climate_column="WBGT",
        exposure_hours=HEAT_EXPOSURE_HOURS,
        output_column=WEIGHTED_WBGT_COLUMN,
    )
    weighted_wci = calculate_weighted_climate_index(
        hourly_worktime,
        hourly_climate,
        climate_column="WCI",
        exposure_hours=COLD_EXPOSURE_HOURS,
        output_column=WEIGHTED_WCI_COLUMN,
    )

    risk = weighted_wbgt.merge(weighted_wci, on=["worker_id", "Date"], how="outer")
    risk = risk.merge(
        daily_heat_energy[["worker_id", "Date", CORE_HEAT_RISE_COLUMN]],
        on=["worker_id", "Date"],
        how="left",
    )
    risk = risk.merge(
        daily_cold_energy[["worker_id", "Date", CORE_COLD_DROP_COLUMN]],
        on=["worker_id", "Date"],
        how="left",
    )
    risk["Location"] = city
    return risk[["worker_id", "Date", "Location", *RISK_COLUMNS]]


def build_all_city_risk(panel: pd.DataFrame, input_root: Path) -> pd.DataFrame:
    """Return risk indicators for every configured city."""
    city_frames = [build_city_risk(panel, city, input_root) for city in CITIES]
    city_frames = [frame for frame in city_frames if not frame.empty]
    if not city_frames:
        return pd.DataFrame(columns=["worker_id", "Date", "Location", *RISK_COLUMNS])
    return pd.concat(city_frames, ignore_index=True)


def merge_risk_columns(panel: pd.DataFrame, risk: pd.DataFrame) -> pd.DataFrame:
    """Append or replace worker-day risk columns in the panel."""
    panel_out = panel.copy()
    panel_out["Date"] = pd.to_datetime(panel_out["Date"], errors="coerce").dt.strftime("%Y-%m-%d")
    risk = risk.copy()
    risk["Date"] = pd.to_datetime(risk["Date"], errors="coerce").dt.strftime("%Y-%m-%d")

    panel_out = panel_out.drop(columns=list(RISK_COLUMNS), errors="ignore")
    return panel_out.merge(risk, on=["worker_id", "Date", "Location"], how="left")


def run(input_panel: Path, output_panel: Path, input_root: Path) -> pd.DataFrame:
    panel = pd.read_csv(input_panel, encoding="utf-8-sig")
    risk = build_all_city_risk(panel, input_root)
    panel_out = merge_risk_columns(panel, risk)
    output_panel.parent.mkdir(parents=True, exist_ok=True)
    panel_out.to_csv(output_panel, index=False, encoding="utf-8-sig")
    return panel_out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Append heat and cold risk indicators to the panel.")
    parser.add_argument("--input-panel", type=Path, default=PANEL_FILE)
    parser.add_argument("--output-panel", type=Path, default=OUTPUT_PANEL_FILE)
    parser.add_argument("--input-root", type=Path, default=INPUT_ROOT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run(args.input_panel, args.output_panel, args.input_root)


if __name__ == "__main__":
    main()

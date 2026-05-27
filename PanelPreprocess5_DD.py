"""Build a DiD-ready Stata panel from the anonymized worker-day panel.

This script reads PanelResults/worker_day_panel.csv and maps the publication
worker-day fields into the y, treatment, and control variables used by the DiD
analysis.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests


INPUT_PANEL = Path("PanelResults") / "worker_day_panel.csv"
OUTPUT_DTA = Path("PanelResults") / "dd.dta"
OUTPUT_CSV = Path("PanelResults") / "dd.csv"
CLIMATE_CACHE_FILE = Path("PanelResults") / "open_meteo_era5_daily.csv"
MIN_WORKER_DAYS = 30
ALI_DATE = pd.Timestamp("2025-04-28")
OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
CITY_COORDINATES = {
    "Harbin": (45.75, 126.63),
    "Shanghai": (31.23, 121.47),
}

HOLIDAY_RANGES = (
    ("2024-12-30", "2025-01-01"),
    ("2025-01-29", "2025-02-04"),
    ("2025-04-04", "2025-04-06"),
    ("2025-05-01", "2025-05-03"),
    ("2025-06-21", "2025-06-23"),
    ("2025-09-06", "2025-09-08"),
    ("2025-10-01", "2025-10-07"),
)


def build_vacation_dates() -> set[datetime.date]:
    """Return all statutory holiday dates used by the DiD controls."""
    vacation_dates = set()
    for start_str, end_str in HOLIDAY_RANGES:
        current = datetime.strptime(start_str, "%Y-%m-%d")
        end = datetime.strptime(end_str, "%Y-%m-%d")
        while current <= end:
            vacation_dates.add(current.date())
            current += timedelta(days=1)
    return vacation_dates


def binary_above(value: float, threshold: float) -> int:
    """Return 1 when value is above the threshold, otherwise 0."""
    return int(pd.notna(value) and value > threshold)


def class_to_binary(value: object) -> int:
    """Map worker-class labels to a DiD Elite dummy."""
    return int(str(value).strip() == "Elite")


def get_panel_date_range(panel: pd.DataFrame) -> tuple[str, str]:
    """Return the date range needed for Open-Meteo daily weather retrieval."""
    dates = pd.to_datetime(panel["Date"], errors="coerce").dropna()
    if dates.empty:
        raise ValueError("No valid dates found in the input panel.")
    return dates.min().strftime("%Y-%m-%d"), dates.max().strftime("%Y-%m-%d")


def fetch_open_meteo_era5_daily(city: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Fetch daily ERA5-derived climate controls from Open-Meteo."""
    if city not in CITY_COORDINATES:
        raise ValueError(f"Unsupported city for Open-Meteo request: {city}")

    latitude, longitude = CITY_COORDINATES[city]
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date,
        "end_date": end_date,
        "daily": "temperature_2m_mean,precipitation_sum,wind_speed_10m_mean",
        "models": "era5",
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
        "timezone": "Asia/Shanghai",
    }
    response = requests.get(OPEN_METEO_ARCHIVE_URL, params=params, timeout=60)
    response.raise_for_status()
    daily = response.json()["daily"]

    climate = pd.DataFrame(
        {
            "Location": city,
            "Date": pd.to_datetime(daily["time"], errors="coerce"),
            "DailyMeanTemperature": daily["temperature_2m_mean"],
            "DailyPrecipitation": daily["precipitation_sum"],
            "DailyMeanWindSpeed": daily["wind_speed_10m_mean"],
        }
    )
    return climate


def load_or_fetch_open_meteo_era5_daily(panel: pd.DataFrame, cache_file: Path) -> pd.DataFrame:
    """Load cached daily controls or fetch them from Open-Meteo."""
    if cache_file.exists():
        climate = pd.read_csv(cache_file, encoding="utf-8-sig")
        climate["Date"] = pd.to_datetime(climate["Date"], errors="coerce")
        return climate

    start_date, end_date = get_panel_date_range(panel)
    cities = sorted(city for city in panel["Location"].dropna().astype(str).unique() if city in CITY_COORDINATES)
    if not cities:
        raise ValueError("No supported cities found for Open-Meteo climate retrieval.")

    climate = pd.concat(
        [fetch_open_meteo_era5_daily(city, start_date, end_date) for city in cities],
        ignore_index=True,
    )
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    climate.to_csv(cache_file, index=False, encoding="utf-8-sig")
    return climate


def merge_daily_climate(panel: pd.DataFrame, climate: pd.DataFrame) -> pd.DataFrame:
    """Append Open-Meteo daily climate controls to the worker-day panel."""
    climate = climate.copy()
    climate["Location"] = climate["Location"].astype(str).str.strip()
    climate["Date"] = pd.to_datetime(climate["Date"], errors="coerce")
    panel = panel.drop(
        columns=["DailyMeanTemperature", "DailyPrecipitation", "DailyMeanWindSpeed"],
        errors="ignore",
    )
    return panel.merge(
        climate[["Location", "Date", "DailyMeanTemperature", "DailyPrecipitation", "DailyMeanWindSpeed"]],
        on=["Location", "Date"],
        how="left",
    )


def normalize_input_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """Clean field types and add time-policy indicators."""
    required_columns = {
        "worker_id",
        "Date",
        "Location",
        "WorkerClass",
        "WorkerClass_8",
        "WorkerClass_10",
        "WorkerClass_12",
    }
    missing_columns = required_columns - set(panel.columns)
    if missing_columns:
        raise KeyError(f"{INPUT_PANEL} missing required columns: {sorted(missing_columns)}")

    panel = panel.copy()
    panel["worker_id"] = panel["worker_id"].astype(str).str.strip()
    panel["Location"] = panel["Location"].astype(str).str.strip()
    panel["Date"] = pd.to_datetime(panel["Date"], errors="coerce")
    panel = panel.dropna(subset=["worker_id", "Date", "Location"])

    vacation_dates = build_vacation_dates()
    panel["week"] = panel["Date"].dt.weekday.ge(5).astype(int)
    panel["isvac"] = panel["Date"].dt.date.apply(lambda value: int(value in vacation_dates))
    panel["ali"] = panel["Date"].ge(ALI_DATE).astype(int)

    numeric_columns = [
        "OrderCount",
        "Workload",
        "On-dutyHour",
        "ExposureHour",
        "CoreTempRise",
        "CoreTempDrop",
        "Ta_max",
        "Ta_min",
        "DailyMeanTemperature",
        "DailyPrecipitation",
        "DailyMeanWindSpeed",
    ]
    for column in numeric_columns:
        if column in panel.columns:
            panel[column] = pd.to_numeric(panel[column], errors="coerce")

    return panel.groupby("worker_id").filter(lambda frame: len(frame) > MIN_WORKER_DAYS)


def build_did_panel(panel: pd.DataFrame, climate_cache_file: Path) -> pd.DataFrame:
    """Map the anonymized worker-day panel into the DiD variable schema."""
    panel = normalize_input_panel(panel)
    climate = load_or_fetch_open_meteo_era5_daily(panel, climate_cache_file)
    panel = merge_daily_climate(panel, climate)
    panel = normalize_input_panel(panel)
    did = pd.DataFrame(index=panel.index)

    did["order"] = panel["OrderCount"]
    did["alpha"] = panel["worker_id"]
    did["gamma"] = panel["Date"]
    did["month"] = (panel["Date"].dt.year - 1960) * 12 + panel["Date"].dt.month
    did["date"] = panel["Date"]

    did["y11"] = panel["Workload"]
    did["y12"] = np.select(
        [
            panel["Location"].eq("Shanghai") & panel["Workload"].gt(50),
            panel["Location"].eq("Harbin") & panel["Workload"].gt(40),
        ],
        [1, 1],
        default=0,
    ) * 100

    did["y21"] = panel["CoreTempRise"].fillna(0.0)
    did["y22"] = did["y21"].apply(binary_above, threshold=1.5) * 100
    did["y23"] = did["y21"].apply(binary_above, threshold=3.5) * 100
    did["y24"] = did["y21"].apply(binary_above, threshold=5.0) * 100

    did["y31"] = panel["CoreTempDrop"].fillna(0.0)
    did["y32"] = did["y31"].apply(binary_above, threshold=0.0) * 100
    did["y33"] = did["y31"].apply(binary_above, threshold=2.0) * 100
    did["y34"] = did["y31"].apply(binary_above, threshold=5.0) * 100

    did["td"] = panel["On-dutyHour"]
    did["ord"] = panel["OrderCount"]

    grade = panel["WorkerClass"].apply(class_to_binary).astype(int)
    did["Grade"] = grade
    did["Climate"] = (panel["Ta_max"].gt(35) | panel["Ta_min"].lt(-15)).astype(int)
    
    did["Xcli1"] = panel["DailyMeanTemperature"]
    did["Xcli2"] = panel["DailyPrecipitation"]
    did["Xcli3"] = panel["DailyMeanWindSpeed"]
    did["Xdq1"] = panel["Location"].eq("Shanghai").astype(int)
    did["Xtime1"] = panel["week"]
    did["Xtime2"] = panel["isvac"]
    did["Xtime3"] = panel["ali"]
    did["Xmeanload"] = did.groupby(["gamma", "Xdq1"])["y11"].transform("mean")
    
    did["Grade_8"] = panel["WorkerClass_8"].apply(class_to_binary).astype(int)
    did["Grade_10"] = panel["WorkerClass_10"].apply(class_to_binary).astype(int)
    did["Grade_12"] = panel["WorkerClass_12"].apply(class_to_binary).astype(int)
    
    did["Climate_l"] = (panel["Ta_max"].gt(33) | panel["Ta_min"].lt(-13)).astype(int)
    did["Climate_h"] = (panel["Ta_max"].gt(37) | panel["Ta_min"].lt(-17)).astype(int)
    did["Climate_fake"] = (panel["Ta_max"].gt(10) & panel["Ta_max"].le(15)).astype(int)
    
    return did.reset_index(drop=True)


def run(
    input_panel: Path,
    output_dta: Path,
    output_csv: Path,
    climate_cache_file: Path,
    write_csv: bool,
) -> pd.DataFrame:
    """Read the anonymized panel, build DiD variables, and save outputs."""
    panel = pd.read_csv(input_panel, encoding="utf-8-sig")
    did = build_did_panel(panel, climate_cache_file)

    output_dta.parent.mkdir(parents=True, exist_ok=True)
    did.to_stata(output_dta, write_index=False, version=118)
    if write_csv:
        output_csv.parent.mkdir(parents=True, exist_ok=True)
        did.to_csv(output_csv, index=False, encoding="utf-8-sig")
    return did


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a DiD-ready panel from worker_day_panel.csv.")
    parser.add_argument("--input-panel", type=Path, default=INPUT_PANEL)
    parser.add_argument("--output-dta", type=Path, default=OUTPUT_DTA)
    parser.add_argument("--output-csv", type=Path, default=OUTPUT_CSV)
    parser.add_argument("--climate-cache-file", type=Path, default=CLIMATE_CACHE_FILE)
    parser.add_argument("--write-csv", action="store_true", help="Also write a CSV copy of the DiD panel.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    did = run(
        input_panel=args.input_panel,
        output_dta=args.output_dta,
        output_csv=args.output_csv,
        climate_cache_file=args.climate_cache_file,
        write_csv=args.write_csv,
    )
    print(f"Output rows: {len(did)}")
    print(f"Saved Stata panel to: {args.output_dta}")
    if args.write_csv:
        print(f"Saved CSV panel to: {args.output_csv}")


if __name__ == "__main__":
    main()

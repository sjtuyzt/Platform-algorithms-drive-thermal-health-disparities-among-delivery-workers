"""Build hourly and daily weather files, then merge daily temperature into worker-day panel data."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

import Utils.climateProcess as cp


OUTPUT_ROOT = Path("PanelResults")
PANEL_FILE = OUTPUT_ROOT / "worker_day_panel.csv"
HOURLY_WEATHER_FILE = OUTPUT_ROOT / "hourly_weather_both_cities.csv"

DEFAULT_CITIES = ("Shanghai", "Harbin")
DEFAULT_START_DATE = "2024-10-31"
DEFAULT_END_DATE = "2025-11-01"
T_RISE = 0


def get_panel_date_range(panel: pd.DataFrame) -> tuple[str, str]:
    if "Date" not in panel.columns:
        return DEFAULT_START_DATE, DEFAULT_END_DATE

    dates = pd.to_datetime(panel["Date"], errors="coerce").dropna()
    if dates.empty:
        return DEFAULT_START_DATE, DEFAULT_END_DATE

    return dates.min().strftime("%Y-%m-%d"), dates.max().strftime("%Y-%m-%d")


def build_hourly_weather(city: str, start_date: str, end_date: str, t_rise: float = 0) -> pd.DataFrame:
    weather = cp.get_climate_data(
        Location=city,
        Start_date=start_date,
        End_date=end_date,
        T_rise=t_rise,
    )
    weather = weather.copy()
    weather["Location"] = city
    weather["Date"] = pd.to_datetime(weather["timestamp"]).dt.strftime("%Y-%m-%d")
    return weather


def build_daily_weather(hourly_weather: pd.DataFrame) -> pd.DataFrame:
    daily_weather = (
        hourly_weather.groupby(["Location", "Date"], as_index=False)
        .agg(
            Ta_max=("Ta", "max"),
            Ta_min=("Ta", "min"),
        )
    )
    return daily_weather


def merge_weather_to_panel(panel: pd.DataFrame, daily_weather: pd.DataFrame) -> pd.DataFrame:
    panel = panel.copy()
    panel["Date"] = pd.to_datetime(panel["Date"], errors="coerce").dt.strftime("%Y-%m-%d")
    daily_weather = daily_weather.copy()
    daily_weather["Date"] = pd.to_datetime(daily_weather["Date"], errors="coerce").dt.strftime("%Y-%m-%d")

    panel = panel.drop(columns=["Ta_max", "Ta_min"], errors="ignore")
    return panel.merge(daily_weather[["Location", "Date", "Ta_max", "Ta_min"]], on=["Location", "Date"], how="left")


def main() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    panel = pd.read_csv(PANEL_FILE)
    start_date, end_date = get_panel_date_range(panel)

    hourly_weather = pd.concat(
        [build_hourly_weather(city, start_date, end_date, T_RISE) for city in DEFAULT_CITIES],
        ignore_index=True,
    )
    daily_weather = build_daily_weather(hourly_weather)
    panel_with_weather = merge_weather_to_panel(panel, daily_weather)

    hourly_weather.to_csv(HOURLY_WEATHER_FILE, index=False, encoding="utf-8-sig")
    panel_with_weather.to_csv(PANEL_FILE, index=False, encoding="utf-8-sig")



if __name__ == "__main__":
    main()

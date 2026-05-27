"""Preprocess worker order records into worker-day panel data.

This script consolidates the workflow from the three preprocessing notebooks:

1. Split monthly order files into one Excel file per worker.
2. Build worker-day-batch JSON records.
3. Export worker-day panel data and worker classifications for Shanghai and Harbin.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler


DEFAULT_CITIES = ("Shanghai", "Harbin")
DEFAULT_MONTHS = (
    "202411",
    "202412",
    "202501",
    "202502",
    "202503",
    "202504",
    "202505",
    "202506",
    "202507",
    "202508",
    "202509",
    "202510",
)

ORDER_COLUMNS = (
    "rider_name",
    "rider_accept_time",
    "rider_pickup_time",
    "rider_delivered_time",
    "weather_level",
    "weather",
    "rider_assessment_time",
)

PERFORMANCE_COLUMN_ALIASES = {
    "worker_name": ("worker_name", "rider_name"),
    "accept_time": ("rider_accept_time", "order_accept_time"),
    "platform_overtime": (
        "platform_overtime",
        "exceed_platform_expect_time",
        "is_exceed_platform_expect_time",
        "platform_expect_overtime",
    ),
    "worker_overtime": (
        "worker_overtime",
        "exceed_rider_t",
        "is_exceed_rider_t",
        "rider_t_overtime",
    ),
    "delivery_duration": ("delivery_duration",),
    "pickup_violation": (
        "pickup_violation",
        "pickup_violation_confirmed",
        "violation_pickup_confirmed",
        "is_pickup_violation_confirmed",
    ),
    "delivery_violation": (
        "delivery_violation",
        "delivery_violation_confirmed",
        "violation_delivery_confirmed",
        "is_delivery_violation_confirmed",
    ),
    "claim": ("claim", "claim_confirmed", "claim_conf", "is_claim_confirmed"),
    "false_report": (
        "false_report",
        "false_report_item",
        "false_mark_confirmed",
        "false_mark_conf",
        "is_false_report_confirmed",
    ),
}

STEPA_COLUMN_POSITIONS = {
    "worker_name": 0,
    "accept_time": 1,
    "platform_overtime": 2,
    "worker_overtime": 3,
    "delivery_duration": 4,
    "pickup_violation": 6,
    "delivery_violation": 7,
    "claim": 8,
    "false_report": 10,
}

WEATHER_LEVEL_MAPPING = {
    "normal": 1,
    "slightly_adverse": 2,
    "adverse": 3,
    "extreme_adverse": 4,
    "rare_extreme_adverse": 5,
}

YES_VALUES = {"1", "yes", "y", "true"}


def normalize_weather_level(value: Any) -> float:
    if pd.isna(value):
        return 1.0
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)
    key = str(value).strip()
    if key in WEATHER_LEVEL_MAPPING:
        return float(WEATHER_LEVEL_MAPPING[key])
    try:
        return float(key)
    except ValueError as exc:
        raise ValueError(f"Unknown weather_level value: {value!r}") from exc


def normalize_weather_description(value: Any) -> int:
    weather = "" if pd.isna(value) else str(value).lower()
    if "extreme cold" in weather or "extreme heat" in weather:
        return 4
    if "cold" in weather or "heat" in weather:
        return 2
    return 1


def datetime_to_str(value: Any) -> str:
    if pd.isna(value):
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return ""


def safe_filename(value: str) -> str:
    return re.sub(r'[<>:"/\\|?*]+', "_", str(value)).strip() or "unknown_worker"


def parse_assessment_time(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series.astype(str).str.split("~").str[-1], errors="coerce")


class Order:
    def __init__(
        self,
        worker_pickup_time: pd.Timestamp,
        order_accept_time: pd.Timestamp,
        delivery_time: pd.Timestamp,
        expected_time: pd.Timestamp,
        weather_level: Any,
    ) -> None:
        self.order_accept_time = order_accept_time
        self.worker_pickup_time = worker_pickup_time
        self.delivery_time = delivery_time
        self.expected_time = expected_time
        self.expected_duration = self.calculate_expected_duration()
        self.weather_level = normalize_weather_level(weather_level)

    def calculate_expected_duration(self) -> float:
        return (self.expected_time - self.order_accept_time).total_seconds() / 3600

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_accept_time": datetime_to_str(self.order_accept_time),
            "worker_pickup_time": datetime_to_str(self.worker_pickup_time),
            "delivered_time": datetime_to_str(self.delivery_time),
            "delivery_difficulty": self.weather_level,
            "platform_expected_duration": round(self.expected_duration, 2),
        }


class Batch:
    def __init__(self, batch_name: str) -> None:
        self.batch_name = batch_name
        self.orders: list[Order] = []
        self.start_time: pd.Timestamp | None = None
        self.end_time: pd.Timestamp | None = None
        self.exposure_duration = 0.0
        self.avg_weather_level = 0.0
        self.duration_hours = 0.0
        self.batch_period: str | None = None
        self.order_count = 0
        self.latest_worker_pickup_time: pd.Timestamp | None = None

    def add_order(self, order: Order) -> None:
        self.orders.append(order)
        if self.start_time is None or order.order_accept_time < self.start_time:
            self.start_time = order.order_accept_time
        if self.end_time is None or order.delivery_time > self.end_time:
            self.end_time = order.delivery_time
        if (
            self.latest_worker_pickup_time is None
            or order.worker_pickup_time > self.latest_worker_pickup_time
        ):
            self.latest_worker_pickup_time = order.worker_pickup_time

        self.order_count = len(self.orders)
        self.calculate_exposure_duration()
        self.calculate_avg_weather()
        self.calculate_duration()
        self.update_batch_period()

    def calculate_exposure_duration(self) -> None:
        if self.latest_worker_pickup_time is not None and self.end_time is not None:
            self.exposure_duration = (
                self.end_time - self.latest_worker_pickup_time
            ).total_seconds() / 3600

    def calculate_avg_weather(self) -> None:
        if not self.orders:
            self.avg_weather_level = 0.0
            return
        self.avg_weather_level = float(np.mean([o.weather_level for o in self.orders]))

    def calculate_duration(self) -> None:
        if self.start_time is not None and self.end_time is not None:
            self.duration_hours = (self.end_time - self.start_time).total_seconds() / 3600

    def update_batch_period(self) -> None:
        if self.start_time is None:
            self.batch_period = None
            return

        hour = self.start_time.hour
        minute = self.start_time.minute
        if (hour == 10 and minute >= 30) or (10 < hour < 13):
            self.batch_period = "lunch_peak"
        elif (hour == 13 and minute < 30) or (13 < hour < 16) or (hour == 16 and minute < 30):
            self.batch_period = "afternoon_tea"
        elif (hour == 16 and minute >= 30) or (16 < hour < 19):
            self.batch_period = "dinner_peak"
        elif (hour == 19 and minute < 30) or (19 <= hour <= 23):
            self.batch_period = "late_night"
        else:
            self.batch_period = "other_period"

    def to_dict(self) -> dict[str, Any]:
        return {
            "batch_period": self.batch_period,
            "batch_order_count": self.order_count,
            "batch_duration_minutes": round(self.duration_hours * 60, 2),
            "batch_exposure_minutes": round(self.exposure_duration * 60, 2),
            "batch_order_efficiency_min_per_order": (
                round(self.duration_hours * 60 / len(self.orders), 2) if self.orders else 0
            ),
            "batch_start_time": datetime_to_str(self.start_time),
            "batch_end_time": datetime_to_str(self.end_time),
            "avg_delivery_difficulty": self.avg_weather_level,
            "order_details": [order.to_dict() for order in self.orders],
        }


class WorkerDay:
    def __init__(self, date: Any) -> None:
        self.date = date
        self.duration = 0.0
        self.batches: dict[str, Batch] = {}
        self.daily_exposure_duration = 0.0
        self.daily_order_volume = 0

    def add_order(self, order: Order) -> None:
        for batch in self.batches.values():
            time_diff = order.order_accept_time - batch.end_time if batch.end_time is not None else timedelta()
            if time_diff <= timedelta(minutes=10):
                batch.add_order(order)
                return

        batch_name = f"batch_{len(self.batches) + 1}"
        self.batches[batch_name] = Batch(batch_name)
        self.batches[batch_name].add_order(order)

    def finalize(self) -> None:
        self.duration = sum(batch.duration_hours for batch in self.batches.values())
        self.daily_exposure_duration = sum(batch.exposure_duration for batch in self.batches.values())
        self.daily_order_volume = sum(batch.order_count for batch in self.batches.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date.strftime("%Y-%m-%d"),
            "daily_on_duty_hours": round(self.duration, 2),
            "daily_total_exposure_hours": round(self.daily_exposure_duration, 2),
            "daily_batch_count": len(self.batches),
            "daily_order_count": self.daily_order_volume,
            "daily_batch_details": [batch.to_dict() for batch in self.batches.values()],
        }


class WorkerOrderTree:
    def __init__(self, worker_name: str) -> None:
        self.worker_name = worker_name
        self.days: dict[Any, WorkerDay] = {}

    def add_order_data(self, data: pd.DataFrame) -> None:
        data = data.copy()
        for column in ("rider_accept_time", "rider_pickup_time", "rider_delivered_time"):
            data[column] = pd.to_datetime(data[column], errors="coerce")
        data = data.sort_values("rider_accept_time")

        for date in data["rider_accept_time"].dt.date.dropna().unique():
            daily_data = data[data["rider_accept_time"].dt.date == date]
            self.days.setdefault(date, WorkerDay(date))
            for _, row in daily_data.iterrows():
                if pd.isna(row["rider_delivered_time"]) or pd.isna(row["rider_pickup_time"]):
                    continue
                order = Order(
                    order_accept_time=row["rider_accept_time"],
                    worker_pickup_time=row["rider_pickup_time"],
                    delivery_time=row["rider_delivered_time"],
                    expected_time=row["rider_assessment_time"],
                    weather_level=row["weather_level"],
                )
                self.days[date].add_order(order)

        for day in self.days.values():
            day.finalize()

    def calculate_worker_stats(self) -> dict[str, float]:
        if not self.days:
            return {
                "attendance_rate_percent": 0.0,
                "active_days": 0,
                "service_capacity": 0,
                "avg_daily_orders": 0.0,
                "avg_daily_on_duty_hours": 0.0,
                "avg_daily_exposure_hours": 0.0,
            }

        dates = list(self.days)
        active_days = len(dates)
        total_days = (max(dates) - min(dates)).days + 1
        total_orders = sum(day.daily_order_volume for day in self.days.values())
        total_on_duty_hours = sum(day.duration for day in self.days.values())
        total_exposure_hours = sum(day.daily_exposure_duration for day in self.days.values())

        return {
            "attendance_rate_percent": round(active_days / total_days * 100, 2) if total_days else 0.0,
            "active_days": active_days,
            "service_capacity": total_orders,
            "avg_daily_orders": round(total_orders / active_days, 2),
            "avg_daily_on_duty_hours": round(total_on_duty_hours / active_days, 2),
            "avg_daily_exposure_hours": round(total_exposure_hours / active_days, 2),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "worker_name": self.worker_name,
            **self.calculate_worker_stats(),
            "date_order_details": {
                date.strftime("%Y-%m-%d"): day.to_dict()
                for date, day in self.days.items()
                if date is not None
            },
        }


class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (datetime, pd.Timestamp)):
            return obj.strftime("%Y-%m-%d %H:%M:%S")
        return super().default(obj)


def find_column(df: pd.DataFrame, aliases: tuple[str, ...]) -> str | None:
    normalized_columns = {str(column).strip(): column for column in df.columns}
    for alias in aliases:
        if alias in normalized_columns:
            return normalized_columns[alias]
    return None


def find_performance_columns(df: pd.DataFrame) -> dict[str, Any]:
    column_map = {
        key: find_column(df, aliases)
        for key, aliases in PERFORMANCE_COLUMN_ALIASES.items()
    }
    if column_map["worker_name"] is not None and column_map["accept_time"] is not None:
        return column_map

    columns = list(df.columns)
    for key, index in STEPA_COLUMN_POSITIONS.items():
        if column_map.get(key) is None and index < len(columns):
            column_map[key] = columns[index]
    return column_map


def to_binary(value: Any) -> int:
    if pd.isna(value):
        return 0
    if isinstance(value, (int, float, np.integer, np.floating)):
        return int(value == 1)
    value_str = str(value).strip().lower()
    return int(value_str in YES_VALUES)


def duration_to_seconds(value: Any) -> float:
    if pd.isna(value) or value == "":
        return math.nan
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)

    parts = str(value).strip().split(":")
    try:
        if len(parts) == 3:
            hours, minutes, seconds = map(float, parts)
            return hours * 3600 + minutes * 60 + seconds
        if len(parts) == 2:
            minutes, seconds = map(float, parts)
            return minutes * 60 + seconds
    except ValueError:
        return math.nan
    return math.nan


def build_worker_detail_files(city_dir: Path, months: tuple[str, ...]) -> Path:
    details_dir = city_dir / "Details"
    details_dir.mkdir(parents=True, exist_ok=True)
    frames: list[pd.DataFrame] = []

    for month in months:
        input_file = city_dir / month / "Orders.xlsx"
        if not input_file.exists():
            print(f"WARNING: missing input file, skipped: {input_file}")
            continue
        df = pd.read_excel(input_file)
        missing_columns = [column for column in ORDER_COLUMNS if column not in df.columns]
        if missing_columns:
            raise KeyError(f"{input_file} is missing columns: {missing_columns}")

        df_tmp = df.loc[:, ORDER_COLUMNS].copy()
        df_tmp["rider_assessment_time"] = parse_assessment_time(df_tmp["rider_assessment_time"])
        df_tmp["weather_level"] = df_tmp["weather_level"].apply(normalize_weather_level)
        df_tmp["weather"] = df_tmp["weather"].apply(normalize_weather_description)
        frames.append(df_tmp)

    if not frames:
        raise FileNotFoundError(f"No monthly Orders.xlsx files were found under {city_dir}")

    all_orders = pd.concat(frames, ignore_index=True)
    all_orders = all_orders.dropna(subset=["rider_name", "rider_accept_time"])

    def save_worker_data(item: tuple[str, pd.DataFrame]) -> None:
        worker_name, group = item
        output_file = details_dir / f"{safe_filename(worker_name)}.xlsx"
        group.sort_values("rider_accept_time").to_excel(output_file, index=False)

    with ThreadPoolExecutor() as executor:
        list(executor.map(save_worker_data, list(all_orders.groupby("rider_name", dropna=True))))

    return details_dir


def build_order_json(details_dir: Path, output_file: Path) -> Path:
    worker_trees: dict[str, WorkerOrderTree] = {}
    output_file.parent.mkdir(parents=True, exist_ok=True)

    for file_path in sorted(details_dir.glob("*.xlsx")):
        df_rider = pd.read_excel(file_path)
        for column in (
            "rider_accept_time",
            "rider_pickup_time",
            "rider_delivered_time",
            "rider_assessment_time",
        ):
            df_rider[column] = pd.to_datetime(df_rider[column], errors="coerce")
        df_rider["weather_level"] = df_rider["weather_level"].apply(normalize_weather_level)
        df_rider = df_rider.dropna(
            subset=["rider_accept_time", "rider_delivered_time", "rider_assessment_time"]
        )

        worker_name = file_path.stem
        worker_trees.setdefault(worker_name, WorkerOrderTree(worker_name))
        worker_trees[worker_name].add_order_data(df_rider)

    with output_file.open("w", encoding="utf-8") as file:
        json.dump(
            {name: tree.to_dict() for name, tree in worker_trees.items()},
            file,
            indent=4,
            ensure_ascii=False,
            cls=CustomJSONEncoder,
        )
    return output_file


def build_worker_day_performance(city_dir: Path, months: tuple[str, ...]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    required_keys = ("worker_name", "accept_time")

    for month in months:
        input_file = city_dir / month / "Orders.xlsx"
        if not input_file.exists():
            continue
        df = pd.read_excel(input_file)
        column_map = find_performance_columns(df)
        if any(column_map[key] is None for key in required_keys):
            continue

        performance = pd.DataFrame(
            {
                "worker_id": df[column_map["worker_name"]],
                "date": pd.to_datetime(df[column_map["accept_time"]], errors="coerce").dt.strftime("%Y-%m-%d"),
            }
        )

        optional_columns = {
            "platform_overtime": "PlatformOvertimeRate",
            "worker_overtime": "WorkerOvertimeRate",
            "pickup_violation": "PickupViolationRate",
            "delivery_violation": "DeliveryViolationRate",
            "claim": "ClaimRate",
            "false_report": "FalseReportRate",
        }
        for source_key, output_column in optional_columns.items():
            source_column = column_map.get(source_key)
            if source_column is not None:
                performance[output_column] = df[source_column].apply(to_binary)

        duration_column = column_map.get("delivery_duration")
        if duration_column is not None:
            performance["DeliveryDurationSecond"] = df[duration_column].apply(duration_to_seconds)

        frames.append(performance.dropna(subset=["worker_id", "date"]))

    if not frames:
        return pd.DataFrame(columns=["worker_id", "date"])

    performance_all = pd.concat(frames, ignore_index=True)
    value_columns = [column for column in performance_all.columns if column not in {"worker_id", "date"}]
    return performance_all.groupby(["worker_id", "date"], as_index=False)[value_columns].mean()


def load_worker_day_orders(json_file: Path, city: str) -> pd.DataFrame:
    with json_file.open("r", encoding="utf-8") as file:
        data = json.load(file)

    records: list[dict[str, Any]] = []
    for worker_name, worker_stats in data.items():
        for date_str, date_info in worker_stats.get("date_order_details", {}).items():
            batch_details = date_info.get("daily_batch_details", [])
            order_details = [order for batch in batch_details for order in batch.get("order_details", [])]
            on_duty_hours = date_info.get("daily_on_duty_hours", np.nan)
            workload = sum(order.get("platform_expected_duration", 0) for order in order_details)
            delivery_difficulties = [
                order.get("delivery_difficulty", np.nan)
                for order in order_details
                if not pd.isna(order.get("delivery_difficulty", np.nan))
            ]

            batch_start_times, batch_end_times = parse_batch_times(batch_details)
            total_period = calculate_total_period(batch_start_times, batch_end_times)
            rest_count = calculate_rest_count(batch_start_times, batch_end_times)
            rest_hours = total_period - on_duty_hours if not pd.isna(total_period) else np.nan
            rest_ratio = rest_hours / total_period if total_period and total_period > 0 else np.nan

            records.append(
                {
                    "worker_id": worker_name,
                    "Date": date_str,
                    "OrderCount": date_info.get("daily_order_count", 0),
                    "Difficulty": float(np.mean(delivery_difficulties)) if delivery_difficulties else np.nan,
                    "ExposureHour": date_info.get("daily_total_exposure_hours", np.nan),
                    "On-dutyHour": on_duty_hours,
                    "Workload": workload,
                    "WorkIntensity": round(workload / on_duty_hours, 2)
                    if on_duty_hours
                    else np.nan,
                    "RestCount": rest_count,
                    "RestHour": rest_hours,
                    "RestRatio": rest_ratio,
                    "Location": city,
                    "AdverseWeatherRate": calculate_adverse_weather_rate(delivery_difficulties),
                    "AverageDeliveryDurationSecond": calculate_avg_duration(order_details),
                }
            )
    return pd.DataFrame(records)


def parse_batch_times(batch_details: list[dict[str, Any]]) -> tuple[list[datetime], list[datetime]]:
    start_times: list[datetime] = []
    end_times: list[datetime] = []
    for batch in batch_details:
        start = parse_datetime(batch.get("batch_start_time"))
        end = parse_datetime(batch.get("batch_end_time"))
        if start is not None and end is not None:
            start_times.append(start)
            end_times.append(end)
    return start_times, end_times


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def calculate_total_period(start_times: list[datetime], end_times: list[datetime]) -> float:
    if not start_times or not end_times:
        return math.nan
    return (max(end_times) - min(start_times)).total_seconds() / 3600


def calculate_rest_count(start_times: list[datetime], end_times: list[datetime]) -> int:
    rest_count = 0
    for index in range(1, min(len(start_times), len(end_times))):
        interval_hours = (start_times[index] - end_times[index - 1]).total_seconds() / 3600
        if interval_hours > 0.25:
            rest_count += 1
    return rest_count


def calculate_adverse_weather_rate(delivery_difficulties: list[float]) -> float:
    if not delivery_difficulties:
        return math.nan
    return sum(value > 1 for value in delivery_difficulties) / len(delivery_difficulties)


def calculate_avg_duration(order_details: list[dict[str, Any]]) -> float:
    durations: list[float] = []
    for order in order_details:
        start = parse_datetime(order.get("order_accept_time"))
        end = parse_datetime(order.get("delivered_time"))
        if start is not None and end is not None:
            durations.append((end - start).total_seconds())
    return float(np.mean(durations)) if durations else math.nan


def classify_workers(json_file: Path, city: str) -> pd.DataFrame:
    with json_file.open("r", encoding="utf-8") as file:
        data = json.load(file)

    worker_data = [
        {
            "worker_id": name,
            "active_days": stats.get("active_days", 0),
            "service_capacity": stats.get("service_capacity", 0),
            "avg_daily_orders": stats.get("avg_daily_orders", 0),
            "Location": city,
        }
        for name, stats in data.items()
    ]
    df = pd.DataFrame(worker_data)
    if df.empty:
        return pd.DataFrame(columns=["worker_id", "WorkerClass", "Location", "CompositeScore"])

    features = ["active_days", "service_capacity", "avg_daily_orders"]
    if len(df) == 1:
        df["CompositeScore"] = 0.0
        df["WorkerClass"] = "Regular"
    else:
        scaled_features = StandardScaler().fit_transform(df[features])
        scores = np.dot(scaled_features, np.array([0.25, 0.25, 0.5]))
        threshold = np.percentile(scores, 91)
        df["CompositeScore"] = scores
        df["WorkerClass"] = np.where(scores > threshold, "Elite", "Regular")

    if "CompositeScore" not in df.columns:
        df["CompositeScore"] = 0.0
    if "WorkerClass" not in df.columns:
        df["WorkerClass"] = "Regular"
    return df[["worker_id", "WorkerClass", "Location", "CompositeScore"]]


def process_city(
    input_root: Path,
    output_root: Path,
    city: str,
    months: tuple[str, ...],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    print(f"Processing city: {city}")
    city_dir = input_root / city
    details_dir = build_worker_detail_files(city_dir, months)
    json_file = build_order_json(details_dir, city_dir / "Json_data" / "order_data.json")
    worker_day_panel = load_worker_day_orders(json_file, city)
    performance = build_worker_day_performance(city_dir, months)
    if not performance.empty:
        worker_day_panel = worker_day_panel.merge(
            performance,
            left_on=["worker_id", "Date"],
            right_on=["worker_id", "date"],
            how="left",
        ).drop(columns=["date"], errors="ignore")
    worker_class = classify_workers(json_file, city)

    classification_dir = city_dir / "Worker Classification"
    classification_dir.mkdir(parents=True, exist_ok=True)
    worker_class.to_csv(
        classification_dir / f"worker_class_{city}_12.csv",
        index=False,
        encoding="utf-8-sig",
    )

    city_output_dir = output_root / city
    city_output_dir.mkdir(parents=True, exist_ok=True)
    worker_day_panel.to_csv(
        city_output_dir / f"worker_day_panel_{city}.csv",
        index=False,
        encoding="utf-8-sig",
    )
    return worker_day_panel, worker_class


def run_pipeline(
    input_root: Path,
    output_root: Path,
    cities: tuple[str, ...],
    months: tuple[str, ...],
) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    worker_day_panels: list[pd.DataFrame] = []
    worker_classes: list[pd.DataFrame] = []

    for city in cities:
        worker_day_panel, worker_class = process_city(input_root, output_root, city, months)
        worker_day_panels.append(worker_day_panel)
        worker_classes.append(worker_class)

    all_worker_days = (
        pd.concat(worker_day_panels, ignore_index=True) if worker_day_panels else pd.DataFrame()
    )
    all_classes = pd.concat(worker_classes, ignore_index=True) if worker_classes else pd.DataFrame()
    all_worker_days_with_class = all_worker_days.merge(
        all_classes[["worker_id", "WorkerClass", "Location"]],
        on=["worker_id", "Location"],
        how="left",
    )

    all_worker_days.to_csv(output_root / "worker_day_panel_all_cities.csv", index=False, encoding="utf-8-sig")
    all_classes.to_csv(output_root / "worker_class_all_cities.csv", index=False, encoding="utf-8-sig")
    all_worker_days_with_class.to_csv(
        output_root / "worker_day_panel_with_class_all_cities.csv",
        index=False,
        encoding="utf-8-sig",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build worker-day panel data for Shanghai and Harbin.")
    parser.add_argument("--input-root", default="INPUT", type=Path)
    parser.add_argument("--output-root", default="PanelResults", type=Path)
    parser.add_argument("--cities", nargs="+", default=list(DEFAULT_CITIES))
    parser.add_argument("--months", nargs="+", default=list(DEFAULT_MONTHS))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_pipeline(
        input_root=args.input_root,
        output_root=args.output_root,
        cities=tuple(args.cities),
        months=tuple(args.months),
    )


if __name__ == "__main__":
    main()

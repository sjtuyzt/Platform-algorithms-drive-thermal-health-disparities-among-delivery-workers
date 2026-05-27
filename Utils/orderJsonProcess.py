import json
import os
from datetime import datetime, timedelta

import pandas as pd


def _load_json(json_file_path):
    with open(json_file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_any(record, *keys, default=None):
    for key in keys:
        if isinstance(record, dict) and key in record:
            return record[key]
    return default


def extract_rider_orders(json_file_path):
    """
    Extract daily rider order details from the raw rider JSON tree.

    The returned structure keeps four levels:
    rider -> date -> wave -> order details.
    """
    raw_data = _load_json(json_file_path)
    result = {}

    for rider_name, rider_record in raw_data.items():
        result[rider_name] = {
            "rider_name": rider_name,
            "date_order_details": {},
        }

        date_orders = _get_any(
            rider_record,
            "date_order_details",
            "\u65e5\u671f\u8ba2\u5355\u8be6\u60c5",
            default={},
        )
        for date_str, day_record in date_orders.items():
            day_info = {
                "date": date_str,
                "wave_details": [],
            }

            for wave in _get_any(
                day_record,
                "daily_wave_details",
                "\u5f53\u5929\u6ce2\u6b21\u8be6\u60c5",
                default=[],
            ):
                wave_info = {
                    "wave_start_time": None,
                    "wave_end_time": None,
                    "order_details": [],
                }

                accept_times = []
                delivery_times = []
                orders = _get_any(wave, "order_details", "\u8ba2\u5355\u8be6\u60c5", default=[])
                for order in orders:
                    accept_time = _get_any(order, "order_accept_time", "\u63a5\u5355\u65f6\u95f4")
                    delivery_time = _get_any(order, "delivered_time", "\u9001\u8fbe\u65f6\u95f4")
                    if accept_time is not None:
                        accept_times.append(accept_time)
                    if delivery_time is not None:
                        delivery_times.append(delivery_time)

                if accept_times:
                    wave_info["wave_start_time"] = min(accept_times)
                if delivery_times:
                    wave_info["wave_end_time"] = max(delivery_times)

                for order in orders:
                    order_info = {
                        "order_accept_time": _get_any(order, "order_accept_time", "\u63a5\u5355\u65f6\u95f4"),
                        "delivered_time": _get_any(order, "delivered_time", "\u9001\u8fbe\u65f6\u95f4"),
                        "delivery_difficulty": _get_any(order, "delivery_difficulty", "\u9001\u9910\u96be\u5ea6"),
                    }
                    wave_info["order_details"].append(order_info)

                day_info["wave_details"].append(wave_info)

            result[rider_name]["date_order_details"][date_str] = day_info

    return result


def gennerate_rider_order_df(json_file_path):
    """
    Read processed rider JSON and return one row per rider-date-wave period.
    """
    data = _load_json(json_file_path)
    records = []

    for rider_name, rider_info in data.items():
        date_details = _get_any(
            rider_info,
            "date_order_details",
            "\u65e5\u671f\u8ba2\u5355\u8be6\u60c5",
            default={},
        )
        for _, date_info in date_details.items():
            wave_details = _get_any(date_info, "wave_details", "\u6ce2\u6b21\u8be6\u60c5", default=[])
            for wave in wave_details:
                records.append(
                    {
                        "rider_name": _get_any(rider_info, "rider_name", "\u9a91\u624b\u540d\u79f0", default=rider_name),
                        "date": _get_any(date_info, "date", "\u65e5\u671f"),
                        "wave_start_time": _get_any(wave, "wave_start_time", "\u6ce2\u6b21\u5f00\u59cb\u65f6\u95f4"),
                        "wave_end_time": _get_any(wave, "wave_end_time", "\u6ce2\u6b21\u7ed3\u675f\u65f6\u95f4"),
                    }
                )

    df = pd.DataFrame(records)
    if not df.empty:
        df = df.sort_values(by=["rider_name", "date"]).reset_index(drop=True)
    return df


def gennerate_rider_daily_stat_df(json_file_path):
    """
    Read processed rider JSON and compute daily workload by rider.
    """
    data = _load_json(json_file_path)
    daily_stat = []

    for rider_name, rider_info in data.items():
        date_details = _get_any(
            rider_info,
            "date_order_details",
            "\u65e5\u671f\u8ba2\u5355\u8be6\u60c5",
            default={},
        )
        for date, date_info in date_details.items():
            daily_workload = 0

            wave_details = _get_any(date_info, "wave_details", "\u6ce2\u6b21\u8be6\u60c5", default=[])
            for wave in wave_details:
                start_str = _get_any(wave, "wave_start_time", "\u6ce2\u6b21\u5f00\u59cb\u65f6\u95f4")
                end_str = _get_any(wave, "wave_end_time", "\u6ce2\u6b21\u7ed3\u675f\u65f6\u95f4")
                order_details = _get_any(wave, "order_details", "\u8ba2\u5355\u8be6\u60c5", default=[])
                if not start_str or not end_str or not order_details:
                    continue

                order_count = len(order_details)
                total_difficulty = sum(
                    _get_any(order, "delivery_difficulty", "\u9001\u9910\u96be\u5ea6", default=0)
                    for order in order_details
                )
                avg_difficulty = total_difficulty / order_count if order_count else 0

                try:
                    start = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
                    end = datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S")
                    if end < start:
                        end += timedelta(days=1)
                    delivery_duration = (end - start).total_seconds() / 3600.0
                except ValueError:
                    continue

                daily_workload += avg_difficulty * order_count * delivery_duration

            daily_stat.append(
                {
                    "rider_name": rider_info.get("rider_name"),
                    "date": date,
                    "workload": daily_workload,
                }
            )

    daily_stat_df = pd.DataFrame(daily_stat)
    if not daily_stat_df.empty:
        daily_stat_df = daily_stat_df.sort_values(by=["rider_name", "date"]).reset_index(drop=True)
    return daily_stat_df


def gennerate_rider_hourly_worktime_df(json_file_path):
    """
    Read processed rider JSON and compute hourly working time columns 0..23.
    """
    data = _load_json(json_file_path)
    records = []

    for rider_name, rider_info in data.items():
        date_details = _get_any(
            rider_info,
            "date_order_details",
            "\u65e5\u671f\u8ba2\u5355\u8be6\u60c5",
            default={},
        )
        for date, date_info in date_details.items():
            hourly_work = [0.0] * 24

            wave_details = _get_any(date_info, "wave_details", "\u6ce2\u6b21\u8be6\u60c5", default=[])
            for wave in wave_details:
                start_str = _get_any(wave, "wave_start_time", "\u6ce2\u6b21\u5f00\u59cb\u65f6\u95f4")
                end_str = _get_any(wave, "wave_end_time", "\u6ce2\u6b21\u7ed3\u675f\u65f6\u95f4")
                if not start_str or not end_str:
                    continue

                start = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
                end = datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S")
                if end < start:
                    end += timedelta(days=1)

                current = start
                while current < end:
                    hour = current.hour
                    next_hour = current.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
                    segment_end = min(end, next_hour)
                    hourly_work[hour] += (segment_end - current).total_seconds() / 3600.0
                    current = segment_end

            record = {
                "rider_name": _get_any(rider_info, "rider_name", "\u9a91\u624b\u540d\u79f0", default=rider_name),
                "date": date,
            }
            for h in range(24):
                record[h] = round(hourly_work[h], 2)
            records.append(record)

    df = pd.DataFrame(records)
    if not df.empty:
        df = df.sort_values(by=["rider_name", "date"]).reset_index(drop=True)
    return df


def generate_rider_order_df(json_file_path):
    """Backward-compatible alias for the correctly spelled function name."""
    return gennerate_rider_order_df(json_file_path)


def generate_rider_daily_stat_df(json_file_path):
    """Backward-compatible alias for the correctly spelled function name."""
    return gennerate_rider_daily_stat_df(json_file_path)


def generate_rider_hourly_worktime_df(json_file_path):
    """Backward-compatible alias for the correctly spelled function name."""
    return gennerate_rider_hourly_worktime_df(json_file_path)


if __name__ == "__main__":
    Location = "Shanghai"

    input_folder = os.path.join(Location, "Json_data")
    climate_folder = os.path.join(Location, "climate")
    jsonPro_folder = os.path.join(Location, "Json_res")
    output_folder = os.path.join(Location, "Risk_Cal")

    os.makedirs(output_folder, exist_ok=True)
    os.makedirs(jsonPro_folder, exist_ok=True)
    os.makedirs(climate_folder, exist_ok=True)

    input_file_path = os.path.join(input_folder, "order_data.json")
    output_file_path = os.path.join(output_folder, "orders_revise.json")

    order_tree = extract_rider_orders(json_file_path=input_file_path)
    with open(output_file_path, "w", encoding="utf-8") as f:
        json.dump(order_tree, f, ensure_ascii=False, indent=2)
    print(f"Extracted rider order data saved to {output_file_path}")

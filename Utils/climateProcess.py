"""Retrieve hourly weather data and calculate outdoor heat/cold stress metrics."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import requests
from numba import njit


SIGMA = 5.67e-8
SURFACE_EMISSIVITY = 0.95
DEFAULT_CYCLING_SPEED_MS = 25 / 3.6

CITY_COORDINATES = {
    "Harbin": (45.75, 126.63),
    "Shanghai": (31.23, 121.47),
    "Guangzhou": (23.13, 113.26),
}

CITY_RADIATION_PARAMETERS = {
    "Harbin": {"bowen_ratio": 3.0, "svf": 0.25},
    "Shanghai": {"bowen_ratio": 1.0, "svf": 0.25},
    "Guangzhou": {"bowen_ratio": 1.0, "svf": 0.25},
}


def RH_convert_from_Trise(df_climate: pd.DataFrame, T_rise: float) -> pd.DataFrame:
    """Adjust relative humidity for a temperature-rise scenario."""
    ta_c = df_climate["Ta"].to_numpy()
    rh = df_climate["RH"].to_numpy()
    ta_c_new = ta_c + T_rise

    psa_original = Psa_kPa_from_TaC(ta_c)
    psa_new = Psa_kPa_from_TaC(ta_c_new)
    rh_new = rh * psa_original / psa_new

    df_out = df_climate.copy()
    df_out["RH"] = np.clip(rh_new, 0, 100)
    return df_out


@njit
def T_Celsius_to_Kelvin(T_c: float) -> float:
    return T_c + 273.15


@njit
def Abs_Hum_from_TaC_PakPa(T_C: float, Pa_kPa: float) -> float:
    return 2.17 * (Pa_kPa / (T_C + 273.15))


@njit
def Psa_kPa_from_TaC(T_C: Any) -> Any:
    return np.exp(18.956 - (4030.18 / (T_C + 235))) / 10


@njit
def Pv_kPa_from_Psa_RH(Psa_kPa: float, RH: float) -> float:
    return Psa_kPa * RH / 100


@njit
def hc_cof_from_Av(Av_ms: float) -> float:
    return np.where(Av_ms < 1, 3.5 + 5.2 * Av_ms, (Av_ms**0.6) * 8.7)


@njit
def calc_relative_wind(wind_10m_arr: np.ndarray, cycling_speed: float) -> tuple[np.ndarray, np.ndarray]:
    """Convert 10 m wind speed to 1.5 m wind speed and worker-relative wind speed."""
    wind_1p5m = wind_10m_arr * (1.5 / 10) ** 0.143
    relative_wind = np.sqrt(wind_1p5m**2 + cycling_speed**2)
    return wind_1p5m, relative_wind


def calc_LR_sky(Ta_C: Any, RH: Any, N: Any) -> Any:
    """Calculate downward longwave sky radiation."""
    ta_k = Ta_C + 273.15
    vapor_pressure_hpa = RH / 100 * 6.105 * np.exp(17.27 * Ta_C / (237.7 + Ta_C))
    emissivity_clear = 0.82 - 0.25 * 10 ** (-0.0945 * vapor_pressure_hpa)
    emissivity_cloudy = emissivity_clear + emissivity_clear * 0.21 * N**2.5
    return emissivity_cloudy * SIGMA * ta_k**4


def solve_LR_s_vectorized(
    epsilon: float,
    Ta_K: Any,
    swr: Any,
    LR_down: Any,
    WS: Any,
    B0: Any = 1.0,
    tol: float = 1e-6,
    max_iter: int = 200,
) -> Any:
    """Solve surface longwave radiation iteratively."""
    lr_surface = LR_down.copy()
    for _ in range(max_iter):
        q_net = 0.7 * swr + LR_down - lr_surface
        storage_term = np.where(q_net > 0, -0.19 * q_net, -0.32 * q_net)
        denominator = 6.2 + 4.26 * WS
        surface_temp_k = Ta_K + (q_net + storage_term) / denominator * (1 + 1 / B0)
        surface_temp_k = np.clip(surface_temp_k, 0, 400)
        lr_new = epsilon * SIGMA * surface_temp_k**4 + (1 - epsilon) * LR_down
        lr_new = np.clip(lr_new, 0, 1e6)
        if np.all(np.abs(lr_new - lr_surface) < tol):
            return lr_new
        lr_surface = lr_new
    return lr_surface


def calc_LR_surface(
    Ta_C: Any,
    RH: Any,
    N: Any,
    WS: Any,
    SWR: Any,
    B0: Any,
    epsilon_surface: float = SURFACE_EMISSIVITY,
) -> tuple[Any, Any]:
    lr_down = calc_LR_sky(Ta_C, RH, N)
    ta_k = Ta_C + 273.15
    lr_surface = solve_LR_s_vectorized(epsilon_surface, ta_k, SWR, lr_down, WS, B0)
    return lr_down, lr_surface


def calc_MRT(Ta_C: Any, RH: Any, N: Any, WS: Any, SWR: Any, Bowen_ratio: Any, SVF: Any) -> Any:
    """Calculate mean radiant temperature in degrees Celsius."""
    shortwave_absorptivity = 0.7
    person_emissivity = 0.97
    ta_k = Ta_C + 273.15
    # Longwave radiation is approximated by air temperature.
    mrt_k = (ta_k**4 + (shortwave_absorptivity * SWR / (person_emissivity * SIGMA)) * SVF) ** 0.25
    return mrt_k - 273.15


def cal_WBGT(df_climate: pd.DataFrame) -> pd.DataFrame:
    """Add wet-bulb globe temperature (WBGT) to a climate DataFrame."""
    coef_l = [
        -2836.5744,
        -6028.076559,
        19.54263612,
        -0.02737830188,
        0.000016261698,
        7.0229056e-10,
        -1.8680009e-13,
    ]
    tmp_df = df_climate.copy()
    tmp_df["tAir_K"] = tmp_df["Ta"] + 273.15
    tmp_df["qAir_hPa"] = 2.7150305 * np.log(tmp_df["tAir_K"])

    for i_coef, coef in enumerate(coef_l):
        tmp_df["qAir_hPa"] += coef * (tmp_df["tAir_K"] ** (i_coef - 2))

    tmp_df["qAir_hPa"] = np.exp(tmp_df["qAir_hPa"]) * tmp_df["RH"] * 0.01 / 100
    tmp_df["tWet_C"] = 1.885 + 0.3704 * tmp_df["Ta"] + 0.4492 * tmp_df["qAir_hPa"]
    tmp_df["tGlobe_C"] = (
        2.098
        - 2.561 * tmp_df["WS_move"]
        + 0.5957 * tmp_df["Ta"]
        + 0.4017 * tmp_df["MRT_move"]
    )
    df_climate["WBGT"] = 0.7 * tmp_df["tWet_C"] + 0.2 * tmp_df["tGlobe_C"] + 0.1 * tmp_df["Ta"]
    return df_climate


def cal_WCI(df_climate: pd.DataFrame) -> pd.DataFrame:
    """Add wind chill index (WCI) to a climate DataFrame."""
    wind_factor = df_climate["WS_move"] ** 0.16
    df_climate["WCI"] = (
        13.12
        + 0.6215 * df_climate["Ta"]
        - 11.37 * wind_factor
        + 0.3965 * df_climate["Ta"] * wind_factor
    )
    return df_climate


def get_city_radiation_parameters(location: str) -> tuple[float, float]:
    parameters = CITY_RADIATION_PARAMETERS.get(location, CITY_RADIATION_PARAMETERS["Shanghai"])
    return parameters["bowen_ratio"], parameters["svf"]


def build_open_meteo_params(location: str, start_date: str, end_date: str) -> dict[str, Any]:
    latitude, longitude = CITY_COORDINATES[location]
    return {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date,
        "end_date": end_date,
        "hourly": (
            "temperature_2m,relativehumidity_2m,windspeed_10m,"
            "shortwave_radiation,cloudcover,diffuse_radiation"
        ),
        "temperature_unit": "celsius",
        "windspeed_unit": "ms",
        "timeformat": "iso8601",
        "timezone": "Asia/Shanghai",
    }


def get_climate_data(Location: str, Start_date: str, End_date: str, T_rise: float = 0) -> pd.DataFrame:
    """Download hourly climate data and derive MRT, WBGT, and WCI."""
    if Location not in CITY_COORDINATES:
        raise ValueError(f"Unsupported location: {Location}")

    bowen_ratio, svf = get_city_radiation_parameters(Location)
    params = build_open_meteo_params(Location, Start_date, End_date)
    response = requests.get("https://archive-api.open-meteo.com/v1/archive", params=params)
    response.raise_for_status()

    df_climate = pd.DataFrame(response.json()["hourly"])
    df_climate["time"] = pd.to_datetime(df_climate["time"])
    df_climate["relativehumidity_2m"] = df_climate["relativehumidity_2m"].clip(lower=20)

    wind_10m = df_climate["windspeed_10m"].to_numpy(dtype=np.float64)
    ta_baseline = df_climate["temperature_2m"].to_numpy(dtype=np.float64)
    ta_c = ta_baseline + T_rise
    swr_wm2 = df_climate["shortwave_radiation"].to_numpy(dtype=np.float64)
    rh_baseline = df_climate["relativehumidity_2m"].to_numpy(dtype=np.float64)
    rh = np.clip(rh_baseline * Psa_kPa_from_TaC(ta_baseline) / Psa_kPa_from_TaC(ta_c), 0, 100)
    cloud_fraction = df_climate["cloudcover"].to_numpy(dtype=np.float64) / 100

    wind_1p5m, relative_wind = calc_relative_wind(wind_10m, DEFAULT_CYCLING_SPEED_MS)
    mrt_move = calc_MRT(ta_c, rh, cloud_fraction, wind_1p5m, swr_wm2, bowen_ratio, svf)

    df_climate["cloudcover"] = df_climate["cloudcover"] / 100
    df_climate["temperature_2m"] = ta_c
    df_climate["relativehumidity_2m"] = rh
    df_climate["WS_move"] = relative_wind
    df_climate["MRT_still"] = ta_c
    df_climate["MRT_move"] = mrt_move
    df_climate.rename(
        columns={
            "time": "timestamp",
            "temperature_2m": "Ta",
            "relativehumidity_2m": "RH",
        },
        inplace=True,
    )

    df_climate = cal_WBGT(df_climate)
    df_climate = cal_WCI(df_climate)
    return df_climate

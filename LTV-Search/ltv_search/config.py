"""Configuration for LTV Search v2. Loads from YAML with env overrides. Precedence: env > file > defaults."""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml


@dataclass
class Config:
    # Mode
    generate_test_simulation: bool = True
    enable_viz: bool = True

    # RSSI model: "linear" (DUST-style) or "path_loss" (log-distance)
    rssi_model: str = "linear"

    # Linear model params (rssi = intercept + slope * distance_m)
    rssi_linear_intercept: float = 0.0
    rssi_linear_slope: float = -0.075

    # Path-loss model params (kept for optional use)
    rssi_ref_dbm: float = -30.0
    d_ref_m: float = 100.0
    path_loss_n: float = 2.5

    rssi_noise_std: float = 1.0

    # Search
    max_pings: int = 10
    found_distance_m: float = 30.0
    search_radius_m: float = 1500.0
    trilateration_offset_scale: float = 0.5

    # Ping timing
    ping_min_interval_sec: float = 20.0

    # Test simulation
    test_sim_seed: Optional[int] = None
    test_sim_unlimited_pings: bool = False
    test_sim_ping_interval_sec: float = 1.0
    test_sim_ltv_min_distance_m: float = 200.0
    test_sim_ltv_max_distance_m: float = 1200.0

    # Tolerances
    at_lkp_tolerance_m: float = 15.0
    arrived_tolerance_m: float = 20.0
    arrived_timeout_sec: float = 300.0

    # TSS
    tss_host: str = "127.0.0.1"
    tss_port: int = 5000


def _env_bool(key: str, default: bool) -> bool:
    v = os.environ.get(key)
    if v is None:
        return default
    return v.lower() in ("1", "true", "yes", "on")


def _env_int(key: str, default: Optional[int]) -> Optional[int]:
    v = os.environ.get(key)
    if v is None:
        return default
    try:
        return int(v)
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    v = os.environ.get(key)
    if v is None:
        return default
    try:
        return float(v)
    except ValueError:
        return default


def load_config(path: Optional[Path] = None) -> Config:
    cfg = Config()
    if path is not None and path.exists():
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        if isinstance(data, dict):
            _apply_dict(cfg, data)

    cfg.generate_test_simulation = _env_bool("LTV_GENERATE_TEST_SIMULATION", cfg.generate_test_simulation)
    cfg.enable_viz = _env_bool("LTV_ENABLE_VIZ", cfg.enable_viz)
    cfg.test_sim_seed = _env_int("LTV_TEST_SIM_SEED", cfg.test_sim_seed)
    cfg.test_sim_unlimited_pings = _env_bool("LTV_TEST_SIM_UNLIMITED_PINGS", cfg.test_sim_unlimited_pings)
    cfg.max_pings = int(_env_float("LTV_MAX_PINGS", cfg.max_pings))
    cfg.found_distance_m = _env_float("LTV_FOUND_DISTANCE_M", cfg.found_distance_m)
    cfg.search_radius_m = _env_float("LTV_SEARCH_RADIUS_M", cfg.search_radius_m)
    cfg.rssi_model = os.environ.get("LTV_RSSI_MODEL", cfg.rssi_model)
    cfg.rssi_linear_intercept = _env_float("LTV_RSSI_LINEAR_INTERCEPT", cfg.rssi_linear_intercept)
    cfg.rssi_linear_slope = _env_float("LTV_RSSI_LINEAR_SLOPE", cfg.rssi_linear_slope)
    cfg.path_loss_n = _env_float("LTV_PATH_LOSS_N", cfg.path_loss_n)
    cfg.rssi_ref_dbm = _env_float("LTV_RSSI_REF_DBM", cfg.rssi_ref_dbm)
    cfg.d_ref_m = _env_float("LTV_D_REF_M", cfg.d_ref_m)
    cfg.rssi_noise_std = _env_float("LTV_RSSI_NOISE_STD", cfg.rssi_noise_std)
    cfg.trilateration_offset_scale = _env_float("LTV_TRILATERATION_OFFSET_SCALE", cfg.trilateration_offset_scale)
    cfg.at_lkp_tolerance_m = _env_float("LTV_AT_LKP_TOLERANCE_M", cfg.at_lkp_tolerance_m)
    cfg.arrived_tolerance_m = _env_float("LTV_ARRIVED_TOLERANCE_M", cfg.arrived_tolerance_m)
    cfg.ping_min_interval_sec = _env_float("LTV_PING_MIN_INTERVAL_SEC", cfg.ping_min_interval_sec)

    return cfg


def _apply_dict(cfg: Config, data: dict[str, Any]) -> None:
    for key, value in data.items():
        if not hasattr(cfg, key):
            continue
        if key == "test_sim_seed":
            setattr(cfg, key, None if value is None else int(value))
        else:
            t = type(getattr(cfg, key))
            if t == bool and not isinstance(value, bool):
                setattr(cfg, key, str(value).lower() in ("1", "true", "yes", "on"))
            elif t in (int, float):
                setattr(cfg, key, t(value))
            else:
                setattr(cfg, key, value)

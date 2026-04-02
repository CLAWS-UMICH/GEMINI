"""RSSI <-> distance conversion for LTV Search v2.

Supports two models:
  - "linear": DUST-style linear scaling (rssi = intercept + slope * distance)
  - "path_loss": Log-distance path-loss model (rssi = ref - 10*n*log10(d/d_ref))
"""
import math
import random
from typing import Tuple


def rssi_to_distance(
    rssi_dbm: float,
    *,
    model: str = "linear",
    intercept: float = 0.0,
    slope: float = -0.075,
    rssi_ref: float = -30.0,
    d_ref: float = 100.0,
    n: float = 2.5,
    noise_std: float = 1.0,
) -> Tuple[float, float]:
    """Convert RSSI to estimated distance and uncertainty (sigma).

    Returns (distance_m, sigma_m).
    """
    if model == "linear":
        if abs(slope) < 1e-12:
            return (1.0, 1.0)
        d = (rssi_dbm - intercept) / slope
        sigma = noise_std / abs(slope)
        return (max(1.0, d), max(1.0, sigma))

    # path_loss
    exponent = (rssi_ref - rssi_dbm) / (10.0 * n)
    d = d_ref * (10.0 ** exponent)
    sigma = d * math.log(10) / (10.0 * n) * noise_std
    return (max(1.0, d), max(1.0, sigma))


def distance_to_rssi(
    distance_m: float,
    *,
    model: str = "linear",
    intercept: float = 0.0,
    slope: float = -0.075,
    rssi_ref: float = -30.0,
    d_ref: float = 100.0,
    n: float = 2.5,
    noise_std: float = 0.0,
) -> float:
    """Convert distance to RSSI. Forward model for test simulator."""
    d = max(1.0, float(distance_m))

    if model == "linear":
        rssi = intercept + slope * d
    else:
        rssi = rssi_ref - 10.0 * n * math.log10(d / d_ref)

    if noise_std > 0:
        rssi += random.gauss(0, noise_std)
    return rssi

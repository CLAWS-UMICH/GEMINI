"""Test simulator: EnvironmentAdapter for development without TSS/DUST."""
import math
import random
import time
from typing import Tuple

from .config import Config
from .environment import EnvironmentAdapter
from .rssi import distance_to_rssi


class TestSimulatorAdapter(EnvironmentAdapter):
    """
    Simulator: LKP at center of dynamic search area, LTV at random offset,
    rover snaps to waypoints, ping returns RSSI from true distance.
    """

    def __init__(self, config: Config):
        self.config = config

        # LKP at origin (or any fixed point — search is relative)
        self._lkp_x = 0.0
        self._lkp_y = 0.0

        if config.test_sim_seed is not None:
            random.seed(config.test_sim_seed)

        dist = random.uniform(config.test_sim_ltv_min_distance_m, config.test_sim_ltv_max_distance_m)
        angle = random.uniform(0, 2 * math.pi)
        self._ltv_x = self._lkp_x + dist * math.cos(angle)
        self._ltv_y = self._lkp_y + dist * math.sin(angle)

        # Clamp LTV to search radius
        r = config.search_radius_m
        self._ltv_x = max(self._lkp_x - r, min(self._lkp_x + r, self._ltv_x))
        self._ltv_y = max(self._lkp_y - r, min(self._lkp_y + r, self._ltv_y))

        self._rover_x = self._lkp_x
        self._rover_y = self._lkp_y
        self._target_x: float | None = None
        self._target_y: float | None = None
        self._pings_used = 0
        self._last_ping_time = 0.0
        self._waypoint_set_time = time.monotonic()

    def get_lkp(self) -> Tuple[float, float]:
        return (self._lkp_x, self._lkp_y)

    def get_rover_position(self) -> Tuple[float, float]:
        return (self._rover_x, self._rover_y)

    def ping(self) -> float:
        self._last_ping_time = time.monotonic()
        self._pings_used += 1
        dist = math.hypot(self._rover_x - self._ltv_x, self._rover_y - self._ltv_y)
        return distance_to_rssi(
            dist,
            model=self.config.rssi_model,
            intercept=self.config.rssi_linear_intercept,
            slope=self.config.rssi_linear_slope,
            rssi_ref=self.config.rssi_ref_dbm,
            d_ref=self.config.d_ref_m,
            n=self.config.path_loss_n,
            noise_std=self.config.rssi_noise_std,
        )

    def set_target_waypoint(self, x: float, y: float) -> None:
        r = self.config.search_radius_m
        lx, ly = self._lkp_x, self._lkp_y
        x = max(lx - r, min(lx + r, x))
        y = max(ly - r, min(ly + r, y))
        self._target_x, self._target_y = x, y
        self._rover_x, self._rover_y = x, y
        self._waypoint_set_time = time.monotonic()

    def is_arrived(self) -> bool:
        if self._target_x is None:
            return True
        dist = math.hypot(self._rover_x - self._target_x, self._rover_y - self._target_y)
        if dist <= self.config.arrived_tolerance_m:
            return True
        if (time.monotonic() - self._waypoint_set_time) >= self.config.arrived_timeout_sec:
            return True
        return False

    def get_pings_left(self) -> int:
        if self.config.test_sim_unlimited_pings:
            return -1
        return max(0, self.config.max_pings - self._pings_used)

    def get_ping_interval_sec(self) -> float:
        return self.config.ping_min_interval_sec

    def get_true_ltv_position(self) -> Tuple[float, float]:
        return (self._ltv_x, self._ltv_y)

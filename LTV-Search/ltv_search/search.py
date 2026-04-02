"""
Search state machine for LTV Search v2.
Uses LTVSearcher internally; drives the rover via EnvironmentAdapter;
communicates with visualization via SharedState.
"""
import math
import threading
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .config import Config
from .environment import EnvironmentAdapter
from .searcher import LTVSearcher


@dataclass
class SharedState:
    """Thread-safe shared state between search thread and visualization."""
    phase: str = "idle"
    lkp: Tuple[float, float] = (0.0, 0.0)
    rover: Tuple[float, float] = (0.0, 0.0)
    waypoint: Optional[Tuple[float, float]] = None
    found: bool = False
    found_coords: Optional[Tuple[float, float]] = None
    seed: Optional[int] = None
    estimate: Optional[Tuple[float, float]] = None

    # Ping data: list of (x, y, estimated_distance)
    pings: List[Tuple[float, float, float]] = None
    circles: List[Tuple[float, float, float]] = None
    ping_count: int = 0
    ping_limit: int = 10

    waypoint_history: List[Tuple[str, float, float]] = None
    autoplay: bool = True
    advance_requested: Optional[threading.Event] = None
    _lock: threading.Lock = None

    def __post_init__(self):
        if self.pings is None:
            self.pings = []
        if self.circles is None:
            self.circles = []
        if self.waypoint_history is None:
            self.waypoint_history = []
        if self._lock is None:
            self._lock = threading.Lock()

    def set_phase(self, p: str) -> None:
        with self._lock:
            self.phase = p

    def set_rover(self, x: float, y: float) -> None:
        with self._lock:
            self.rover = (x, y)

    def set_waypoint(self, w: Optional[Tuple[float, float]]) -> None:
        with self._lock:
            self.waypoint = w
            if w is not None:
                self.waypoint_history.append(("waypoint", w[0], w[1]))

    def add_ping(self, x: float, y: float, distance: float) -> None:
        with self._lock:
            self.pings.append((x, y, distance))
            self.circles = list(self.pings)
            self.ping_count = len(self.pings)
            self.waypoint_history.append(("ping", x, y))

    def set_estimate(self, est: Optional[Tuple[float, float]]) -> None:
        with self._lock:
            self.estimate = est

    def set_found(self, x: float, y: float) -> None:
        with self._lock:
            self.found = True
            self.found_coords = (x, y)
            self.phase = "found"
        print("LTV found at", (x, y))

    def wait_advance(self, step_mode: bool) -> None:
        if not step_mode or self.advance_requested is None:
            return
        self.advance_requested.clear()
        self.advance_requested.wait()

    def request_advance(self) -> None:
        if self.advance_requested:
            self.advance_requested.set()


def _dist(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(ax - bx, ay - by)


def _is_ltv_found(adapter: EnvironmentAdapter, rx: float, ry: float, config: Config) -> bool:
    if hasattr(adapter, "get_true_ltv_position"):
        tx, ty = adapter.get_true_ltv_position()
        return _dist(rx, ry, tx, ty) <= config.found_distance_m
    return False


def run_search(adapter: EnvironmentAdapter, config: Config, shared: SharedState) -> None:
    """Run the trilateration search. Updates shared state for visualization."""
    shared.set_phase("idle")
    lkp_x, lkp_y = adapter.get_lkp()
    shared.lkp = (lkp_x, lkp_y)
    shared.ping_limit = config.max_pings if adapter.get_pings_left() != -1 else 999

    # Wait until at LKP
    while True:
        rx, ry = adapter.get_rover_position()
        shared.set_rover(rx, ry)
        if _dist(rx, ry, lkp_x, lkp_y) <= config.at_lkp_tolerance_m:
            break
        time.sleep(0.2)

    searcher = LTVSearcher(
        lkp_x=lkp_x,
        lkp_y=lkp_y,
        found_distance_m=config.found_distance_m,
        offset_scale=config.trilateration_offset_scale,
        search_radius_m=config.search_radius_m,
        rssi_model=config.rssi_model,
        rssi_linear_intercept=config.rssi_linear_intercept,
        rssi_linear_slope=config.rssi_linear_slope,
        rssi_ref_dbm=config.rssi_ref_dbm,
        d_ref_m=config.d_ref_m,
        path_loss_n=config.path_loss_n,
        rssi_noise_std=config.rssi_noise_std,
    )

    last_ping_time = 0.0

    def _step_mode() -> bool:
        with shared._lock:
            return not shared.autoplay and shared.advance_requested is not None

    def can_ping() -> bool:
        pings_left = adapter.get_pings_left()
        if pings_left == 0:
            return False
        now = time.monotonic()
        if shared.ping_count > 0 and (now - last_ping_time) < config.ping_min_interval_sec:
            return False
        return True

    shared.set_phase("triangulate")

    # Main search loop: ping -> get action from searcher -> drive to target -> repeat
    while True:
        rx, ry = adapter.get_rover_position()
        shared.set_rover(rx, ry)

        if _is_ltv_found(adapter, rx, ry, config):
            shared.set_found(rx, ry)
            return

        if adapter.get_pings_left() == 0:
            shared.set_phase("pings_exhausted")
            return

        # Wait for ping interval
        if not can_ping():
            now = time.monotonic()
            wait_sec = config.ping_min_interval_sec - (now - last_ping_time)
            if wait_sec > 0.05:
                time.sleep(wait_sec)

        if not can_ping():
            shared.set_phase("pings_exhausted")
            return

        # Ping
        rssi = adapter.ping()
        last_ping_time = time.monotonic()
        rx, ry = adapter.get_rover_position()

        # Get distance estimate for shared state
        from .rssi import rssi_to_distance
        d_est, _ = rssi_to_distance(
            rssi,
            model=config.rssi_model,
            intercept=config.rssi_linear_intercept,
            slope=config.rssi_linear_slope,
            rssi_ref=config.rssi_ref_dbm,
            d_ref=config.d_ref_m,
            n=config.path_loss_n,
            noise_std=config.rssi_noise_std,
        )
        shared.add_ping(rx, ry, d_est)

        # Feed to searcher
        action = searcher.report_ping(rx, ry, rssi)
        shared.set_estimate(action.estimate)

        if action.action_type == "found":
            shared.set_found(rx, ry)
            return

        if action.phase == "approaching":
            shared.set_phase("approach")

        if action.target is None:
            continue

        # Drive to target
        tx, ty = action.target
        shared.set_waypoint((tx, ty))
        shared.wait_advance(_step_mode())
        adapter.set_target_waypoint(tx, ty)

        while not adapter.is_arrived():
            rx, ry = adapter.get_rover_position()
            shared.set_rover(rx, ry)
            time.sleep(0.1)

        rx, ry = adapter.get_rover_position()
        shared.set_rover(rx, ry)

        if _is_ltv_found(adapter, rx, ry, config):
            shared.set_found(rx, ry)
            return

        if config.enable_viz and not _step_mode():
            time.sleep(0.05)

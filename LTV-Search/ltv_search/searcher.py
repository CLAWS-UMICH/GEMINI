"""
LTVSearcher — public integration API for LTV Search v2.

No dependency on environment.py, search.py, visualization, Pygame, or config files.
Only depends on rssi.py and trilateration.py.

Usage:
    from ltv_search import LTVSearcher

    searcher = LTVSearcher(lkp_x=-5839.0, lkp_y=-10460.0)
    action = searcher.report_ping(rover_x, rover_y, rssi_dbm)
    # action.action_type: "move_and_ping" | "move_to_estimate" | "found"
    # action.target: (x, y) — where to drive next
"""
import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .rssi import rssi_to_distance
from .trilateration import solve as trilaterate


@dataclass
class SearchAction:
    action_type: str
    target: Optional[Tuple[float, float]] = None
    estimate: Optional[Tuple[float, float]] = None
    phase: str = "triangulating"
    confidence: Optional[float] = None


class LTVSearcher:
    """Stateful trilateration-based LTV search. Feed pings, get waypoints."""

    def __init__(
        self,
        lkp_x: float,
        lkp_y: float,
        found_distance_m: float = 30.0,
        offset_scale: float = 0.5,
        search_radius_m: float = 1500.0,
        rssi_model: str = "linear",
        rssi_linear_intercept: float = 0.0,
        rssi_linear_slope: float = -0.075,
        rssi_ref_dbm: float = -30.0,
        d_ref_m: float = 100.0,
        path_loss_n: float = 2.5,
        rssi_noise_std: float = 1.0,
    ):
        self.lkp_x = lkp_x
        self.lkp_y = lkp_y
        self.found_distance_m = found_distance_m
        self.offset_scale = offset_scale
        self.search_radius_m = search_radius_m
        self.rssi_model = rssi_model
        self.rssi_intercept = rssi_linear_intercept
        self.rssi_slope = rssi_linear_slope
        self.rssi_ref = rssi_ref_dbm
        self.d_ref = d_ref_m
        self.path_loss_n = path_loss_n
        self.rssi_noise_std = rssi_noise_std

        self.circles: List[Tuple[float, float, float]] = []
        self.estimate: Optional[Tuple[float, float]] = None
        self._phase = "triangulating"

    @classmethod
    def from_calibration(
        cls,
        lkp_x: float,
        lkp_y: float,
        known_points: List[Tuple[float, float]],
        **kwargs,
    ) -> "LTVSearcher":
        """Create an LTVSearcher with RSSI model fitted from measured data.

        ``known_points`` is a list of (distance_m, rssi_dbm) pairs collected
        during a calibration run in DUST.  A simple linear regression is used to
        derive *slope* and *intercept* so you don't have to compute them by hand.

        All other keyword arguments (``found_distance_m``, etc.) are forwarded
        to the regular constructor.
        """
        if len(known_points) < 2:
            raise ValueError("Need at least 2 (distance, rssi) points to calibrate")

        n = len(known_points)
        sum_d = sum(p[0] for p in known_points)
        sum_r = sum(p[1] for p in known_points)
        sum_dr = sum(p[0] * p[1] for p in known_points)
        sum_dd = sum(p[0] ** 2 for p in known_points)

        denom = n * sum_dd - sum_d ** 2
        if abs(denom) < 1e-12:
            raise ValueError("Calibration points are too close together to fit a line")

        slope = (n * sum_dr - sum_d * sum_r) / denom
        intercept = (sum_r - slope * sum_d) / n

        kwargs.setdefault("rssi_model", "linear")
        return cls(
            lkp_x=lkp_x,
            lkp_y=lkp_y,
            rssi_linear_slope=slope,
            rssi_linear_intercept=intercept,
            **kwargs,
        )

    def get_initial_waypoint(self) -> Tuple[float, float]:
        """Return the first waypoint (the LKP). Drive here before pinging."""
        return (self.lkp_x, self.lkp_y)

    def reset(
        self,
        lkp_x: Optional[float] = None,
        lkp_y: Optional[float] = None,
    ) -> None:
        """Clear all state and optionally set a new LKP. Keeps RSSI model config."""
        if lkp_x is not None:
            self.lkp_x = lkp_x
        if lkp_y is not None:
            self.lkp_y = lkp_y
        self.circles = []
        self.estimate = None
        self._phase = "triangulating"

    def report_ping(self, rover_x: float, rover_y: float, rssi_dbm: float) -> SearchAction:
        """
        Report a ping result. Returns a SearchAction telling the caller what to do next.
        """
        d, _ = rssi_to_distance(
            rssi_dbm,
            model=self.rssi_model,
            intercept=self.rssi_intercept,
            slope=self.rssi_slope,
            rssi_ref=self.rssi_ref,
            d_ref=self.d_ref,
            n=self.path_loss_n,
            noise_std=self.rssi_noise_std,
        )
        self.circles.append((rover_x, rover_y, d))
        n = len(self.circles)

        if n < 3:
            target = self._next_triangulation_position(n, d)
            return SearchAction(
                action_type="move_and_ping",
                target=target,
                estimate=None,
                phase="triangulating",
            )

        est_x, est_y, residual = trilaterate(self.circles)

        # Degenerate solution guard: clamp to search radius
        dx = est_x - self.lkp_x
        dy = est_y - self.lkp_y
        dist_from_lkp = math.hypot(dx, dy)
        if dist_from_lkp > self.search_radius_m:
            scale = self.search_radius_m / dist_from_lkp
            est_x = self.lkp_x + dx * scale
            est_y = self.lkp_y + dy * scale

        self.estimate = (est_x, est_y)
        self._phase = "approaching"

        if d <= self.found_distance_m:
            self._phase = "found"
            return SearchAction(
                action_type="found",
                target=None,
                estimate=self.estimate,
                phase="found",
                confidence=residual,
            )

        target = self._approach_target(rover_x, rover_y, est_x, est_y, n)

        return SearchAction(
            action_type="move_to_estimate",
            target=target,
            estimate=self.estimate,
            phase="approaching",
            confidence=residual,
        )

    def _approach_target(
        self, rover_x: float, rover_y: float, est_x: float, est_y: float, n_circles: int
    ) -> Tuple[float, float]:
        """Position next ping around the estimate for geometric diversity.

        For the first few approach pings, offsets the target perpendicular to the
        LKP→estimate line so that subsequent circles provide new angular information
        instead of clustering at the (possibly inaccurate) estimate.
        """
        if n_circles >= 6:
            return (est_x, est_y)

        dx = est_x - self.lkp_x
        dy = est_y - self.lkp_y
        dist_lkp_est = math.hypot(dx, dy)

        if dist_lkp_est < 30:
            return (est_x, est_y)

        perp_x = -dy / dist_lkp_est
        perp_y = dx / dist_lkp_est
        sign = 1 if n_circles % 2 == 1 else -1

        offset_r = max(80.0, dist_lkp_est * 0.15)
        return (est_x + sign * perp_x * offset_r, est_y + sign * perp_y * offset_r)

    def _next_triangulation_position(self, n_circles: int, last_distance: float) -> Tuple[float, float]:
        """Compute the next ping position for good geometric spread."""
        offset = max(200.0, last_distance * self.offset_scale)

        if n_circles == 1:
            return (self.lkp_x, self.lkp_y + offset)

        if n_circles == 2:
            p1x, p1y, _ = self.circles[0]
            p2x, p2y, _ = self.circles[1]
            mx = (p1x + p2x) / 2.0
            my = (p1y + p2y) / 2.0
            dx = p2x - p1x
            dy = p2y - p1y
            seg_len = math.hypot(dx, dy)
            if seg_len < 1.0:
                return (self.lkp_x + offset, self.lkp_y)
            perp_x = -dy / seg_len
            perp_y = dx / seg_len
            h = seg_len * math.sqrt(3) / 2.0
            return (mx + perp_x * h, my + perp_y * h)

        return (self.lkp_x + offset, self.lkp_y + offset)

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from pathlib import Path

from dumbdrive import (
    FrontendTimingLogger,
    REMOTE_SERVER,
    REMOTE_SERVER_URL,
    drive_to_goal,
    hold_with_ui_updates,
    make_sanitized_telemetry,
)
from main import (
    POSE_OFFSET_X_CM,
    POSE_OFFSET_Y_CM,
    POSE_UNITS_TO_CM,
    MapWindow,
    parse_pose,
    stop_rover,
)
from rover_control import (
    close_rover_socket,
    configure_remote_server,
    fetch_ltv_json,
    fetch_rover_json,
    open_rover_socket,
    send_float_command,
    set_brakes,
    set_lights,
    set_steering,
    set_throttle,
    wait_for_dust,
)

CMD_LTV_PING = 2050
CMD_LTV_PING_UNLIMITED = 2051
USE_UNLIMITED_PING = False
PING_SETTLE_SEC = 1.2
TRILOCATION_PING_STOP_SEC = 5.0
PING_LOG_INTERVAL_SEC = 1.0
PING_RESPONSE_TIMEOUT_SEC = 1.5
PING_RESPONSE_POLL_SEC = 0.05
PING_DISTANCE_SENTINEL = 1.0
PING_DISTANCE_REFERENCE_M = 100.0
PING_DISTANCE_COEFFICIENT = 34.28525109707769
PING_SENTINEL_RETRY_MAX = 3
PING_SENTINEL_RETRY_GOAL_REACHED_CM = 250.0
ENABLE_METRICS_LOGGING = False
SECOND_TRILOCATION_STRONG_PING_THRESHOLD = -0.75
MAX_DRIVE_SEGMENT_CM = 4000.0
LAST_KNOWN_GOAL_REACHED_CM = 10000.0
PING_MOVE_GOAL_REACHED_CM = 1000.0
FINAL_ESTIMATE_GOAL_REACHED_CM = 300.0
STOP_AT_LAST_KNOWN_ONLY = False
EFFICIENCY_MODE = True
GUIDED_PING_STEP_RADIUS_SCALE = 0.6
GUIDED_PING_STEP_MIN_CM = 1100.0
GUIDED_PING_STEP_MAX_CM = 2000.0
GUIDED_PING_LATERAL_SCALE = 1.25
GUIDED_PING_GOAL_REACHED_SCALE = 0.24
#OLD LTV, FROM PREVIOUS RUN, NO LONGER ACCURATE (it gets randomized every time)
REAL_LTV_LOCATION_M = (-6047.30, -10769.3, 1463.0)


@dataclass
class PingSample:
    rover_x_m: float
    rover_y_m: float
    ping_value: float
    radius_m: float


@dataclass(frozen=True)
class TrilaterationRoundConfig:
    round_index: int
    debug_prefix: str
    estimate_label: str
    prepare_status: str
    pre_drive_hold_debug_mode: str
    final_drive_debug_mode: str
    arrival_message: str


TRILATERATION_ROUNDS: tuple[TrilaterationRoundConfig, ...] = (
    TrilaterationRoundConfig(
        round_index=1,
        debug_prefix="dumblocate_round1",
        estimate_label="Trilaterated LTV estimate",
        prepare_status="Preparing final drive...",
        pre_drive_hold_debug_mode="dumblocate_hold_before_final_drive",
        final_drive_debug_mode="dumblocate_drive_final",
        arrival_message="Arrived near trilaterated LTV location.",
    ),
    TrilaterationRoundConfig(
        round_index=2,
        debug_prefix="dumblocate_round2",
        estimate_label="Second-round trilaterated LTV estimate",
        prepare_status="Preparing second final drive...",
        pre_drive_hold_debug_mode="dumblocate_hold_before_second_final_drive",
        final_drive_debug_mode="dumblocate_drive_second_final",
        arrival_message="Arrived near second-round trilaterated LTV location.",
    ),
    TrilaterationRoundConfig(
        round_index=3,
        debug_prefix="dumblocate_round3",
        estimate_label="Third-round trilaterated LTV estimate",
        prepare_status="Preparing third final drive...",
        pre_drive_hold_debug_mode="dumblocate_hold_before_third_final_drive",
        final_drive_debug_mode="dumblocate_drive_third_final",
        arrival_message="Arrived near third-round trilaterated LTV location.",
    ),
)


class LocateMetricsLogger:
    def __init__(self) -> None:
        root = Path("runs")
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / f"dumblocate_metrics_{time.strftime('%Y%m%d_%H%M%S')}.tsv"
        self._file = self.path.open("w", encoding="utf-8", newline="")
        self._file.write(
            "iso_time_utc\tmono_s\tphase\trover_x_m\trover_y_m\trover_z_m\t"
            "dist_to_real_ltv_m\tping_strength\tgoal_dist_cm\n"
        )
        self._file.flush()
        print(f"Locate metrics log: {self.path}")

    def log(self, *, phase: str, rover_x_m: float, rover_y_m: float, rover_z_m: float, ping_strength: float, goal_dist_cm: float) -> None:
        dx = rover_x_m - REAL_LTV_LOCATION_M[0]
        dy = rover_y_m - REAL_LTV_LOCATION_M[1]
        dz = rover_z_m - REAL_LTV_LOCATION_M[2]
        dist_m = math.sqrt(dx * dx + dy * dy + dz * dz)
        self._file.write(
            "\t".join(
                [
                    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    f"{time.monotonic():.3f}",
                    phase,
                    f"{rover_x_m:.3f}",
                    f"{rover_y_m:.3f}",
                    f"{rover_z_m:.3f}",
                    f"{dist_m:.3f}",
                    f"{ping_strength:.3f}",
                    f"{goal_dist_cm:.3f}",
                ]
            )
            + "\n"
        )
        self._file.flush()

    def close(self) -> None:
        self._file.close()


class PingStrengthSampler:
    def __init__(self, interval_sec: float) -> None:
        self.interval_sec = float(interval_sec)
        self.last_sample_monotonic: float | None = None
        self.last_strength: float = float("nan")
        self.enabled = True

    def sample(self, sock) -> tuple[float, bool]:
        now = time.monotonic()
        if not self.enabled:
            return (self.last_strength, False)
        if (
            self.last_sample_monotonic is None
            or (now - self.last_sample_monotonic) >= self.interval_sec
        ):
            self.last_strength = current_ping_strength(sock)
            self.last_sample_monotonic = now
            return (self.last_strength, True)
        return (self.last_strength, False)

def ltv_ping_to_meters(ping_value: float) -> float:
    ping = float(ping_value)
    if is_ltv_ping_distance_sentinel(ping):
        raise ValueError("LTV ping value 1.0 is a sentinel for distance > 500, not a circle radius")
    return PING_DISTANCE_REFERENCE_M * (10.0 ** ((-30.0 - ping) / PING_DISTANCE_COEFFICIENT))


def is_ltv_ping_distance_sentinel(ping_value: float) -> bool:
    return abs(float(ping_value) - PING_DISTANCE_SENTINEL) <= 1e-6



def read_ltv_signal_strength(sock) -> float:
    ltv_json = fetch_ltv_json(sock)
    signal = ltv_json.get("signal", {})
    return float(signal.get("strength", 0.0))


def raw_world_m_to_local_cm(x_m: float, y_m: float) -> tuple[float, float]:
    x_cm = float(x_m) * POSE_UNITS_TO_CM - POSE_OFFSET_X_CM
    y_cm = float(y_m) * POSE_UNITS_TO_CM - POSE_OFFSET_Y_CM
    return (x_cm, y_cm)


def fetch_pose_and_telemetry(sock) -> tuple[float, float, float, float, dict]:
    rover_json = fetch_rover_json(sock)
    raw_telemetry = rover_json.get("pr_telemetry")
    if not isinstance(raw_telemetry, dict):
        raise RuntimeError("ROVER.json did not contain pr_telemetry")
    telemetry = make_sanitized_telemetry(raw_telemetry)
    x_cm, y_cm, z_cm, heading_deg = parse_pose(telemetry)
    return (x_cm, y_cm, z_cm, heading_deg, raw_telemetry)


def fetch_ltv_last_known_goal(sock) -> tuple[tuple[float, float], tuple[float, float]]:
    ltv_json = fetch_ltv_json(sock)
    location = ltv_json.get("location", {})
    last_known_x_m = float(location.get("last_known_x", 0.0))
    last_known_y_m = float(location.get("last_known_y", 0.0))
    goal_xy = raw_world_m_to_local_cm(last_known_x_m, last_known_y_m)
    return ((last_known_x_m, last_known_y_m), goal_xy)


def request_ping_and_read_strength(sock) -> float:
    ping_command = CMD_LTV_PING_UNLIMITED if USE_UNLIMITED_PING else CMD_LTV_PING
    previous_strength = read_ltv_signal_strength(sock)
    send_float_command(sock, ping_command, 1.0)
    deadline = time.monotonic() + PING_RESPONSE_TIMEOUT_SEC
    latest_strength = previous_strength
    while time.monotonic() < deadline:
        time.sleep(PING_RESPONSE_POLL_SEC)
        latest_strength = read_ltv_signal_strength(sock)
        if latest_strength != previous_strength:
            return latest_strength
    # print(
    #     f"Warning: ping command {ping_command} did not change LTV signal strength "
    #     f"within {PING_RESPONSE_TIMEOUT_SEC:.2f}s; keeping {latest_strength:.3f}"
    # )
    return latest_strength


def current_ping_strength(sock) -> float:
    return request_ping_and_read_strength(sock)


def sample_ping(sock, raw_telemetry: dict) -> PingSample:
    ping_value = request_ping_and_read_strength(sock)
    radius_m = ltv_ping_to_meters(ping_value)
    rover_x_m = float(raw_telemetry.get("rover_pos_x", 0.0))
    rover_y_m = float(raw_telemetry.get("rover_pos_y", 0.0))
    sample = PingSample(
        rover_x_m=rover_x_m,
        rover_y_m=rover_y_m,
        ping_value=ping_value,
        radius_m=radius_m,
    )
    print(
        f"Ping sample: rover=({sample.rover_x_m:.3f}, {sample.rover_y_m:.3f}) m | "
        f"ping={sample.ping_value:.3f} | radius={sample.radius_m:.3f} m"
    )
    return sample


def try_sample_ping(sock, raw_telemetry: dict) -> PingSample | None:
    ping_value = request_ping_and_read_strength(sock)
    rover_x_m = float(raw_telemetry.get("rover_pos_x", 0.0))
    rover_y_m = float(raw_telemetry.get("rover_pos_y", 0.0))
    if is_ltv_ping_distance_sentinel(ping_value):
        print(
            f"Ping sample: rover=({rover_x_m:.3f}, {rover_y_m:.3f}) m | "
            f"ping={ping_value:.3f} means distance > 500; no trilateration radius"
        )
        return None
    radius_m = ltv_ping_to_meters(ping_value)
    sample = PingSample(
        rover_x_m=rover_x_m,
        rover_y_m=rover_y_m,
        ping_value=ping_value,
        radius_m=radius_m,
    )
    print(
        f"Ping sample: rover=({sample.rover_x_m:.3f}, {sample.rover_y_m:.3f}) m | "
        f"ping={sample.ping_value:.3f} | radius={sample.radius_m:.3f} m"
    )
    return sample


def stop_then_try_sample_ping(
    sock,
    run_state,
    *,
    viewer,
    telemetry_callback,
    debug_logger: FrontendTimingLogger | None,
    debug_mode: str,
    status: str,
) -> tuple[PingSample | None, bool]:
    set_throttle(sock, 0.0)
    set_steering(sock, 0.0)
    set_brakes(sock, True)
    if not hold_with_ui_updates(
        sock,
        viewer=viewer,
        planner=run_state.planner,
        goal_xy=run_state.goal_xy,
        obstacle_total=run_state.obstacle_total,
        start_time=run_state.start_time,
        total_traveled_cm=run_state.total_traveled_cm,
        duration_s=TRILOCATION_PING_STOP_SEC,
        status=status,
        telemetry_callback=telemetry_callback,
        debug_logger=debug_logger,
        debug_mode=debug_mode,
    ):
        return (None, False)

    rover_json = fetch_rover_json(sock)
    raw_telemetry = rover_json.get("pr_telemetry")
    if not isinstance(raw_telemetry, dict):
        raise RuntimeError("ROVER.json did not contain pr_telemetry")
    telemetry = make_sanitized_telemetry(raw_telemetry)
    run_state.raw_telemetry = raw_telemetry
    run_state.pose_xyzh = parse_pose(telemetry)
    return (try_sample_ping(sock, raw_telemetry), True)


def trilaterate(
    samples: tuple[PingSample, PingSample, PingSample],
) -> tuple[float, float]:
    s1, s2, s3 = samples
    for i, s in enumerate(samples):
        if not math.isfinite(s.radius_m):
            raise RuntimeError(
                f"Ping sample {i} has non-finite radius {s.radius_m!r}; cannot trilaterate"
            )
    min_pair_distance_m = min(
        math.hypot(s2.rover_x_m - s1.rover_x_m, s2.rover_y_m - s1.rover_y_m),
        math.hypot(s3.rover_x_m - s1.rover_x_m, s3.rover_y_m - s1.rover_y_m),
        math.hypot(s3.rover_x_m - s2.rover_x_m, s3.rover_y_m - s2.rover_y_m),
    )
    if min_pair_distance_m < 0.5:
        raise RuntimeError(
            "Ping geometry degenerate; at least two ping samples were taken from nearly "
            "the same rover position"
        )
    a11 = 2.0 * (s2.rover_x_m - s1.rover_x_m)
    a12 = 2.0 * (s2.rover_y_m - s1.rover_y_m)
    a21 = 2.0 * (s3.rover_x_m - s1.rover_x_m)
    a22 = 2.0 * (s3.rover_y_m - s1.rover_y_m)
    b1 = (
        s1.radius_m * s1.radius_m
        - s2.radius_m * s2.radius_m
        - s1.rover_x_m * s1.rover_x_m
        + s2.rover_x_m * s2.rover_x_m
        - s1.rover_y_m * s1.rover_y_m
        + s2.rover_y_m * s2.rover_y_m
    )
    b2 = (
        s1.radius_m * s1.radius_m
        - s3.radius_m * s3.radius_m
        - s1.rover_x_m * s1.rover_x_m
        + s3.rover_x_m * s3.rover_x_m
        - s1.rover_y_m * s1.rover_y_m
        + s3.rover_y_m * s3.rover_y_m
    )
    det = a11 * a22 - a12 * a21
    if abs(det) < 1e-9:
        raise RuntimeError("Ping geometry degenerate; cannot trilaterate")
    x_m = (b1 * a22 - b2 * a12) / det
    y_m = (a11 * b2 - a21 * b1) / det
    return (x_m, y_m)


def local_cm_to_raw_world_m(x_cm: float, y_cm: float) -> tuple[float, float]:
    x_m = (float(x_cm) + POSE_OFFSET_X_CM) / POSE_UNITS_TO_CM
    y_m = (float(y_cm) + POSE_OFFSET_Y_CM) / POSE_UNITS_TO_CM
    return (x_m, y_m)


def ping_move_goal_reached_cm(radius_m: float, desired_step_cm: float | None = None) -> float:
    radius_cm = float(radius_m) * 100.0
    tolerance_from_radius_cm = radius_cm * 0.2
    tolerance_from_step_cm = 0.0 if desired_step_cm is None else float(desired_step_cm) * GUIDED_PING_GOAL_REACHED_SCALE
    return max(
        FINAL_ESTIMATE_GOAL_REACHED_CM,
        min(PING_MOVE_GOAL_REACHED_CM, max(tolerance_from_radius_cm, tolerance_from_step_cm)),
    )


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def normalize_xy(dx: float, dy: float) -> tuple[float, float]:
    dist = math.hypot(dx, dy)
    if dist <= 1e-9:
        return (1.0, 0.0)
    return (dx / dist, dy / dist)


def guided_sample_points_cm(
    *,
    first_sample_xy: tuple[float, float],
    anchor_xy: tuple[float, float],
    first_radius_m: float,
    fallback_heading_deg: float,
) -> list[tuple[float, float]]:
    dx = anchor_xy[0] - first_sample_xy[0]
    dy = anchor_xy[1] - first_sample_xy[1]
    if math.hypot(dx, dy) <= 1e-6:
        heading_rad = math.radians(float(fallback_heading_deg))
        forward_x = math.cos(heading_rad)
        forward_y = math.sin(heading_rad)
    else:
        forward_x, forward_y = normalize_xy(dx, dy)
    left_x = -forward_y
    left_y = forward_x
    step_cm = clamp(
        float(first_radius_m) * 100.0 * GUIDED_PING_STEP_RADIUS_SCALE,
        GUIDED_PING_STEP_MIN_CM,
        GUIDED_PING_STEP_MAX_CM,
    )
    forward_goal_xy = (
        first_sample_xy[0] + forward_x * step_cm,
        first_sample_xy[1] + forward_y * step_cm,
    )
    lateral_goal_xy = (
        first_sample_xy[0] + forward_x * (0.5 * step_cm) + left_x * (step_cm * GUIDED_PING_LATERAL_SCALE),
        first_sample_xy[1] + forward_y * (0.5 * step_cm) + left_y * (step_cm * GUIDED_PING_LATERAL_SCALE),
    )
    return [forward_goal_xy, lateral_goal_xy]


def phase_label(phase: str) -> str:
    labels = {
        "to_last_known": "Drive: last known",
        "to_ping_2": "Move for ping 2",
        "to_ping_3": "Move for ping 3",
        "to_estimated": "Drive: trilaterated LTV",
        "done": "Done",
    }
    return labels.get(phase, phase)


def step_toward_goal_cm(
    start_xy: tuple[float, float],
    goal_xy: tuple[float, float],
    max_step_cm: float,
) -> tuple[float, float]:
    dx = float(goal_xy[0] - start_xy[0])
    dy = float(goal_xy[1] - start_xy[1])
    dist = math.hypot(dx, dy)
    if dist <= max_step_cm or dist <= 1e-6:
        return goal_xy
    scale = max_step_cm / dist
    return (start_xy[0] + dx * scale, start_xy[1] + dy * scale)


def drive_to_goal_segmented(
    sock,
    *,
    final_goal_xy: tuple[float, float],
    goal_label: str | None,
    viewer,
    recorded_obstacle_points: list[tuple[float, float]],
    obstacle_total: int,
    start_time: float | None,
    step_idx: int,
    total_traveled_cm: float,
    goals_reached: int,
    telemetry_callback=None,
    path_callback=None,
    debug_logger: FrontendTimingLogger | None,
    debug_mode: str,
    goal_reached_cm: float,
):
    run_state = None
    while True:
        if run_state is None:
            start_x, start_y, _z, _heading, _raw = fetch_pose_and_telemetry(sock)
            current_xy = (start_x, start_y)
        else:
            current_xy = (run_state.pose_xyzh[0], run_state.pose_xyzh[1])

        segment_goal_xy = step_toward_goal_cm(
            current_xy,
            final_goal_xy,
            MAX_DRIVE_SEGMENT_CM,
        )
        run_state = drive_to_goal(
            sock,
            goal_xy=segment_goal_xy,
            display_goal_xy=final_goal_xy,
            goal_label=goal_label,
            viewer=viewer,
            frontend_enabled=False,
            recorded_obstacle_points=recorded_obstacle_points,
            obstacle_total=obstacle_total,
            start_time=start_time,
            step_idx=step_idx,
            total_traveled_cm=total_traveled_cm,
            goals_reached=goals_reached,
            goal_reached_cm=goal_reached_cm,
            telemetry_callback=telemetry_callback,
            path_callback=path_callback,
            debug_logger=debug_logger,
            debug_mode=debug_mode,
        )
        if run_state.aborted:
            return run_state
        rover_x, rover_y, _z, _heading = run_state.pose_xyzh
        remaining_cm = math.hypot(final_goal_xy[0] - rover_x, final_goal_xy[1] - rover_y)
        if remaining_cm <= MAX_DRIVE_SEGMENT_CM:
            if segment_goal_xy == final_goal_xy:
                return run_state
            viewer = run_state.viewer
            recorded_obstacle_points = run_state.recorded_obstacle_points
            obstacle_total = run_state.obstacle_total
            start_time = run_state.start_time
            step_idx = run_state.step_idx
            total_traveled_cm = run_state.total_traveled_cm
            continue
        viewer = run_state.viewer
        recorded_obstacle_points = run_state.recorded_obstacle_points
        obstacle_total = run_state.obstacle_total
        start_time = run_state.start_time
        step_idx = run_state.step_idx
        total_traveled_cm = run_state.total_traveled_cm


def drive_to_goal_locate(
    sock,
    *,
    final_goal_xy: tuple[float, float],
    goal_label: str | None,
    viewer,
    recorded_obstacle_points: list[tuple[float, float]],
    obstacle_total: int,
    start_time: float | None,
    step_idx: int,
    total_traveled_cm: float,
    goals_reached: int,
    telemetry_callback=None,
    path_callback=None,
    debug_logger: FrontendTimingLogger | None,
    debug_mode: str,
    goal_reached_cm: float,
):
    if EFFICIENCY_MODE:
        return drive_to_goal(
            sock,
            goal_xy=final_goal_xy,
            display_goal_xy=final_goal_xy,
            goal_label=goal_label,
            viewer=viewer,
            frontend_enabled=False,
            recorded_obstacle_points=recorded_obstacle_points,
            obstacle_total=obstacle_total,
            start_time=start_time,
            step_idx=step_idx,
            total_traveled_cm=total_traveled_cm,
            goals_reached=goals_reached,
            goal_reached_cm=goal_reached_cm,
            replan_on_edge=False,
            replan_only_on_obstacle=True,
            telemetry_callback=telemetry_callback,
            path_callback=path_callback,
            debug_logger=debug_logger,
            debug_mode=debug_mode,
        )
    return drive_to_goal_segmented(
        sock,
        final_goal_xy=final_goal_xy,
        goal_label=goal_label,
        viewer=viewer,
        recorded_obstacle_points=recorded_obstacle_points,
        obstacle_total=obstacle_total,
        start_time=start_time,
        step_idx=step_idx,
        total_traveled_cm=total_traveled_cm,
        goals_reached=goals_reached,
        telemetry_callback=telemetry_callback,
        path_callback=path_callback,
        debug_logger=debug_logger,
        debug_mode=debug_mode,
        goal_reached_cm=goal_reached_cm,
    )


def drive_to_last_known_ltv(
    sock,
    *,
    viewer,
    recorded_obstacle_points: list[tuple[float, float]] | None = None,
    obstacle_total: int = 0,
    start_time: float | None = None,
    step_idx: int = 0,
    total_traveled_cm: float = 0.0,
    goals_reached: int = 0,
    goal_reached_cm: float = LAST_KNOWN_GOAL_REACHED_CM,
    telemetry_callback=None,
    path_callback=None,
    debug_logger: FrontendTimingLogger | None = None,
    debug_mode: str = "dumblocate_drive_last_known",
):
    last_known_xy_m, goal_xy = fetch_ltv_last_known_goal(sock)
    last_known_x_m, last_known_y_m = last_known_xy_m
    print(
        f"Last known LTV location: ({last_known_x_m:.3f}, {last_known_y_m:.3f}) m"
    )
    run_state = drive_to_goal_locate(
        sock,
        final_goal_xy=goal_xy,
        goal_label=f"{last_known_x_m:.3f}, {last_known_y_m:.3f}",
        viewer=viewer,
        recorded_obstacle_points=recorded_obstacle_points or [],
        obstacle_total=obstacle_total,
        start_time=start_time,
        step_idx=step_idx,
        total_traveled_cm=total_traveled_cm,
        goals_reached=goals_reached,
        goal_reached_cm=goal_reached_cm,
        telemetry_callback=telemetry_callback,
        path_callback=path_callback,
        debug_logger=debug_logger,
        debug_mode=debug_mode,
    )
    return run_state, goal_xy, last_known_xy_m


def collect_guided_ping_samples(
    sock,
    *,
    anchor_xy: tuple[float, float],
    run_state,
    viewer,
    telemetry_callback,
    path_callback=None,
    debug_logger: FrontendTimingLogger | None,
    debug_prefix: str,
) -> tuple[list[PingSample], object, MapWindow | None, bool]:
    samples: list[PingSample] = []
    first_sample: PingSample | None = None
    for attempt_idx in range(PING_SENTINEL_RETRY_MAX + 1):
        print(f"Collecting {debug_prefix} ping 1 at current rover position...")
        first_sample, ok = stop_then_try_sample_ping(
            sock,
            viewer=viewer,
            run_state=run_state,
            status=f"Stopping for {debug_prefix} ping 1...",
            telemetry_callback=telemetry_callback,
            debug_logger=debug_logger,
            debug_mode=f"{debug_prefix}_hold_ping_1",
        )
        if not ok:
            return (samples, run_state, viewer, False)
        if first_sample is not None:
            break
        if attempt_idx >= PING_SENTINEL_RETRY_MAX:
            print(
                f"{debug_prefix} ping 1 still reports distance > 500 after "
                f"{PING_SENTINEL_RETRY_MAX + 1} attempts; cannot trilaterate from here."
            )
            return (samples, run_state, viewer, False)

        anchor_x_m, anchor_y_m = local_cm_to_raw_world_m(*anchor_xy)
        remaining_cm = math.hypot(
            anchor_xy[0] - run_state.pose_xyzh[0],
            anchor_xy[1] - run_state.pose_xyzh[1],
        )
        print(
            f"{debug_prefix} ping 1 is out of range; driving closer to anchor "
            f"({anchor_x_m:.3f}, {anchor_y_m:.3f}) m before retry "
            f"{attempt_idx + 2}/{PING_SENTINEL_RETRY_MAX + 1}. "
            f"anchor_remaining={remaining_cm:.1f} cm"
        )
        run_state = drive_to_goal_locate(
            sock,
            final_goal_xy=anchor_xy,
            goal_label=f"{anchor_x_m:.3f}, {anchor_y_m:.3f}",
            viewer=viewer,
            recorded_obstacle_points=run_state.recorded_obstacle_points,
            obstacle_total=run_state.obstacle_total,
            start_time=run_state.start_time,
            step_idx=run_state.step_idx,
            total_traveled_cm=run_state.total_traveled_cm,
            goals_reached=0,
            goal_reached_cm=PING_SENTINEL_RETRY_GOAL_REACHED_CM,
            telemetry_callback=telemetry_callback,
            path_callback=path_callback,
            debug_logger=debug_logger,
            debug_mode=f"{debug_prefix}_drive_closer_after_sentinel",
        )
        viewer = run_state.viewer
        if run_state.aborted:
            return (samples, run_state, viewer, False)
    if first_sample is None:
        return (samples, run_state, viewer, False)
    samples.append(first_sample)

    first_sample_xy = (run_state.pose_xyzh[0], run_state.pose_xyzh[1])
    guided_points = guided_sample_points_cm(
        first_sample_xy=first_sample_xy,
        anchor_xy=anchor_xy,
        first_radius_m=samples[0].radius_m,
        fallback_heading_deg=run_state.pose_xyzh[3],
    )
    for ping_idx, guided_goal_xy in enumerate(guided_points, start=2):
        sample_x_m, sample_y_m = local_cm_to_raw_world_m(*guided_goal_xy)
        desired_step_cm = math.hypot(
            guided_goal_xy[0] - first_sample_xy[0],
            guided_goal_xy[1] - first_sample_xy[1],
        )
        move_goal_reached_cm = ping_move_goal_reached_cm(
            samples[0].radius_m,
            desired_step_cm=desired_step_cm,
        )
        print(
            f"Driving to {debug_prefix} ping {ping_idx} guided point: "
            f"({sample_x_m:.3f}, {sample_y_m:.3f}) m"
        )
        run_state = drive_to_goal_locate(
            sock,
            final_goal_xy=guided_goal_xy,
            goal_label=f"{sample_x_m:.3f}, {sample_y_m:.3f}",
            viewer=viewer,
            recorded_obstacle_points=run_state.recorded_obstacle_points,
            obstacle_total=run_state.obstacle_total,
            start_time=run_state.start_time,
            step_idx=run_state.step_idx,
            total_traveled_cm=run_state.total_traveled_cm,
            goals_reached=0,
            goal_reached_cm=move_goal_reached_cm,
            telemetry_callback=telemetry_callback,
            path_callback=path_callback,
            debug_logger=debug_logger,
            debug_mode=f"{debug_prefix}_drive_ping_{ping_idx}",
        )
        viewer = run_state.viewer
        if run_state.aborted:
            return (samples, run_state, viewer, False)

        print(f"Collecting {debug_prefix} ping {ping_idx}...")
        sample, ok = stop_then_try_sample_ping(
            sock,
            viewer=viewer,
            run_state=run_state,
            status=f"Stopping for {debug_prefix} ping {ping_idx}...",
            telemetry_callback=telemetry_callback,
            debug_logger=debug_logger,
            debug_mode=f"{debug_prefix}_hold_ping_{ping_idx}",
        )
        if not ok:
            return (samples, run_state, viewer, False)
        if sample is None:
            print(
                f"{debug_prefix} ping {ping_idx} reports distance > 500; "
                "cannot use it as a trilateration circle."
            )
            return (samples, run_state, viewer, False)
        samples.append(sample)
        if ping_idx < 3:
            if not hold_with_ui_updates(
                sock,
                viewer=viewer,
                planner=run_state.planner,
                goal_xy=run_state.goal_xy,
                obstacle_total=run_state.obstacle_total,
                start_time=run_state.start_time,
                total_traveled_cm=run_state.total_traveled_cm,
                duration_s=0.5,
                status="Preparing next move...",
                telemetry_callback=telemetry_callback,
                debug_logger=debug_logger,
                debug_mode=f"{debug_prefix}_hold_after_ping_{ping_idx}",
            ):
                return (samples, run_state, viewer, False)
    return (samples, run_state, viewer, True)


def run_trilateration_round(
    sock,
    *,
    round_config: TrilaterationRoundConfig,
    anchor_xy: tuple[float, float],
    run_state,
    viewer,
    telemetry_callback,
    path_callback=None,
    debug_logger: FrontendTimingLogger | None,
) -> tuple[tuple[float, float] | None, object, MapWindow | None, bool]:
    samples, run_state, viewer, ok = collect_guided_ping_samples(
        sock,
        anchor_xy=anchor_xy,
        run_state=run_state,
        viewer=viewer,
        telemetry_callback=telemetry_callback,
        path_callback=path_callback,
        debug_logger=debug_logger,
        debug_prefix=round_config.debug_prefix,
    )
    if not ok or run_state.aborted:
        return (None, run_state, viewer, False)

    est_x_m, est_y_m = trilaterate((samples[0], samples[1], samples[2]))
    print(f"{round_config.estimate_label}: ({est_x_m:.3f}, {est_y_m:.3f}) m")
    goal_x, goal_y = raw_world_m_to_local_cm(est_x_m, est_y_m)

    if not hold_with_ui_updates(
        sock,
        viewer=viewer,
        planner=run_state.planner,
        goal_xy=(goal_x, goal_y),
        obstacle_total=run_state.obstacle_total,
        start_time=run_state.start_time,
        total_traveled_cm=run_state.total_traveled_cm,
        duration_s=0.5,
        status=round_config.prepare_status,
        telemetry_callback=telemetry_callback,
        debug_logger=debug_logger,
        debug_mode=round_config.pre_drive_hold_debug_mode,
    ):
        return (None, run_state, viewer, False)

    run_state = drive_to_goal_locate(
        sock,
        final_goal_xy=(goal_x, goal_y),
        goal_label=f"{est_x_m:.3f}, {est_y_m:.3f}",
        viewer=viewer,
        recorded_obstacle_points=run_state.recorded_obstacle_points,
        obstacle_total=run_state.obstacle_total,
        start_time=run_state.start_time,
        step_idx=run_state.step_idx,
        total_traveled_cm=run_state.total_traveled_cm,
        goals_reached=0,
        goal_reached_cm=FINAL_ESTIMATE_GOAL_REACHED_CM,
        telemetry_callback=telemetry_callback,
        path_callback=path_callback,
        debug_logger=debug_logger,
        debug_mode=round_config.final_drive_debug_mode,
    )
    viewer = run_state.viewer
    if run_state.aborted:
        return (None, run_state, viewer, False)

    print(round_config.arrival_message)
    return ((est_x_m, est_y_m), run_state, viewer, True)


def run_ltv_trilateration_search(
    sock,
    *,
    run_state,
    anchor_xy: tuple[float, float],
    viewer,
    telemetry_callback=None,
    path_callback=None,
    debug_logger: FrontendTimingLogger | None = None,
    ping_budget: int | None = None,
    hold_verify_debug_mode: str = "dumblocate_hold_verify_estimate",
) -> tuple[object, MapWindow | None, bool, int | None, bool]:
    current_anchor_xy = anchor_xy
    ltv_found = False
    remaining_ping_budget = ping_budget
    completed = True

    for round_config in TRILATERATION_ROUNDS:
        if remaining_ping_budget is not None and remaining_ping_budget <= 0:
            break

        estimate_xy_m, run_state, viewer, ok = run_trilateration_round(
            sock,
            round_config=round_config,
            anchor_xy=current_anchor_xy,
            run_state=run_state,
            viewer=viewer,
            telemetry_callback=telemetry_callback,
            path_callback=path_callback,
            debug_logger=debug_logger,
        )
        if remaining_ping_budget is not None:
            remaining_ping_budget = max(0, remaining_ping_budget - 3)
        if not ok or run_state.aborted or estimate_xy_m is None:
            completed = False
            break

        final_estimate_ping, ok = stop_then_try_sample_ping(
            sock,
            viewer=viewer,
            run_state=run_state,
            status="Stopping for estimate ping...",
            telemetry_callback=telemetry_callback,
            debug_logger=debug_logger,
            debug_mode=hold_verify_debug_mode,
        )
        if remaining_ping_budget is not None:
            remaining_ping_budget = max(0, remaining_ping_budget - 1)
        if not ok:
            completed = False
            break
        if final_estimate_ping is None:
            print(
                f"Ping at round {round_config.round_index} estimate is still out of range "
                "(distance > 500)."
            )
            if round_config.round_index == len(TRILATERATION_ROUNDS):
                print("Estimate ping is still out of range after the final trilateration round.")
                break
            print(
                f"Running trilateration round {round_config.round_index + 1} "
                "from the current estimate."
            )
            current_anchor_xy = raw_world_m_to_local_cm(*estimate_xy_m)
            continue

        print(
            f"Ping at round {round_config.round_index} estimate: "
            f"{final_estimate_ping.ping_value:.3f} "
            f"(strong-enough threshold {SECOND_TRILOCATION_STRONG_PING_THRESHOLD:.3f})"
        )
        if final_estimate_ping.ping_value >= SECOND_TRILOCATION_STRONG_PING_THRESHOLD:
            ltv_found = True
            if round_config.round_index > 1:
                print(
                    f"Round {round_config.round_index} estimate ping is strong enough. "
                    "Stopping additional trilateration rounds."
                )
            else:
                print("Estimate ping is strong enough. Skipping additional trilateration rounds.")
            break

        if round_config.round_index == len(TRILATERATION_ROUNDS):
            print("Estimate ping is still too weak after the final trilateration round.")
            break

        print(
            f"Estimate ping is still too weak. Running trilateration round "
            f"{round_config.round_index + 1}."
        )
        current_anchor_xy = raw_world_m_to_local_cm(*estimate_xy_m)

    return run_state, viewer, ltv_found, remaining_ping_budget, completed


def main() -> None:
    configure_remote_server(REMOTE_SERVER, REMOTE_SERVER_URL)
    sock = open_rover_socket()
    viewer: MapWindow | None = None
    debug_logger: FrontendTimingLogger | None = None
    metrics_logger: LocateMetricsLogger | None = None
    ping_sampler: PingStrengthSampler | None = None
    run_start_wall = time.time()
    run_completed = False
    print(f"Dumblocate start: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(run_start_wall))}")
    try:
        debug_logger = FrontendTimingLogger("dumblocate")
        if ENABLE_METRICS_LOGGING:
            metrics_logger = LocateMetricsLogger()
            ping_sampler = PingStrengthSampler(PING_LOG_INTERVAL_SEC)
        if not wait_for_dust(sock, timeout_seconds=20.0, poll_seconds=0.5):
            raise RuntimeError("DUST is not connected to TSS.")
        set_lights(sock, True)

        def log_metrics(*, phase: str, raw_telemetry: dict, rover_xyzh: tuple[float, float, float, float], goal_xy: tuple[float, float], goal_distance_cm: float) -> None:
            if metrics_logger is None or ping_sampler is None:
                return
            ping_strength, sampled_now = ping_sampler.sample(sock)
            if not sampled_now:
                return
            rover_x_m = float(raw_telemetry.get("rover_pos_x", 0.0))
            rover_y_m = float(raw_telemetry.get("rover_pos_y", 0.0))
            rover_z_m = float(raw_telemetry.get("rover_pos_z", 0.0))
            metrics_logger.log(
                phase=phase,
                rover_x_m=rover_x_m,
                rover_y_m=rover_y_m,
                rover_z_m=rover_z_m,
                ping_strength=ping_strength,
                goal_dist_cm=goal_distance_cm,
            )

        run_state, goal_xy, _last_known_xy_m = drive_to_last_known_ltv(
            sock,
            viewer=viewer,
            recorded_obstacle_points=[],
            obstacle_total=0,
            start_time=None,
            step_idx=0,
            total_traveled_cm=0.0,
            goals_reached=0,
            goal_reached_cm=LAST_KNOWN_GOAL_REACHED_CM,
            telemetry_callback=log_metrics if ENABLE_METRICS_LOGGING else None,
            debug_logger=debug_logger,
            debug_mode="dumblocate_drive_last_known",
        )
        viewer = run_state.viewer
        if run_state.aborted:
            return

        if STOP_AT_LAST_KNOWN_ONLY:
            print("Reached last known LTV location. Stopping here because STOP_AT_LAST_KNOWN_ONLY is enabled.")
            return

        last_known_remaining_cm = math.hypot(
            goal_xy[0] - run_state.pose_xyzh[0],
            goal_xy[1] - run_state.pose_xyzh[1],
        )
        print("Arrived near last known location.")
        print(f"Distance from last known at first ping: {last_known_remaining_cm:.1f} cm")
        run_state, viewer, _ltv_found, _remaining_ping_budget, search_completed = run_ltv_trilateration_search(
            sock,
            run_state=run_state,
            anchor_xy=goal_xy,
            viewer=viewer,
            telemetry_callback=log_metrics if ENABLE_METRICS_LOGGING else None,
            debug_logger=debug_logger,
            hold_verify_debug_mode="dumblocate_hold_verify_estimate",
        )
        if not search_completed or run_state.aborted:
            return
        run_completed = True

    except KeyboardInterrupt:
        pass
    finally:
        run_end_wall = time.time()
        elapsed_sec = run_end_wall - run_start_wall
        print(f"Dumblocate end: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(run_end_wall))}")
        print(
            f"Dumblocate elapsed: {elapsed_sec:.1f}s "
            f"({elapsed_sec / 60.0:.2f} min){' [completed]' if run_completed else ' [stopped early]'}"
        )
        stop_rover(sock)
       
        close_rover_socket(sock)
        if viewer is not None:
            viewer.close()
        if debug_logger is not None:
            debug_logger.close()
        if metrics_logger is not None:
            metrics_logger.close()


if __name__ == "__main__":
    main()

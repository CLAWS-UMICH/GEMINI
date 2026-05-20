from __future__ import annotations

import math
import time
from pathlib import Path
from math import ceil
from typing import TextIO

import numpy as np

from model import inferencer_backend, ingest_lidar, reset_history
from planner import (
    CELL_LOW_CLEARANCE_OBSTACLE,
    CELL_OBSTACLE,
    OccupancyPlanner,
    PlannerConfig,
)
from rover_control import (
    close_rover_socket,
    fetch_rover_telemetry,
    open_rover_socket,
    set_brakes,
    set_steering,
    set_throttle,
    wait_for_dust,
)

pygame = None


def require_pygame():
    global pygame
    if pygame is None:
        try:
            import pygame as pygame_module
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "pygame is required for the map window. Install with: pip install pygame"
            ) from exc
        pygame = pygame_module
    return pygame


TARGET_DX_CM = -4000
TARGET_DY_CM = -4000

CONTROL_PERIOD_SEC = 0.20
PREPATH_STRAIGHT_SECONDS = 0
PREPATH_STRAIGHT_THROTTLE = 100.0
PREPATH_MOMENTUM_BRAKE_SECONDS = 1.0
GOAL_REACHED_CM = 200.0
PATH_TARGET_LOOKAHEAD_CM = 500.0
STEP_LOGGING = False
LIDAR_FILE_LOGGING = False
DEBUG_TEXT_LOGGING = True

CRUISE_THROTTLE = 50
TURN_THROTTLE = 10.0
HEADING_ALIGN_DEG = 8.0
FULL_STEER_ERROR_DEG = 35.0
THROTTLE_STEERING_EXPONENT = 2.0
FORWARD_DRIVE_PULSE_SEC = 2.0
FORWARD_BRAKE_PULSE_SEC = 1.0

LIDAR_MAX_RANGE_CM = 1000.0
REPLAN_MIN_INTERVAL_SEC = 0.50
# rover_pos_* telemetry arrives in meter-scale world units, while the lidar layout,
# planner, and renderer are all defined in centimeters.
POSE_UNITS_TO_CM = 100.0
# Recenter the telemetry pose into the model's near-origin frame.
POSE_OFFSET_X_CM = -566700.0
POSE_OFFSET_Y_CM = -1009190.039
POSE_OFFSET_Z_CM = 144000.006
# Only map nearby hazards into occupancy; long-range sparse lidar points were polluting the goal area.
LOCAL_OBSTACLE_MARK_RADIUS_CM = 1000.0
MIN_OBSTACLE_MARK_DISTANCE_CM = 15.0
OBSTACLE_HITS_REQUIRED_PER_CHUNK = 1

# Space hub footprint. Static obstacle marked on every planner instance.
# Rover spawns just south of this rectangle and must never plan through it.
SPACE_HUB_RECT_CM: tuple[float, float, float, float] = (
    -5670.0,  # x_min
    -5660.0,  # x_max
    -10045.0, # y_min
    -10025.0, # y_max
)
ROVER_UNDERBODY_CLEARANCE_CM = 110.0
LIDAR_OBSTACLE_EVIDENCE_DELTA = 1.0
LIDAR_CLEAR_EVIDENCE_DELTA = -0.55
PATH_EVIDENCE_COST_SCALE = 2
PATH_CLEARANCE_COST_SCALE = 0.65
PATH_EVIDENCE_MIN_VALUE = -3.0
PATH_EVIDENCE_MAX_VALUE = 8.0
LIDAR_OBSTACLE_PROXIMITY_GAIN = 1.5
LIDAR_OBSTACLE_EVIDENCE_BLOCK_SIZE_CM = 280.0
LIDAR_OBSTACLE_EVIDENCE_EDGE_GAIN = 0.55
LIDAR_CLEARANCE_COST_DELTA = 0.65
PATH_CLEARANCE_MIN_VALUE = 0.0
PATH_CLEARANCE_MAX_VALUE = 12.0
# If True, low-clearance hits stay on the map but render in a different color.
# If False, low-clearance hits are ignored for obstacle mapping.
RENDER_LOW_CLEARANCE_HITS_IN_ALT_COLOR = True

WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 900
MAP_MARGIN = 24
PANEL_WIDTH = 320
BG_COLOR = (16, 18, 24)
MAP_BG_COLOR = (26, 31, 38)
OBSTACLE_COLOR = (220, 77, 77)
LOW_CLEARANCE_OBSTACLE_COLOR = (214, 168, 72)
PATH_COLOR = (110, 170, 255)
ROVER_COLOR = (255, 220, 80)
GOAL_COLOR = (80, 220, 120)
TARGET_COLOR = (255, 170, 70)
TEXT_COLOR = (235, 239, 245)
LIDAR_HIT_COLOR = (255, 60, 60)
LIDAR_MAP_HIT_NEAR_COLOR = (235, 245, 255)
LIDAR_MAP_HIT_FAR_COLOR = (35, 90, 210)
EVIDENCE_HEAT_POSITIVE_COLOR = (255, 96, 64)
EVIDENCE_HEAT_NEGATIVE_COLOR = (70, 150, 255)
CLEARANCE_HEAT_COLOR = (255, 190, 70)
EVIDENCE_HEAT_MIN_ALPHA = 32
EVIDENCE_HEAT_MAX_ALPHA = 190
# Viewer footprint. The earlier rectangle was doubled because the prior footprint extents
# were treated as full dimensions instead of half-extents.
ROVER_BODY_LENGTH_CM = 345.0
ROVER_BODY_WIDTH_CM = 260.0
# Temporary conservative inflation while LiDAR-to-body clearance is still being tuned.
ROVER_FOOTPRINT_LENGTH_BUFFER_CM = 80.0
ROVER_FOOTPRINT_WIDTH_BUFFER_CM = 60.0
ROVER_HALF_LENGTH_CM = (ROVER_BODY_LENGTH_CM + ROVER_FOOTPRINT_LENGTH_BUFFER_CM) * 0.5
ROVER_HALF_WIDTH_CM = (ROVER_BODY_WIDTH_CM + ROVER_FOOTPRINT_WIDTH_BUFFER_CM) * 0.5
ROVER_OUTLINE_COLOR = (25, 25, 25)
# NOTE: empirical debug runs indicate center-origin projection matches observed close-contact behavior better.
MAP_USE_SENSOR_ORIGIN = True
MAP_MIN_ZOOM = 1.0
MAP_MAX_ZOOM = 12.0
MAP_ZOOM_STEP = 1.2


GRID_CELL_SIZE_CM = 50.0
GRID_MARGIN_CM = 1200.0
OBSTACLE_PADDING_CELLS = 5
PATH_WAYPOINT_SPACING_CM = 10.0


# (sensor_local_x_cm, sensor_local_y_cm, sensor_yaw_deg, sensor_pitch_deg)
LIDAR_SENSOR_LAYOUT = [
    (250.0, 245.0, 30.0, 0.0),
    (325.0, 75.0, 20.0, -20.0),
    (325.0, 0.0, 0.0, 0.0),
    (325.0, -75.0, -20.0, -20.0),
    (250.0, -245.0, -30.0, 0.0),
    (325.0, 75.0, 0.0, -25.0),
    (325.0, -75.0, 0.0, -25.0),
    (40.0, 235.0, 90.0, -20.0),
    (40.0, -235.0, -90.0, -20.0),
    (-215.0, 270.0, 140.0, 0.0),
    (-320.0, 80.0, 180.0, 0.0),
    (-320.0, -50.0, 180.0, 0.0),
    (-215.0, -215.0, -140.0, 0.0),
    (325.0, 75.0, 20.0, -10.0),
    (325.0, -75.0, -20.0, -10.0),
    (250.0, 245.0, 15.0, 0.0),
    (250.0, -245.0, -15.0, 0.0),
]

LIDAR_SENSOR_LABELS = [
    "front_left_wheel_hub_yaw_p30",
    "front_left_frame_yaw_p20_pitch_n20",
    "front_center_frame_forward",
    "front_right_frame_yaw_n20_pitch_n20",
    "front_right_wheel_hub_yaw_n30",
    "front_left_frame_pitch_n25",
    "front_right_frame_pitch_n25",
    "left_mid_frame_left_pitch_n20",
    "right_mid_frame_right_pitch_n20",
    "rear_left_wheel_hub_back_yaw_p40",
    "rear_left_frame_backward",
    "rear_right_frame_backward",
    "rear_right_wheel_hub_back_yaw_n40",
    "front_left_frame_yaw_p20_pitch_n10",
    "front_right_frame_yaw_n20_pitch_n10",
    "front_left_wheel_hub_yaw_p15",
    "front_right_wheel_hub_yaw_n15",
]

# Human-readable pointing labels shown in the viewer key (index-aligned to sensors 0..16).
# Controls whether each lidar can contribute obstacle marks to the occupancy map.
# All sensors are still logged and still fed into the model regardless of these flags.
LIDAR_SENSOR_MAP_ENABLED = [
    True,   # 00 front_left_wheel_hub_yaw_p30
    False,  # 01 front_left_frame_yaw_p20_pitch_n20
    True,   # 02 front_center_frame_forward
    False,  # 03 front_right_frame_yaw_n20_pitch_n20
    True,   # 04 front_right_wheel_hub_yaw_n30
    False,  # 05 front_left_frame_pitch_n25
    False,  # 06 front_right_frame_pitch_n25
    False,  # 07 left_mid_frame_left_pitch_n20
    False,  # 08 right_mid_frame_right_pitch_n20
    True,   # 09 rear_left_wheel_hub_back_yaw_p40
    True,   # 10 rear_left_frame_backward
    True,   # 11 rear_right_frame_backward
    True,   # 12 rear_right_wheel_hub_back_yaw_n40
    True,   # 13 front_left_frame_yaw_p20_pitch_n10
    True,   # 14 front_right_frame_yaw_n20_pitch_n10
    True,   # 15 front_left_wheel_hub_yaw_p15
    True,   # 16 front_right_wheel_hub_yaw_n15
]
LIDAR_LOG_DIR = Path("runs")
DEBUG_LOG_ROOT = Path("runs")

if len(LIDAR_SENSOR_MAP_ENABLED) != len(LIDAR_SENSOR_LAYOUT):
    raise RuntimeError(
        "LIDAR_SENSOR_MAP_ENABLED must have one entry per lidar sensor "
        f"({len(LIDAR_SENSOR_LAYOUT)} expected, got {len(LIDAR_SENSOR_MAP_ENABLED)})."
    )


def default_lidar_chunk_sensor_groups(num_sensors: int) -> dict[str, list[int]]:
    if int(num_sensors) == 17:
        return {
            "front": [0, 1, 2, 3, 4, 5, 6, 13, 14, 15, 16],
            "left": [7],
            "right": [8],
            "rear": [9, 10, 11, 12],
        }
    chunks = np.array_split(np.arange(int(num_sensors), dtype=np.int64), 4)
    return {
        "front": [int(v) for v in chunks[0].tolist()],
        "left": [int(v) for v in chunks[1].tolist()],
        "right": [int(v) for v in chunks[2].tolist()],
        "rear": [int(v) for v in chunks[3].tolist()],
    }


LIDAR_CHUNK_SENSOR_GROUPS = default_lidar_chunk_sensor_groups(len(LIDAR_SENSOR_LAYOUT))
LIDAR_SENSOR_TO_CHUNK = {
    sensor_idx: chunk_name
    for chunk_name, sensor_ids in LIDAR_CHUNK_SENSOR_GROUPS.items()
    for sensor_idx in sensor_ids
}


def local_to_world_2d(
    base_x_cm: float,
    base_y_cm: float,
    heading_deg: float,
    local_x_cm: float,
    local_y_cm: float,
) -> tuple[float, float]:
    rad = math.radians(heading_deg)
    cos_h = math.cos(rad)
    sin_h = math.sin(rad)
    wx = base_x_cm + local_x_cm * cos_h - local_y_cm * sin_h
    wy = base_y_cm + local_x_cm * sin_h + local_y_cm * cos_h
    return (wx, wy)


def point_in_rover_bbox(
    rover_x_cm: float,
    rover_y_cm: float,
    rover_heading_deg: float,
    point_x_cm: float,
    point_y_cm: float,
) -> bool:
    rad = math.radians(rover_heading_deg)
    cos_h = math.cos(rad)
    sin_h = math.sin(rad)
    dx = point_x_cm - rover_x_cm
    dy = point_y_cm - rover_y_cm
    local_x = dx * cos_h + dy * sin_h
    local_y = -dx * sin_h + dy * cos_h
    return abs(local_x) <= ROVER_HALF_LENGTH_CM and abs(local_y) <= ROVER_HALF_WIDTH_CM


def lidar_map_hit_line_color(distance_cm: float) -> tuple[int, int, int]:
    if not math.isfinite(distance_cm):
        return LIDAR_MAP_HIT_FAR_COLOR
    t = max(0.0, min(1.0, distance_cm / max(1.0, LIDAR_MAX_RANGE_CM)))
    near_r, near_g, near_b = LIDAR_MAP_HIT_NEAR_COLOR
    far_r, far_g, far_b = LIDAR_MAP_HIT_FAR_COLOR
    return (
        int(near_r + (far_r - near_r) * t),
        int(near_g + (far_g - near_g) * t),
        int(near_b + (far_b - near_b) * t),
    )


def planner_evidence_heat_color(planner: OccupancyPlanner, evidence_value: float) -> tuple[int, int, int, int] | None:
    evidence = float(evidence_value)
    if abs(evidence) <= 1e-6:
        return None

    if evidence > 0.0:
        scale = max(float(planner.config.evidence_max_value), 1e-6)
        t = max(0.0, min(1.0, evidence / scale))
        r, g, b = EVIDENCE_HEAT_POSITIVE_COLOR
    else:
        scale = max(abs(float(planner.config.evidence_min_value)), 1e-6)
        t = max(0.0, min(1.0, abs(evidence) / scale))
        r, g, b = EVIDENCE_HEAT_NEGATIVE_COLOR

    alpha = int(EVIDENCE_HEAT_MIN_ALPHA + (EVIDENCE_HEAT_MAX_ALPHA - EVIDENCE_HEAT_MIN_ALPHA) * t)
    return (r, g, b, alpha)


def planner_clearance_heat_color(planner: OccupancyPlanner, clearance_value: float) -> tuple[int, int, int, int] | None:
    clearance = float(clearance_value)
    if clearance <= 1e-6:
        return None
    scale = max(float(planner.config.clearance_max_value), 1e-6)
    t = max(0.0, min(1.0, clearance / scale))
    r, g, b = CLEARANCE_HEAT_COLOR
    alpha = int(EVIDENCE_HEAT_MIN_ALPHA + (EVIDENCE_HEAT_MAX_ALPHA - EVIDENCE_HEAT_MIN_ALPHA) * t)
    return (r, g, b, alpha)


def apply_obstacle_evidence_kernel(
    planner: OccupancyPlanner,
    hit_world_xy_cm: tuple[float, float],
    hit_cell: tuple[int, int],
    hit_dist_from_rover_cm: float,
    evidence_updates: list[tuple[float, float, float]] | None = None,
    clearance_updates: list[tuple[float, float, float]] | None = None,
) -> tuple[bool, float, float]:
    base_delta = float(LIDAR_OBSTACLE_EVIDENCE_DELTA)
    local_radius = max(1.0, float(LOCAL_OBSTACLE_MARK_RADIUS_CM))
    proximity_t = max(0.0, min(1.0, 1.0 - (float(hit_dist_from_rover_cm) / local_radius)))
    proximity_scale = 1.0 + (proximity_t * float(LIDAR_OBSTACLE_PROXIMITY_GAIN))
    block_size_cm = max(float(planner.config.cell_size_cm), float(LIDAR_OBSTACLE_EVIDENCE_BLOCK_SIZE_CM))
    half_block_cm = block_size_cm * 0.5
    block_radius_cells = max(0, int(math.ceil(half_block_cm / max(1.0, float(planner.config.cell_size_cm)))))
    edge_gain = max(0.0, min(1.0, float(LIDAR_OBSTACLE_EVIDENCE_EDGE_GAIN)))
    any_changed = False
    hit_world_x_cm, hit_world_y_cm = hit_world_xy_cm

    for dy in range(-block_radius_cells, block_radius_cells + 1):
        for dx in range(-block_radius_cells, block_radius_cells + 1):
            cell = (hit_cell[0] + dx, hit_cell[1] + dy)
            if not planner.in_bounds(cell):
                continue
            cell_x_cm, cell_y_cm = planner.cell_to_world_center(cell)
            offset_x_cm = abs(cell_x_cm - hit_world_x_cm)
            offset_y_cm = abs(cell_y_cm - hit_world_y_cm)
            if offset_x_cm > half_block_cm or offset_y_cm > half_block_cm:
                continue
            norm_x = 0.0 if half_block_cm <= 1e-6 else (offset_x_cm / half_block_cm)
            norm_y = 0.0 if half_block_cm <= 1e-6 else (offset_y_cm / half_block_cm)
            edge_t = max(norm_x, norm_y)
            cell_gain = 1.0 - (1.0 - edge_gain) * edge_t
            clearance_delta = float(LIDAR_CLEARANCE_COST_DELTA) * proximity_scale * cell_gain
            if clearance_delta > 0.0:
                planner.add_clearance_cell(cell, clearance_delta)
                if clearance_updates is not None:
                    clearance_updates.append((cell_x_cm, cell_y_cm, clearance_delta))
            if dx != 0 or dy != 0:
                continue
            delta = base_delta * proximity_scale
            if delta <= 0.0:
                continue
            changed = planner.add_evidence_cell(cell, delta)
            any_changed = any_changed or changed
            if evidence_updates is not None:
                evidence_updates.append((cell_x_cm, cell_y_cm, delta))
    return any_changed, planner.cell_evidence(hit_cell), planner.cell_clearance(hit_cell)


def heading_basis_matrix(heading_deg: float) -> np.ndarray:
    rad = math.radians(heading_deg)
    cos_h = math.cos(rad)
    sin_h = math.sin(rad)
    return np.asarray(
        [
            [cos_h, -sin_h, 0.0],
            [sin_h, cos_h, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float32,
    )


class DebugRunWriter:
    def __init__(self) -> None:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        self.run_dir = DEBUG_LOG_ROOT / f"debug_{timestamp}"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = (self.run_dir / "config.txt").open("w", encoding="utf-8")
        self.steps_file = (self.run_dir / "steps.txt").open("w", encoding="utf-8")
        self.replans_file = (self.run_dir / "replans.txt").open("w", encoding="utf-8")
        self.lidar_file = (self.run_dir / "lidar_points.txt").open("w", encoding="utf-8")
        self.zero_file = (self.run_dir / "zero_hits.txt").open("w", encoding="utf-8")
        self.steps_file.write(
            "step_idx\telapsed_s\tstatus\trover_x_cm\trover_y_cm\trover_z_cm\trover_heading_deg\t"
            "goal_dist_cm\tnext_waypoint_dist_cm\tnext_waypoint_avg_cm\t"
            "target_x_cm\ttarget_y_cm\twaypoint_idx\tpath_len\tthrottle_cmd\tsteering_cmd\t"
            "telemetry_throttle\ttelemetry_steering\ttelemetry_speed\ttelemetry_brakes\ttelemetry_distance_traveled\t"
            "new_obstacles\tobstacle_total\trover_cell_x\trover_cell_y\ttarget_cell_x\ttarget_cell_y\t"
            "viewer_scale_x\tviewer_scale_y\tclosest_usable_lidar_cm\t"
            "closest_raw_positive_lidar_cm\tzero_lidar_sensor_count\tusable_lidar_sensor_count\n"
        )
        self.replans_file.write(
            "step_idx\telapsed_s\tattempted\traw_path_points\tfollow_path_points\tstatus\n"
        )
        self.lidar_file.write(
            "step_idx\telapsed_s\tsensor_idx\tsensor_label\tsensor_enabled\traw_cm\traw_is_zero\tvalid_range_gt0\tvalid_range_ge0\tmask_hit\tpitch_scale\t"
            "planar_hit_cm\thit_world_z_cm\tlow_clearance_hit\tchunk_name\tchunk_hit_count\tchunk_threshold_met\thit_dist_from_rover_cm\twithin_local_radius\t"
            "usable_for_mark\tplaced\tusable_reason\tmap_origin\t"
            "sensor_local_x_cm\tsensor_local_y_cm\t"
            "sensor_yaw_deg\tsensor_pitch_deg\tsensor_world_x_cm\tsensor_world_y_cm\t"
            "sensor_cell_x\tsensor_cell_y\thit_world_x_cm\thit_world_y_cm\thit_cell_x\thit_cell_y\t"
            "center_hit_world_x_cm\tcenter_hit_world_y_cm\tcenter_hit_cell_x\tcenter_hit_cell_y\n"
        )
        self.zero_file.write(
            "step_idx\telapsed_s\tsensor_idx\tsensor_label\traw_cm\tmask_hit\tsensor_world_x_cm\tsensor_world_y_cm\t"
            "sensor_cell_x\tsensor_cell_y\trover_x_cm\trover_y_cm\trover_heading_deg\n"
        )

    @staticmethod
    def _fmt(value: float | int | bool | str) -> str:
        if isinstance(value, bool):
            return "1" if value else "0"
        if isinstance(value, int):
            return str(value)
        if isinstance(value, float):
            if math.isnan(value):
                return "nan"
            if math.isinf(value):
                return "inf" if value > 0 else "-inf"
            return f"{value:.3f}"
        return str(value)

    def write_config(
        self,
        planner: OccupancyPlanner,
        start_xy: tuple[float, float],
        goal_xy: tuple[float, float],
        model_backend: str,
    ) -> None:
        cfg = planner.config
        self.config_file.write(f"created_utc={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n")
        self.config_file.write(f"pose_units_to_cm={POSE_UNITS_TO_CM}\n")
        self.config_file.write("heading_frame=math_deg_from_dust_compass_90_minus_raw\n")
        self.config_file.write(f"lidar_max_range_cm={LIDAR_MAX_RANGE_CM}\n")
        self.config_file.write(f"local_obstacle_mark_radius_cm={LOCAL_OBSTACLE_MARK_RADIUS_CM}\n")
        self.config_file.write(f"min_obstacle_mark_distance_cm={MIN_OBSTACLE_MARK_DISTANCE_CM}\n")
        self.config_file.write(f"obstacle_hits_required_per_chunk={OBSTACLE_HITS_REQUIRED_PER_CHUNK}\n")
        self.config_file.write(f"rover_underbody_clearance_cm={ROVER_UNDERBODY_CLEARANCE_CM}\n")
        self.config_file.write(
            f"render_low_clearance_hits_in_alt_color={int(RENDER_LOW_CLEARANCE_HITS_IN_ALT_COLOR)}\n"
        )
        self.config_file.write(f"path_target_lookahead_cm={PATH_TARGET_LOOKAHEAD_CM}\n")
        self.config_file.write(f"path_waypoint_spacing_cm={PATH_WAYPOINT_SPACING_CM}\n")
        self.config_file.write(f"forward_drive_pulse_sec={FORWARD_DRIVE_PULSE_SEC}\n")
        self.config_file.write(f"forward_brake_pulse_sec={FORWARD_BRAKE_PULSE_SEC}\n")
        self.config_file.write(f"map_use_sensor_origin={int(MAP_USE_SENSOR_ORIGIN)}\n")
        self.config_file.write(f"model_backend={model_backend}\n")
        self.config_file.write(f"grid_cell_size_cm={cfg.cell_size_cm}\n")
        self.config_file.write(f"obstacle_padding_cells={cfg.obstacle_padding_cells}\n")
        self.config_file.write(f"grid_origin_x_cm={planner.origin_x_cm}\n")
        self.config_file.write(f"grid_origin_y_cm={planner.origin_y_cm}\n")
        self.config_file.write(f"grid_width_cells={planner.width_cells}\n")
        self.config_file.write(f"grid_height_cells={planner.height_cells}\n")
        self.config_file.write(f"start_x_cm={start_xy[0]:.3f}\n")
        self.config_file.write(f"start_y_cm={start_xy[1]:.3f}\n")
        self.config_file.write(f"goal_x_cm={goal_xy[0]:.3f}\n")
        self.config_file.write(f"goal_y_cm={goal_xy[1]:.3f}\n")
        for chunk_name, sensor_ids in LIDAR_CHUNK_SENSOR_GROUPS.items():
            sensor_id_text = ",".join(str(sensor_idx) for sensor_idx in sensor_ids)
            self.config_file.write(f"lidar_chunk_{chunk_name}={sensor_id_text}\n")
        sensor_enabled_text = ",".join("1" if enabled else "0" for enabled in LIDAR_SENSOR_MAP_ENABLED)
        self.config_file.write(f"lidar_sensor_map_enabled={sensor_enabled_text}\n")
        self.config_file.write(
            "sensor_layout_idx\tsensor_enabled\tsensor_x_cm\tsensor_y_cm\tsensor_yaw_deg\tsensor_pitch_deg\n"
        )
        for idx, (sx, sy, syaw, spitch) in enumerate(LIDAR_SENSOR_LAYOUT):
            enabled = int(LIDAR_SENSOR_MAP_ENABLED[idx])
            self.config_file.write(f"{idx}\t{enabled}\t{sx:.3f}\t{sy:.3f}\t{syaw:.3f}\t{spitch:.3f}\n")
        self.config_file.flush()

    def log_step(self, **values: float | int | bool | str) -> None:
        ordered_keys = [
            "step_idx",
            "elapsed_s",
            "status",
            "rover_x_cm",
            "rover_y_cm",
            "rover_z_cm",
            "rover_heading_deg",
            "goal_dist_cm",
            "next_waypoint_dist_cm",
            "next_waypoint_avg_cm",
            "target_x_cm",
            "target_y_cm",
            "waypoint_idx",
            "path_len",
            "throttle_cmd",
            "steering_cmd",
            "telemetry_throttle",
            "telemetry_steering",
            "telemetry_speed",
            "telemetry_brakes",
            "telemetry_distance_traveled",
            "new_obstacles",
            "obstacle_total",
            "rover_cell_x",
            "rover_cell_y",
            "target_cell_x",
            "target_cell_y",
            "viewer_scale_x",
            "viewer_scale_y",
            "closest_usable_lidar_cm",
            "closest_raw_positive_lidar_cm",
            "zero_lidar_sensor_count",
            "usable_lidar_sensor_count",
        ]
        row = "\t".join(self._fmt(values.get(k, "nan")) for k in ordered_keys)
        self.steps_file.write(f"{row}\n")
        self.steps_file.flush()

    def log_replan(
        self,
        step_idx: int,
        elapsed_s: float,
        attempted: bool,
        raw_path_points: int,
        follow_path_points: int,
        status: str,
    ) -> None:
        self.replans_file.write(
            f"{step_idx}\t{elapsed_s:.3f}\t{int(attempted)}\t{raw_path_points}\t{follow_path_points}\t{status}\n"
        )
        self.replans_file.flush()

    def log_lidar_rows(self, step_idx: int, elapsed_s: float, rows: list[dict[str, float | int | bool | str]]) -> None:
        for row in rows:
            self.lidar_file.write(
                "\t".join(
                    [
                        self._fmt(step_idx),
                        self._fmt(elapsed_s),
                        self._fmt(row["sensor_idx"]),
                        self._fmt(row["sensor_label"]),
                        self._fmt(row["sensor_enabled"]),
                        self._fmt(row["raw_cm"]),
                        self._fmt(row["raw_is_zero"]),
                        self._fmt(row["valid_range_gt0"]),
                        self._fmt(row["valid_range_ge0"]),
                        self._fmt(row["mask_hit"]),
                        self._fmt(row["pitch_scale"]),
                        self._fmt(row["planar_hit_cm"]),
                        self._fmt(row["hit_world_z_cm"]),
                        self._fmt(row["low_clearance_hit"]),
                        self._fmt(row["chunk_name"]),
                        self._fmt(row["chunk_hit_count"]),
                        self._fmt(row["chunk_threshold_met"]),
                        self._fmt(row["hit_dist_from_rover_cm"]),
                        self._fmt(row["within_local_radius"]),
                        self._fmt(row["usable_for_mark"]),
                        self._fmt(row["placed"]),
                        self._fmt(row["usable_reason"]),
                        self._fmt(row["map_origin"]),
                        self._fmt(row["sensor_local_x_cm"]),
                        self._fmt(row["sensor_local_y_cm"]),
                        self._fmt(row["sensor_yaw_deg"]),
                        self._fmt(row["sensor_pitch_deg"]),
                        self._fmt(row["sensor_world_x_cm"]),
                        self._fmt(row["sensor_world_y_cm"]),
                        self._fmt(row["sensor_cell_x"]),
                        self._fmt(row["sensor_cell_y"]),
                        self._fmt(row["hit_world_x_cm"]),
                        self._fmt(row["hit_world_y_cm"]),
                        self._fmt(row["hit_cell_x"]),
                        self._fmt(row["hit_cell_y"]),
                        self._fmt(row["center_hit_world_x_cm"]),
                        self._fmt(row["center_hit_world_y_cm"]),
                        self._fmt(row["center_hit_cell_x"]),
                        self._fmt(row["center_hit_cell_y"]),
                    ]
                )
                + "\n"
            )
        self.lidar_file.flush()

    def log_zero_rows(self, step_idx: int, elapsed_s: float, rows: list[dict[str, float | int | bool | str]]) -> None:
        for row in rows:
            if float(row["raw_cm"]) != 0.0:
                continue
            self.zero_file.write(
                "\t".join(
                    [
                        self._fmt(step_idx),
                        self._fmt(elapsed_s),
                        self._fmt(row["sensor_idx"]),
                        self._fmt(row["sensor_label"]),
                        self._fmt(row["raw_cm"]),
                        self._fmt(row["mask_hit"]),
                        self._fmt(row["sensor_world_x_cm"]),
                        self._fmt(row["sensor_world_y_cm"]),
                        self._fmt(row["sensor_cell_x"]),
                        self._fmt(row["sensor_cell_y"]),
                        self._fmt(row["rover_x_cm"]),
                        self._fmt(row["rover_y_cm"]),
                        self._fmt(row["rover_heading_deg"]),
                    ]
                )
                + "\n"
            )
        self.zero_file.flush()

    def close(self) -> None:
        self.config_file.close()
        self.steps_file.close()
        self.replans_file.close()
        self.lidar_file.close()
        self.zero_file.close()


class MapWindow:
    def __init__(self, planner: OccupancyPlanner) -> None:
        require_pygame()
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Rover Planner")
        self.font = pygame.font.SysFont("Consolas", 20)
        self.small_font = pygame.font.SysFont("Consolas", 16)
        self.tiny_font = pygame.font.SysFont("Consolas", 13)
        self.map_rect = pygame.Rect(
            MAP_MARGIN,
            MAP_MARGIN,
            WINDOW_WIDTH - PANEL_WIDTH - MAP_MARGIN * 2,
            WINDOW_HEIGHT - MAP_MARGIN * 2,
        )
        self.panel_rect = pygame.Rect(
            self.map_rect.right + MAP_MARGIN,
            MAP_MARGIN,
            PANEL_WIDTH - MAP_MARGIN * 2,
            WINDOW_HEIGHT - MAP_MARGIN * 2,
        )
        self.zoom = 1.0
        self.view_center_x_cm = planner.origin_x_cm + planner.width_cells * planner.config.cell_size_cm * 0.5
        self.view_center_y_cm = planner.origin_y_cm + planner.height_cells * planner.config.cell_size_cm * 0.5
        self.dragging_map = False
        self._update_scale(planner)

    def _update_scale(self, planner: OccupancyPlanner) -> None:
        full_width_cm = max(1.0, planner.width_cells * planner.config.cell_size_cm)
        full_height_cm = max(1.0, planner.height_cells * planner.config.cell_size_cm)
        self.base_scale_x = self.map_rect.width / full_width_cm
        self.base_scale_y = self.map_rect.height / full_height_cm
        self.scale_x = self.base_scale_x * self.zoom * planner.config.cell_size_cm
        self.scale_y = self.base_scale_y * self.zoom * planner.config.cell_size_cm
        self.view_width_cm = full_width_cm / self.zoom
        self.view_height_cm = full_height_cm / self.zoom
        self._clamp_view_center(planner)

    def close(self) -> None:
        pygame.quit()

    def _clamp_view_center(self, planner: OccupancyPlanner) -> None:
        full_width_cm = max(1.0, planner.width_cells * planner.config.cell_size_cm)
        full_height_cm = max(1.0, planner.height_cells * planner.config.cell_size_cm)
        half_view_w = min(full_width_cm * 0.5, self.view_width_cm * 0.5)
        half_view_h = min(full_height_cm * 0.5, self.view_height_cm * 0.5)
        min_center_x = planner.origin_x_cm + half_view_w
        max_center_x = planner.origin_x_cm + full_width_cm - half_view_w
        min_center_y = planner.origin_y_cm + half_view_h
        max_center_y = planner.origin_y_cm + full_height_cm - half_view_h
        self.view_center_x_cm = min(max(self.view_center_x_cm, min_center_x), max_center_x)
        self.view_center_y_cm = min(max(self.view_center_y_cm, min_center_y), max_center_y)

    def _screen_to_world(self, planner: OccupancyPlanner, sx: int, sy: int) -> tuple[float, float]:
        left_world = self.view_center_x_cm - self.view_width_cm * 0.5
        bottom_world = self.view_center_y_cm - self.view_height_cm * 0.5
        fx = (sx - self.map_rect.left) / max(1.0, float(self.map_rect.width))
        fy = (self.map_rect.bottom - sy) / max(1.0, float(self.map_rect.height))
        wx = left_world + fx * self.view_width_cm
        wy = bottom_world + fy * self.view_height_cm
        return (wx, wy)

    def _zoom_at_screen_pos(self, planner: OccupancyPlanner, zoom_factor: float, screen_pos: tuple[int, int]) -> None:
        if not self.map_rect.collidepoint(screen_pos):
            return
        before_x, before_y = self._screen_to_world(planner, screen_pos[0], screen_pos[1])
        self.zoom = min(MAP_MAX_ZOOM, max(MAP_MIN_ZOOM, self.zoom * zoom_factor))
        self._update_scale(planner)
        after_x, after_y = self._screen_to_world(planner, screen_pos[0], screen_pos[1])
        self.view_center_x_cm += before_x - after_x
        self.view_center_y_cm += before_y - after_y
        self._clamp_view_center(planner)
        self._update_scale(planner)

    def _pan_by_screen_delta(self, planner: OccupancyPlanner, dx_px: int, dy_px: int) -> None:
        if dx_px == 0 and dy_px == 0:
            return
        px_per_cm_x = max(self.base_scale_x * self.zoom, 1e-6)
        px_per_cm_y = max(self.base_scale_y * self.zoom, 1e-6)
        self.view_center_x_cm -= dx_px / px_per_cm_x
        self.view_center_y_cm += dy_px / px_per_cm_y
        self._clamp_view_center(planner)
        self._update_scale(planner)

    def _world_to_screen(self, planner: OccupancyPlanner, x_cm: float, y_cm: float) -> tuple[int, int]:
        left_world = self.view_center_x_cm - self.view_width_cm * 0.5
        bottom_world = self.view_center_y_cm - self.view_height_cm * 0.5
        fx = (x_cm - left_world) / max(1.0, self.view_width_cm)
        fy = (y_cm - bottom_world) / max(1.0, self.view_height_cm)
        sx = int(self.map_rect.left + fx * self.map_rect.width)
        sy = int(self.map_rect.bottom - fy * self.map_rect.height)
        return (sx, sy)

    def _draw_rover(self, planner: OccupancyPlanner, rover_xy: tuple[float, float], heading_deg: float) -> None:
        footprint_local = [
            (ROVER_HALF_LENGTH_CM, ROVER_HALF_WIDTH_CM),
            (ROVER_HALF_LENGTH_CM, -ROVER_HALF_WIDTH_CM),
            (-ROVER_HALF_LENGTH_CM, -ROVER_HALF_WIDTH_CM),
            (-ROVER_HALF_LENGTH_CM, ROVER_HALF_WIDTH_CM),
        ]
        footprint_screen = []
        for lx, ly in footprint_local:
            wx, wy = local_to_world_2d(rover_xy[0], rover_xy[1], heading_deg, lx, ly)
            footprint_screen.append(self._world_to_screen(planner, wx, wy))
        pygame.draw.polygon(self.screen, ROVER_COLOR, footprint_screen)
        pygame.draw.polygon(self.screen, ROVER_OUTLINE_COLOR, footprint_screen, width=2)
        cx, cy = self._world_to_screen(planner, rover_xy[0], rover_xy[1])
        heading_rad = math.radians(heading_deg)
        nose_len_px = max(10, int(ROVER_HALF_LENGTH_CM * self.base_scale_x * self.zoom * 0.85))
        nose_end = (cx + int(math.cos(heading_rad) * nose_len_px), cy - int(math.sin(heading_rad) * nose_len_px))
        pygame.draw.line(self.screen, ROVER_OUTLINE_COLOR, (cx, cy), nose_end, width=3)
        pygame.draw.circle(self.screen, ROVER_OUTLINE_COLOR, (cx, cy), 3)

    def draw(
        self,
        planner: OccupancyPlanner,
        rover_xy: tuple[float, float],
        heading_deg: float,
        goal_xy: tuple[float, float],
        target_xy: tuple[float, float],
        path_world: list[tuple[float, float]],
        status: str,
        goal_distance_cm: float,
        throttle_cmd: float,
        steering_cmd: float,
        waypoint_idx: int,
        waypoint_distance_cm: float,
        waypoint_distance_avg_cm: float,
        obstacle_total: int,
        lidar_cm: np.ndarray,
        lidar_debug_rows: list[dict[str, float | int | bool | str]] | None = None,
    ) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return False
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.map_rect.collidepoint(event.pos):
                self.dragging_map = True
            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self.dragging_map = False
            if event.type == pygame.MOUSEMOTION and self.dragging_map:
                self._pan_by_screen_delta(planner, event.rel[0], event.rel[1])
            if event.type == pygame.MOUSEWHEEL:
                mouse_pos = pygame.mouse.get_pos()
                if event.y > 0:
                    self._zoom_at_screen_pos(planner, MAP_ZOOM_STEP ** event.y, mouse_pos)
                elif event.y < 0:
                    self._zoom_at_screen_pos(planner, MAP_ZOOM_STEP ** event.y, mouse_pos)
            if hasattr(pygame, "MULTIGESTURE") and event.type == pygame.MULTIGESTURE:
                if abs(getattr(event, "pinched", 0.0)) > 1e-4:
                    gesture_pos = (
                        int(float(getattr(event, "x", 0.5)) * WINDOW_WIDTH),
                        int(float(getattr(event, "y", 0.5)) * WINDOW_HEIGHT),
                    )
                    self._zoom_at_screen_pos(planner, MAP_ZOOM_STEP ** (event.pinched * 4.0), gesture_pos)

        self._update_scale(planner)
        self.screen.fill(BG_COLOR)
        pygame.draw.rect(self.screen, MAP_BG_COLOR, self.map_rect)
        pygame.draw.rect(self.screen, (65, 78, 96), self.map_rect, width=2)
        pygame.draw.rect(self.screen, (28, 34, 44), self.panel_rect)

        map_clip = self.screen.get_clip()
        self.screen.set_clip(self.map_rect)
        evidence_min_seen = 0.0
        evidence_max_seen = 0.0
        clearance_max_seen = 0.0
        cost_max_seen = 1.0
        for y in range(planner.height_cells):
            for x in range(planner.width_cells):
                clearance_value = float(planner.clearance_grid[y][x])
                clearance_color = planner_clearance_heat_color(planner, clearance_value)
                if clearance_color is not None:
                    clearance_max_seen = max(clearance_max_seen, clearance_value)
                    cost_max_seen = max(
                        cost_max_seen,
                        1.0 + clearance_value * float(planner.config.clearance_cost_scale),
                    )
                    cell_min_x = planner.origin_x_cm + x * planner.config.cell_size_cm
                    cell_min_y = planner.origin_y_cm + y * planner.config.cell_size_cm
                    cell_max_x = cell_min_x + planner.config.cell_size_cm
                    cell_max_y = cell_min_y + planner.config.cell_size_cm
                    left, top = self._world_to_screen(planner, cell_min_x, cell_max_y)
                    right, bottom = self._world_to_screen(planner, cell_max_x, cell_min_y)
                    rect = pygame.Rect(
                        min(left, right),
                        min(top, bottom),
                        max(1, abs(right - left)),
                        max(1, abs(bottom - top)),
                    )
                    heat_surface = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
                    heat_surface.fill(clearance_color)
                    self.screen.blit(heat_surface, rect.topleft)

        for y in range(planner.height_cells):
            for x in range(planner.width_cells):
                evidence_value = float(planner.evidence_grid[y][x])
                heat_color = planner_evidence_heat_color(planner, evidence_value)
                if heat_color is None:
                    continue
                evidence_min_seen = min(evidence_min_seen, evidence_value)
                evidence_max_seen = max(evidence_max_seen, evidence_value)
                cost_max_seen = max(
                    cost_max_seen,
                    1.0 + max(0.0, evidence_value) * float(planner.config.evidence_cost_scale),
                )
                cell_min_x = planner.origin_x_cm + x * planner.config.cell_size_cm
                cell_min_y = planner.origin_y_cm + y * planner.config.cell_size_cm
                cell_max_x = cell_min_x + planner.config.cell_size_cm
                cell_max_y = cell_min_y + planner.config.cell_size_cm
                left, top = self._world_to_screen(planner, cell_min_x, cell_max_y)
                right, bottom = self._world_to_screen(planner, cell_max_x, cell_min_y)
                rect = pygame.Rect(
                    min(left, right),
                    min(top, bottom),
                    max(1, abs(right - left)),
                    max(1, abs(bottom - top)),
                )
                heat_surface = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
                heat_surface.fill(heat_color)
                self.screen.blit(heat_surface, rect.topleft)
        self._draw_rover(planner, rover_xy, heading_deg)
        for y in range(planner.height_cells):
            for x in range(planner.width_cells):
                cell_value = planner.grid[y][x]
                if cell_value == 0:
                    continue
                cell_min_x = planner.origin_x_cm + x * planner.config.cell_size_cm
                cell_min_y = planner.origin_y_cm + y * planner.config.cell_size_cm
                cell_max_x = cell_min_x + planner.config.cell_size_cm
                cell_max_y = cell_min_y + planner.config.cell_size_cm
                left, top = self._world_to_screen(planner, cell_min_x, cell_max_y)
                right, bottom = self._world_to_screen(planner, cell_max_x, cell_min_y)
                rect = pygame.Rect(
                    min(left, right),
                    min(top, bottom),
                    max(1, abs(right - left)),
                    max(1, abs(bottom - top)),
                )
                cell_color = LOW_CLEARANCE_OBSTACLE_COLOR if cell_value == CELL_LOW_CLEARANCE_OBSTACLE else OBSTACLE_COLOR
                pygame.draw.rect(self.screen, cell_color, rect)

        if len(path_world) >= 2:
            path_points = [self._world_to_screen(planner, px, py) for px, py in path_world]
            pygame.draw.lines(self.screen, PATH_COLOR, False, path_points, width=3)

        for row in lidar_debug_rows or []:
            start_x = float(row["sensor_world_x_cm"])
            start_y = float(row["sensor_world_y_cm"])
            raw_cm = float(row["raw_cm"])
            if raw_cm < 0.0:
                sensor_yaw_deg = float(row["sensor_yaw_deg"])
                ray_heading_rad = math.radians(heading_deg + sensor_yaw_deg)
                hit_x = start_x + float(LIDAR_MAX_RANGE_CM) * math.cos(ray_heading_rad)
                hit_y = start_y + float(LIDAR_MAX_RANGE_CM) * math.sin(ray_heading_rad)
                hit_color = (185, 185, 185)
            else:
                if not bool(row["valid_range_ge0"]):
                    continue
                hit_x = float(row["ray_hit_world_x_cm"])
                hit_y = float(row["ray_hit_world_y_cm"])
                hit_color = LIDAR_HIT_COLOR if bool(row["mask_hit"]) else PATH_COLOR
            start_px = self._world_to_screen(planner, start_x, start_y)
            hit_px = self._world_to_screen(planner, hit_x, hit_y)
            pygame.draw.line(self.screen, hit_color, start_px, hit_px, width=2)

        gx, gy = self._world_to_screen(planner, goal_xy[0], goal_xy[1])
        tx, ty = self._world_to_screen(planner, target_xy[0], target_xy[1])
        pygame.draw.circle(self.screen, GOAL_COLOR, (gx, gy), 8)
        pygame.draw.circle(self.screen, TARGET_COLOR, (tx, ty), 6)
        self.screen.set_clip(map_clip)

        hud_lines = [
            f"Status: {status}",
            "",
            f"Rover X: {rover_xy[0]:.1f} cm",
            f"Rover Y: {rover_xy[1]:.1f} cm",
            f"Heading: {heading_deg:.1f} deg",
            f"Goal Dist: {goal_distance_cm:.1f} cm",
            f"Next Wpt Dist: {waypoint_distance_cm:.1f} cm",
            f"Avg Wpt Dist: {waypoint_distance_avg_cm:.1f} cm",
            "",
            f"Throttle Cmd: {throttle_cmd:.1f}",
            f"Steering Cmd: {steering_cmd:.2f}",
            f"Waypoint: {waypoint_idx + 1}/{max(1, len(path_world))}",
            f"Obstacles: {obstacle_total}",
            f"Evidence Min: {evidence_min_seen:.2f}",
            f"Evidence Max: {evidence_max_seen:.2f}",
            f"Clearance Max: {clearance_max_seen:.2f}",
            f"Max Cost x: {cost_max_seen:.2f}",
            "",
            "Legend",
            "Yellow triangle: Rover heading",
            "Green dot: Goal",
            "Orange dot: Current target",
            "Blue line: Planned path",
            "Blue lidar rays: classified clear",
            "Orange heat: clearance halo / keep-out cost",
            "Red lidar rays: classified obstacle",
            "Blue heat: repeated clear-space evidence",
            "Red heat: exact obstacle confidence",
            "Red cells: Obstacles",
            "Gold cells: low-clearance hits",
            "Wheel/pinch: Zoom map",
            "Drag: Pan map",
        ]

        y = self.panel_rect.top + 10
        for idx, line in enumerate(hud_lines):
            font = self.font if idx == 0 else self.small_font
            surf = font.render(line, True, TEXT_COLOR)
            self.screen.blit(surf, (self.panel_rect.left + 10, y))
            y += 32 if idx == 0 else 22

        pygame.display.flip()
        return True


def distance_cm(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(bx - ax, by - ay)


def densify_path(path_world: list[tuple[float, float]], spacing_cm: float) -> list[tuple[float, float]]:
    if len(path_world) <= 1:
        return list(path_world)
    spacing = max(1.0, float(spacing_cm))
    dense_path: list[tuple[float, float]] = [path_world[0]]
    for start, end in zip(path_world, path_world[1:]):
        sx, sy = start
        ex, ey = end
        segment_length = distance_cm(sx, sy, ex, ey)
        if segment_length <= 0.0:
            continue
        step_count = max(1, int(math.ceil(segment_length / spacing)))
        for step_idx in range(1, step_count + 1):
            t = min(1.0, float(step_idx) / float(step_count))
            dense_path.append((sx + (ex - sx) * t, sy + (ey - sy) * t))
    return dense_path


def prepend_path_endpoints(
    path_world: list[tuple[float, float]],
    start_xy: tuple[float, float],
    goal_xy: tuple[float, float],
) -> list[tuple[float, float]]:
    if not path_world:
        return []
    anchored: list[tuple[float, float]] = [start_xy]
    for point in path_world:
        if distance_cm(anchored[-1][0], anchored[-1][1], point[0], point[1]) > 1e-6:
            anchored.append(point)
    if distance_cm(anchored[-1][0], anchored[-1][1], goal_xy[0], goal_xy[1]) > 1e-6:
        anchored.append(goal_xy)
    return anchored


def select_local_path_target(
    path_world: list[tuple[float, float]],
    rover_x_cm: float,
    rover_y_cm: float,
    lookahead_cm: float,
) -> tuple[float, float, int]:
    if not path_world:
        return (rover_x_cm, rover_y_cm, 0)
    if len(path_world) == 1:
        px, py = path_world[0]
        return (px, py, 0)

    best_distance = float("inf")
    best_arc_cm = 0.0
    total_arc_cm = 0.0
    segment_lengths: list[float] = []

    for start, end in zip(path_world, path_world[1:]):
        sx, sy = start
        ex, ey = end
        dx = ex - sx
        dy = ey - sy
        seg_len_sq = dx * dx + dy * dy
        seg_len = math.sqrt(seg_len_sq)
        segment_lengths.append(seg_len)
        if seg_len_sq <= 0.0:
            continue
        proj_t = ((rover_x_cm - sx) * dx + (rover_y_cm - sy) * dy) / seg_len_sq
        proj_t = max(0.0, min(1.0, proj_t))
        proj_x = sx + proj_t * dx
        proj_y = sy + proj_t * dy
        proj_distance = distance_cm(rover_x_cm, rover_y_cm, proj_x, proj_y)
        if proj_distance < best_distance:
            best_distance = proj_distance
            best_arc_cm = total_arc_cm + proj_t * seg_len
        total_arc_cm += seg_len

    target_arc_cm = min(total_arc_cm, best_arc_cm + max(1.0, float(lookahead_cm)))
    traversed_cm = 0.0
    for seg_idx, seg_len in enumerate(segment_lengths):
        start = path_world[seg_idx]
        end = path_world[seg_idx + 1]
        if seg_len <= 0.0:
            continue
        next_traversed_cm = traversed_cm + seg_len
        if target_arc_cm <= next_traversed_cm:
            local_t = (target_arc_cm - traversed_cm) / seg_len
            sx, sy = start
            ex, ey = end
            target_x = sx + (ex - sx) * local_t
            target_y = sy + (ey - sy) * local_t
            return (target_x, target_y, seg_idx + 1)
        traversed_cm = next_traversed_cm

    target_x, target_y = path_world[-1]
    return (target_x, target_y, max(0, len(path_world) - 1))


def build_active_path_from_rover(
    path_world: list[tuple[float, float]],
    rover_x_cm: float,
    rover_y_cm: float,
) -> list[tuple[float, float]]:
    if not path_world:
        return []
    if len(path_world) == 1:
        only_x, only_y = path_world[0]
        if distance_cm(rover_x_cm, rover_y_cm, only_x, only_y) <= 1e-6:
            return [(rover_x_cm, rover_y_cm)]
        return [(rover_x_cm, rover_y_cm), (only_x, only_y)]

    best_distance = float("inf")
    best_segment_idx = 0
    best_proj_x = path_world[0][0]
    best_proj_y = path_world[0][1]
    best_proj_t = 0.0

    for seg_idx, (start, end) in enumerate(zip(path_world, path_world[1:])):
        sx, sy = start
        ex, ey = end
        dx = ex - sx
        dy = ey - sy
        seg_len_sq = dx * dx + dy * dy
        if seg_len_sq <= 0.0:
            continue
        proj_t = ((rover_x_cm - sx) * dx + (rover_y_cm - sy) * dy) / seg_len_sq
        proj_t = max(0.0, min(1.0, proj_t))
        proj_x = sx + proj_t * dx
        proj_y = sy + proj_t * dy
        proj_distance = distance_cm(rover_x_cm, rover_y_cm, proj_x, proj_y)
        if proj_distance < best_distance:
            best_distance = proj_distance
            best_segment_idx = seg_idx
            best_proj_x = proj_x
            best_proj_y = proj_y
            best_proj_t = proj_t

    active_path: list[tuple[float, float]] = [(rover_x_cm, rover_y_cm)]
    if distance_cm(rover_x_cm, rover_y_cm, best_proj_x, best_proj_y) > 1e-6:
        active_path.append((best_proj_x, best_proj_y))

    if best_proj_t < 1.0 - 1e-6:
        segment_end = path_world[best_segment_idx + 1]
        if distance_cm(active_path[-1][0], active_path[-1][1], segment_end[0], segment_end[1]) > 1e-6:
            active_path.append(segment_end)

    for point in path_world[best_segment_idx + 2 :]:
        if distance_cm(active_path[-1][0], active_path[-1][1], point[0], point[1]) > 1e-6:
            active_path.append(point)
    return active_path


def wrap_angle_deg(angle: float) -> float:
    return (angle + 180.0) % 360.0 - 180.0


def heading_error_deg(current_heading_deg: float, target_heading_deg: float) -> float:
    return wrap_angle_deg(target_heading_deg - current_heading_deg)


def dust_heading_to_math_deg(raw_heading_deg: float) -> float:
    # DUST heading behaves like a compass heading: 0 is +Y and positive rotation is clockwise.
    return wrap_angle_deg(90.0 - raw_heading_deg)


def parse_pose(telemetry: dict) -> tuple[float, float, float, float]:
    x = float(telemetry.get("rover_pos_x", 0.0)) * POSE_UNITS_TO_CM - POSE_OFFSET_X_CM
    y = float(telemetry.get("rover_pos_y", 0.0)) * POSE_UNITS_TO_CM - POSE_OFFSET_Y_CM
    z = float(telemetry.get("rover_pos_z", 0.0)) * POSE_UNITS_TO_CM - POSE_OFFSET_Z_CM
    heading = dust_heading_to_math_deg(float(telemetry.get("heading", 0.0)))
    return (x, y, z, heading)


def parse_lidar(telemetry: dict) -> np.ndarray:
    raw = telemetry.get("lidar", [])
    return np.asarray(raw, dtype=np.float32).reshape(-1)


def open_lidar_log_file() -> tuple[TextIO, Path]:
    LIDAR_LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    path = LIDAR_LOG_DIR / f"lidar_readings_{timestamp}.csv"
    log_file = path.open("w", encoding="utf-8")
    log_file.write(
        "elapsed_s,step_idx,rover_x_cm,rover_y_cm,rover_heading_deg,"
        "sensor_index,sensor_label,sensor_x_cm,sensor_y_cm,sensor_yaw_deg,sensor_pitch_deg,"
        "distance_cm\n"
    )
    return (log_file, path)


def sensor_label_for_index(sensor_index: int) -> str:
    if 0 <= sensor_index < len(LIDAR_SENSOR_LABELS):
        return LIDAR_SENSOR_LABELS[sensor_index]
    return f"sensor_{sensor_index:02d}"


def log_lidar_snapshot(
    log_file: TextIO,
    elapsed_s: float,
    step_idx: int,
    rover_x_cm: float,
    rover_y_cm: float,
    rover_heading_deg: float,
    lidar_cm: np.ndarray,
) -> None:
    count = len(lidar_cm)
    for idx in range(count):
        distance = float(lidar_cm[idx])
        sx, sy, syaw, spitch = (float("nan"), float("nan"), float("nan"), float("nan"))
        if idx < len(LIDAR_SENSOR_LAYOUT):
            sx, sy, syaw, spitch = LIDAR_SENSOR_LAYOUT[idx]
        log_file.write(
            f"{elapsed_s:.3f},{step_idx},{rover_x_cm:.2f},{rover_y_cm:.2f},{rover_heading_deg:.2f},"
            f"{idx},{sensor_label_for_index(idx)},{sx:.2f},{sy:.2f},{syaw:.2f},{spitch:.2f},"
            f"{distance:.2f}\n"
        )
    log_file.flush()


def obstacle_mask_from_inference(infer_output: dict, lidar_count: int) -> np.ndarray:
    if "obstacle_mask" in infer_output:
        mask = np.asarray(infer_output["obstacle_mask"]).reshape(-1).astype(bool)
    elif "class_ids" in infer_output:
        class_ids = np.asarray(infer_output["class_ids"]).reshape(-1)
        mask = class_ids == 1
    else:
        mask = np.zeros(lidar_count, dtype=bool)

    if mask.size == lidar_count:
        return mask
    if mask.size == 1:
        return np.full(lidar_count, bool(mask[0]), dtype=bool)
    if mask.size > lidar_count:
        return mask[:lidar_count]

    padded = np.zeros(lidar_count, dtype=bool)
    padded[: mask.size] = mask
    return padded


def _mark_space_hub(planner: OccupancyPlanner) -> None:
    x_min, x_max, y_min, y_max = SPACE_HUB_RECT_CM
    cx_min, cy_min = planner.world_to_cell(x_min, y_min)
    cx_max, cy_max = planner.world_to_cell(x_max, y_max)
    if cx_min > cx_max:
        cx_min, cx_max = cx_max, cx_min
    if cy_min > cy_max:
        cy_min, cy_max = cy_max, cy_min
    for cy in range(cy_min, cy_max + 1):
        for cx in range(cx_min, cx_max + 1):
            planner.mark_obstacle_cell((cx, cy), CELL_OBSTACLE)


def create_planner(
    start_xy: tuple[float, float],
    goal_xy: tuple[float, float],
    *,
    use_jump_point_search: bool = False,
) -> OccupancyPlanner:
    min_x = min(start_xy[0], goal_xy[0]) - GRID_MARGIN_CM
    max_x = max(start_xy[0], goal_xy[0]) + GRID_MARGIN_CM
    min_y = min(start_xy[1], goal_xy[1]) - GRID_MARGIN_CM
    max_y = max(start_xy[1], goal_xy[1]) + GRID_MARGIN_CM

    width_cells = int(math.ceil((max_x - min_x) / GRID_CELL_SIZE_CM)) + 1
    height_cells = int(math.ceil((max_y - min_y) / GRID_CELL_SIZE_CM)) + 1

    planner = OccupancyPlanner(
        origin_x_cm=min_x,
        origin_y_cm=min_y,
        width_cells=width_cells,
        height_cells=height_cells,
        config=PlannerConfig(
            cell_size_cm=GRID_CELL_SIZE_CM,
            obstacle_padding_cells=OBSTACLE_PADDING_CELLS,
            allow_diagonal=True,
            use_jump_point_search=use_jump_point_search,
            evidence_cost_scale=PATH_EVIDENCE_COST_SCALE,
            clearance_cost_scale=PATH_CLEARANCE_COST_SCALE,
            evidence_min_value=PATH_EVIDENCE_MIN_VALUE,
            evidence_max_value=PATH_EVIDENCE_MAX_VALUE,
            clearance_min_value=PATH_CLEARANCE_MIN_VALUE,
            clearance_max_value=PATH_CLEARANCE_MAX_VALUE,
        ),
    )
    _mark_space_hub(planner)
    return planner


def smooth_path_los(
    path: list[tuple[float, float]],
    planner: OccupancyPlanner,
) -> list[tuple[float, float]]:
    if len(path) < 3:
        return path
    smoothed: list[tuple[float, float]] = [path[0]]
    i = 0
    n = len(path)
    while i < n - 1:
        # Scan from the end backwards for the furthest point reachable in a straight
        # line. If no LOS exists to any skip-ahead point, j falls to i+1 (next step).
        # i = j always advances by at least 1 so the loop terminates.
        j = n - 1
        while j > i + 1:
            cells = planner.world_line_cells(path[i], path[j])
            if not any(planner.is_padded_obstacle(cell) for cell in cells):
                break
            j -= 1
        smoothed.append(path[j])
        i = j
    return smoothed


def plan_path_for_following(
    planner: OccupancyPlanner,
    start_xy: tuple[float, float],
    goal_xy: tuple[float, float],
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    raw_path = planner.plan_path(start_xy, goal_xy)
    smoothed_path = smooth_path_los(raw_path, planner)
    anchored_path = prepend_path_endpoints(smoothed_path, start_xy, goal_xy)
    follow_path = densify_path(anchored_path, PATH_WAYPOINT_SPACING_CM)
    return (anchored_path, follow_path)


def update_obstacles_from_lidar(
    planner: OccupancyPlanner,
    rover_x_cm: float,
    rover_y_cm: float,
    rover_z_cm: float,
    rover_heading_deg: float,
    lidar_cm: np.ndarray,
    obstacle_mask: np.ndarray,
    debug_rows: list[dict[str, float | int | bool | str]] | None = None,
    evidence_updates: list[tuple[float, float, float]] | None = None,
    clearance_updates: list[tuple[float, float, float]] | None = None,
) -> int:
    new_obstacles = 0
    count = len(LIDAR_SENSOR_LAYOUT)
    sensor_states: list[dict[str, float | int | bool | str]] = []
    chunk_hit_counts = {chunk_name: 0 for chunk_name in LIDAR_CHUNK_SENSOR_GROUPS}

    for idx in range(count):
        distance_hit = float(lidar_cm[idx]) if idx < len(lidar_cm) else float("nan")
        mask_hit = bool(obstacle_mask[idx]) if idx < len(obstacle_mask) else False
        sensor_enabled = bool(LIDAR_SENSOR_MAP_ENABLED[idx]) if idx < len(LIDAR_SENSOR_MAP_ENABLED) else False
        sx, sy, syaw, spitch = LIDAR_SENSOR_LAYOUT[idx]
        chunk_name = LIDAR_SENSOR_TO_CHUNK.get(idx, "unassigned")
        pitch_scale = max(0.0, math.cos(math.radians(spitch)))
        pitch_rad = math.radians(spitch)
        raw_is_zero = idx < len(lidar_cm) and (distance_hit == 0.0)
        valid_range_gt0 = idx < len(lidar_cm) and (distance_hit > 0.0) and (distance_hit <= LIDAR_MAX_RANGE_CM)
        valid_range_ge0 = idx < len(lidar_cm) and (distance_hit >= 0.0) and (distance_hit <= LIDAR_MAX_RANGE_CM)
        planar_hit_distance = distance_hit * pitch_scale if valid_range_ge0 else float("nan")
        hit_world_z_cm = rover_z_cm + distance_hit * math.sin(pitch_rad) if valid_range_ge0 else float("nan")
        low_clearance_hit = valid_range_ge0 and hit_world_z_cm < (rover_z_cm - ROVER_UNDERBODY_CLEARANCE_CM)
        min_distance_ok = valid_range_gt0 and planar_hit_distance >= MIN_OBSTACLE_MARK_DISTANCE_CM
        candidate_hit = min_distance_ok and mask_hit
        low_clearance_allowed = (not low_clearance_hit) or RENDER_LOW_CLEARANCE_HITS_IN_ALT_COLOR
        candidate_map_hit = candidate_hit and sensor_enabled and low_clearance_allowed
        if candidate_map_hit:
            chunk_hit_counts[chunk_name] = chunk_hit_counts.get(chunk_name, 0) + 1
        sensor_states.append(
            {
                "sensor_idx": idx,
                "sensor_label": sensor_label_for_index(idx),
                "sensor_enabled": sensor_enabled,
                "raw_cm": distance_hit,
                "raw_is_zero": raw_is_zero,
                "valid_range_gt0": valid_range_gt0,
                "valid_range_ge0": valid_range_ge0,
                "mask_hit": mask_hit,
                "pitch_scale": pitch_scale,
                "planar_hit_cm": planar_hit_distance,
                "hit_world_z_cm": hit_world_z_cm,
                "low_clearance_hit": low_clearance_hit,
                "chunk_name": chunk_name,
                "candidate_hit": candidate_hit,
                "candidate_map_hit": candidate_map_hit,
                "low_clearance_allowed": low_clearance_allowed,
                "min_distance_ok": min_distance_ok,
                "sensor_local_x_cm": sx,
                "sensor_local_y_cm": sy,
                "sensor_yaw_deg": syaw,
                "sensor_pitch_deg": spitch,
            }
        )

    for state in sensor_states:
        idx = int(state["sensor_idx"])
        distance_hit = float(state["raw_cm"])
        mask_hit = bool(state["mask_hit"])
        sx = float(state["sensor_local_x_cm"])
        sy = float(state["sensor_local_y_cm"])
        syaw = float(state["sensor_yaw_deg"])
        chunk_name = str(state["chunk_name"])
        sensor_enabled = bool(state["sensor_enabled"])
        valid_range_ge0 = bool(state["valid_range_ge0"])
        valid_range_gt0 = bool(state["valid_range_gt0"])
        candidate_hit = bool(state["candidate_hit"])
        candidate_map_hit = bool(state["candidate_map_hit"])
        low_clearance_allowed = bool(state["low_clearance_allowed"])
        min_distance_ok = bool(state["min_distance_ok"])
        planar_hit_distance = float(state["planar_hit_cm"])
        hit_world_z_cm = float(state["hit_world_z_cm"])
        low_clearance_hit = bool(state["low_clearance_hit"])
        chunk_hit_count = int(chunk_hit_counts.get(chunk_name, 0))
        chunk_threshold_met = chunk_hit_count >= OBSTACLE_HITS_REQUIRED_PER_CHUNK
        usable_for_mark = candidate_map_hit and chunk_threshold_met and low_clearance_allowed
        sensor_world_x, sensor_world_y = local_to_world_2d(
            rover_x_cm,
            rover_y_cm,
            rover_heading_deg,
            sx,
            sy,
        )
        sensor_cell_x, sensor_cell_y = planner.world_to_cell(sensor_world_x, sensor_world_y)
        hit_heading_rad = math.radians(rover_heading_deg + syaw)
        center_hit_world_x = float("nan")
        center_hit_world_y = float("nan")
        center_hit_cell_x = -1
        center_hit_cell_y = -1
        ray_hit_world_x = float("nan")
        ray_hit_world_y = float("nan")
        if valid_range_ge0:
            center_hit_world_x = rover_x_cm + planar_hit_distance * math.cos(hit_heading_rad)
            center_hit_world_y = rover_y_cm + planar_hit_distance * math.sin(hit_heading_rad)
            center_hit_cell_x, center_hit_cell_y = planner.world_to_cell(center_hit_world_x, center_hit_world_y)
            ray_hit_world_x = sensor_world_x + planar_hit_distance * math.cos(hit_heading_rad)
            ray_hit_world_y = sensor_world_y + planar_hit_distance * math.sin(hit_heading_rad)
        hit_world_x = float("nan")
        hit_world_y = float("nan")
        hit_dist_from_rover = float("nan")
        hit_cell_x = -1
        hit_cell_y = -1
        within_local_radius = False
        placed = False
        inside_rover_bbox = False
        usable_reason = "invalid_range"
        map_origin = "sensor" if MAP_USE_SENSOR_ORIGIN else "center"
        evidence_delta = 0.0
        evidence_value = float("nan")
        clearance_value = float("nan")
        free_evidence_applied = 0

        ray_end_world_x = float("nan")
        ray_end_world_y = float("nan")
        if valid_range_ge0:
            if MAP_USE_SENSOR_ORIGIN:
                ray_end_world_x = ray_hit_world_x
                ray_end_world_y = ray_hit_world_y
            else:
                ray_end_world_x = center_hit_world_x
                ray_end_world_y = center_hit_world_y

        if valid_range_gt0 and math.isfinite(ray_end_world_x) and math.isfinite(ray_end_world_y):
            line_cells = planner.world_line_cells((sensor_world_x, sensor_world_y), (ray_end_world_x, ray_end_world_y))
            free_cells = line_cells[:-1] if line_cells else []
            if not mask_hit and line_cells:
                free_cells = line_cells
            for free_cell_x, free_cell_y in free_cells:
                if planner.add_evidence_cell((free_cell_x, free_cell_y), LIDAR_CLEAR_EVIDENCE_DELTA):
                    free_evidence_applied += 1
                    if evidence_updates is not None:
                        free_x_cm, free_y_cm = planner.cell_to_world_center((free_cell_x, free_cell_y))
                        evidence_updates.append((free_x_cm, free_y_cm, LIDAR_CLEAR_EVIDENCE_DELTA))

        if usable_for_mark:
            if MAP_USE_SENSOR_ORIGIN:
                hit_world_x = ray_hit_world_x
                hit_world_y = ray_hit_world_y
            else:
                hit_world_x = center_hit_world_x
                hit_world_y = center_hit_world_y
            hit_dist_from_rover = distance_cm(rover_x_cm, rover_y_cm, hit_world_x, hit_world_y)
            within_local_radius = hit_dist_from_rover <= LOCAL_OBSTACLE_MARK_RADIUS_CM
            hit_cell_x, hit_cell_y = planner.world_to_cell(hit_world_x, hit_world_y)
            if within_local_radius:
                inside_rover_bbox = point_in_rover_bbox(
                    rover_x_cm,
                    rover_y_cm,
                    rover_heading_deg,
                    hit_world_x,
                    hit_world_y,
                )
                if inside_rover_bbox:
                    usable_reason = "inside_rover_bbox"
                else:
                    placed, evidence_value, clearance_value = apply_obstacle_evidence_kernel(
                        planner,
                        (hit_world_x, hit_world_y),
                        (hit_cell_x, hit_cell_y),
                        hit_dist_from_rover,
                        evidence_updates=evidence_updates,
                        clearance_updates=clearance_updates,
                    )
                    evidence_delta = (
                        float(LIDAR_OBSTACLE_EVIDENCE_DELTA)
                        * (1.0 + max(0.0, min(1.0, 1.0 - (hit_dist_from_rover / max(1.0, LOCAL_OBSTACLE_MARK_RADIUS_CM)))) * float(LIDAR_OBSTACLE_PROXIMITY_GAIN))
                    )
                    usable_reason = "evidence_added" if placed else "evidence_saturated"
            else:
                usable_reason = "out_of_local_radius"
        else:
            if not valid_range_ge0:
                usable_reason = "invalid_range"
            elif not valid_range_gt0:
                usable_reason = "nonpositive_range"
            elif not sensor_enabled:
                usable_reason = "sensor_disabled"
            elif not min_distance_ok:
                usable_reason = "below_min_distance"
            elif not candidate_hit:
                usable_reason = "masked_hit"
            elif low_clearance_hit and not RENDER_LOW_CLEARANCE_HITS_IN_ALT_COLOR:
                usable_reason = "low_clearance_ignored"
            elif not chunk_threshold_met:
                usable_reason = "insufficient_chunk_hits"
            else:
                usable_reason = "unknown_reject"
        if placed:
            new_obstacles += 1
        if debug_rows is not None:
            debug_rows.append(
                {
                    "sensor_idx": idx,
                    "sensor_label": state["sensor_label"],
                    "sensor_enabled": sensor_enabled,
                    "raw_cm": distance_hit,
                    "raw_is_zero": bool(state["raw_is_zero"]),
                    "valid_range_gt0": bool(state["valid_range_gt0"]),
                    "valid_range_ge0": valid_range_ge0,
                    "mask_hit": mask_hit,
                    "pitch_scale": float(state["pitch_scale"]),
                    "planar_hit_cm": planar_hit_distance,
                    "hit_world_z_cm": hit_world_z_cm,
                    "low_clearance_hit": low_clearance_hit,
                    "chunk_name": chunk_name,
                    "chunk_hit_count": chunk_hit_count,
                    "chunk_threshold_met": chunk_threshold_met,
                    "hit_dist_from_rover_cm": hit_dist_from_rover,
                    "within_local_radius": within_local_radius,
                    "usable_for_mark": usable_for_mark,
                    "placed": placed,
                    "evidence_delta": evidence_delta,
                    "evidence_value": evidence_value,
                    "clearance_value": clearance_value,
                    "free_evidence_applied": free_evidence_applied,
                    "usable_reason": usable_reason,
                    "map_origin": map_origin,
                    "sensor_local_x_cm": sx,
                    "sensor_local_y_cm": sy,
                    "sensor_yaw_deg": syaw,
                    "sensor_pitch_deg": float(state["sensor_pitch_deg"]),
                    "sensor_world_x_cm": sensor_world_x,
                    "sensor_world_y_cm": sensor_world_y,
                    "sensor_cell_x": sensor_cell_x,
                    "sensor_cell_y": sensor_cell_y,
                    "hit_world_x_cm": hit_world_x,
                    "hit_world_y_cm": hit_world_y,
                    "ray_hit_world_x_cm": ray_hit_world_x,
                    "ray_hit_world_y_cm": ray_hit_world_y,
                    "hit_cell_x": hit_cell_x,
                    "hit_cell_y": hit_cell_y,
                    "center_hit_world_x_cm": center_hit_world_x,
                    "center_hit_world_y_cm": center_hit_world_y,
                    "center_hit_cell_x": center_hit_cell_x,
                    "center_hit_cell_y": center_hit_cell_y,
                    "rover_x_cm": rover_x_cm,
                    "rover_y_cm": rover_y_cm,
                    "rover_heading_deg": rover_heading_deg,
                }
            )
    return new_obstacles


def choose_drive_command(
    rover_x_cm: float,
    rover_y_cm: float,
    rover_heading_deg: float,
    target_x_cm: float,
    target_y_cm: float,
    *,
    cruise_throttle: float | None = None,
    turn_throttle: float | None = None,
    heading_align_deg: float | None = None,
    throttle_steering_exponent: float | None = None,
) -> tuple[float, float, float, float]:
    _cruise = CRUISE_THROTTLE if cruise_throttle is None else cruise_throttle
    _turn = TURN_THROTTLE if turn_throttle is None else turn_throttle
    _align = HEADING_ALIGN_DEG if heading_align_deg is None else heading_align_deg
    _exp = THROTTLE_STEERING_EXPONENT if throttle_steering_exponent is None else throttle_steering_exponent

    desired_heading = math.degrees(math.atan2(target_y_cm - rover_y_cm, target_x_cm - rover_x_cm))
    error = heading_error_deg(rover_heading_deg, desired_heading)
    steering = max(-1.0, min(1.0, error / FULL_STEER_ERROR_DEG))
    if abs(error) < 2.0:
        steering = 0.0

    throttle_span = max(0.0, _cruise - _turn)
    steering_fraction = min(1.0, abs(steering))
    throttle_drop = throttle_span * (steering_fraction ** _exp)
    throttle = _cruise - throttle_drop
    if abs(error) > _align:
        throttle = max(_turn, throttle)
    return (throttle, steering, desired_heading, error)


def resolve_forward_pulse_command(
    desired_throttle: float,
    now_monotonic: float,
    pulse_start_monotonic: float | None,
) -> tuple[float, bool, float | None]:
    if desired_throttle <= 0.0:
        return (desired_throttle, False, None)

    pulse_period_sec = FORWARD_DRIVE_PULSE_SEC + FORWARD_BRAKE_PULSE_SEC
    if pulse_start_monotonic is None:
        pulse_start_monotonic = now_monotonic
    pulse_elapsed_sec = (now_monotonic - pulse_start_monotonic) % pulse_period_sec
    if pulse_elapsed_sec < FORWARD_DRIVE_PULSE_SEC:
        return (CRUISE_THROTTLE, False, pulse_start_monotonic)
    return (CRUISE_THROTTLE, True, pulse_start_monotonic)


def log_step(
    step_idx: int,
    elapsed_s: float,
    x_cm: float,
    y_cm: float,
    heading_deg: float,
    heading_delta_deg: float,
    desired_heading_deg: float,
    heading_error: float,
    throttle_cmd: float,
    steering_cmd: float,
    waypoint_idx: int,
    path_len: int,
    dist_to_waypoint_cm: float,
    waypoint_progress_cm: float,
    dist_to_goal_cm: float,
    goal_progress_pct: float,
    new_obstacles: int,
    status: str,
) -> None:
    print(
        f"[step {step_idx:05d}] "
        f"t={elapsed_s:7.2f}s "
        f"wp={waypoint_idx + 1:03d}/{max(path_len, 1):03d} "
        f"pos=({x_cm:8.1f},{y_cm:8.1f}) "
        f"hdg={heading_deg:7.2f} dH={heading_delta_deg:+7.2f} "
        f"target_hdg={desired_heading_deg:7.2f} err={heading_error:+7.2f} "
        f"thr={throttle_cmd:+7.2f} str={steering_cmd:+6.2f} "
        f"d_wp={dist_to_waypoint_cm:8.1f} d_wp_step={waypoint_progress_cm:+7.1f} "
        f"d_goal={dist_to_goal_cm:8.1f} goal_prog={goal_progress_pct:6.2f}% "
        f"obs+={new_obstacles:2d} status='{status}'"
    )


def stop_rover(sock) -> None:
    for fn, value in ((set_throttle, 0.0), (set_steering, 0.0), (set_brakes, True)):
        try:
            fn(sock, value)
        except Exception:
            pass


def main() -> None:
    sock = open_rover_socket()
    viewer: MapWindow | None = None
    debug_writer: DebugRunWriter | None = None
    try:
        if not wait_for_dust(sock, timeout_seconds=20.0, poll_seconds=0.5):
            raise RuntimeError("DUST is not connected to TSS.")

        reset_history()
        telemetry = fetch_rover_telemetry(sock)
        initial_x, initial_y, _, _ = parse_pose(telemetry)
        goal_x = initial_x + TARGET_DX_CM
        goal_y = initial_y + TARGET_DY_CM

        set_brakes(sock, False)

        # Requested pre-path behavior: reverse burst, then hold brakes briefly to kill momentum.
        set_steering(sock, -0.5)
        set_throttle(sock, PREPATH_STRAIGHT_THROTTLE)
        burst_end = time.monotonic() + PREPATH_STRAIGHT_SECONDS
        while time.monotonic() < burst_end:
            time.sleep(CONTROL_PERIOD_SEC)

        # Kill residual momentum before taking the pathfinding start pose.
        set_throttle(sock, 0.0)
        set_brakes(sock, True)
        set_steering(sock, 0.0)
        time.sleep(PREPATH_MOMENTUM_BRAKE_SECONDS)

        telemetry = fetch_rover_telemetry(sock)
        start_x, start_y, _, heading = parse_pose(telemetry)
        planner = create_planner((start_x, start_y), (goal_x, goal_y))
        viewer = MapWindow(planner)
        model_backend = inferencer_backend()
        if not model_backend.startswith("gru_pt_loaded"):
            print(f"WARNING: lidar classifier backend='{model_backend}' (not using GRU inferencer).")
        if DEBUG_TEXT_LOGGING:
            debug_writer = DebugRunWriter()
            debug_writer.write_config(
                planner=planner,
                start_xy=(start_x, start_y),
                goal_xy=(goal_x, goal_y),
                model_backend=model_backend,
            )
            print(f"Debug logs: {debug_writer.run_dir}")

        set_brakes(sock, False)
        _, path = plan_path_for_following(planner, (start_x, start_y), (goal_x, goal_y))
        waypoint_idx = 0
        last_plan_time = 0.0
        obstacle_total = 0
        status = "Running"
        loop_start_time = time.monotonic()
        step_idx = 0
        prev_heading = heading
        prev_waypoint_idx = waypoint_idx
        prev_waypoint_distance: float | None = None
        forward_pulse_start: float | None = None
        waypoint_distance_sum_cm = 0.0
        waypoint_distance_count = 0
        initial_goal_distance = max(distance_cm(start_x, start_y, goal_x, goal_y), 1.0)
        while True:
            telemetry = fetch_rover_telemetry(sock)
            x, y, z, heading = parse_pose(telemetry)
            telemetry_speed = float(telemetry.get("speed", 0.0))
            telemetry_throttle = float(telemetry.get("throttle", 0.0))
            telemetry_steering = float(telemetry.get("steering", 0.0))
            telemetry_brakes = bool(telemetry.get("brakes", False))
            telemetry_distance_traveled = float(telemetry.get("distance_traveled", 0.0))
            goal_distance = distance_cm(x, y, goal_x, goal_y)
            elapsed_s = time.monotonic() - loop_start_time

            lidar = parse_lidar(telemetry)
            inference = ingest_lidar(
                lidar_cm=lidar,
                pose_xyz_cm=np.asarray([x, y, z], dtype=np.float32),
                basis=heading_basis_matrix(heading),
            )
            obstacle_mask = obstacle_mask_from_inference(inference, len(lidar))
            lidar_debug_rows: list[dict[str, float | int | bool | str]] = []
            new_obstacles = update_obstacles_from_lidar(
                planner=planner,
                rover_x_cm=x,
                rover_y_cm=y,
                rover_z_cm=z,
                rover_heading_deg=heading,
                lidar_cm=lidar,
                obstacle_mask=obstacle_mask,
                debug_rows=lidar_debug_rows,
            )
            if debug_writer is not None:
                debug_writer.log_lidar_rows(step_idx=step_idx, elapsed_s=elapsed_s, rows=lidar_debug_rows)
                debug_writer.log_zero_rows(step_idx=step_idx, elapsed_s=elapsed_s, rows=lidar_debug_rows)
            obstacle_total += new_obstacles

            now = time.monotonic()
            should_replan = (new_obstacles > 0 and (now - last_plan_time) >= REPLAN_MIN_INTERVAL_SEC) or not path
            raw_path_points = 0
            follow_path_points = 0
            if should_replan:
                raw_path, new_path = plan_path_for_following(planner, (x, y), (goal_x, goal_y))
                raw_path_points = len(raw_path)
                follow_path_points = len(new_path)
                if new_path:
                    path = new_path
                    waypoint_idx = 0
                    last_plan_time = now
                    status = f"Replanned ({len(path)} pts)"
                else:
                    status = "Replan failed"
            elif new_obstacles > 0:
                status = f"Obstacle hits: +{new_obstacles}"
            else:
                status = "Running"
            if debug_writer is not None:
                debug_writer.log_replan(
                    step_idx=step_idx,
                    elapsed_s=elapsed_s,
                    attempted=should_replan,
                    raw_path_points=raw_path_points,
                    follow_path_points=follow_path_points,
                    status=status,
                )

            active_path = build_active_path_from_rover(path, x, y)

            if active_path:
                target_x, target_y, waypoint_idx = select_local_path_target(
                    path_world=active_path,
                    rover_x_cm=x,
                    rover_y_cm=y,
                    lookahead_cm=PATH_TARGET_LOOKAHEAD_CM,
                )
            else:
                target_x, target_y = goal_x, goal_y
                waypoint_idx = 0

            dist_to_waypoint = distance_cm(x, y, target_x, target_y)
            waypoint_distance_sum_cm += dist_to_waypoint
            waypoint_distance_count += 1
            waypoint_distance_avg_cm = waypoint_distance_sum_cm / max(1, waypoint_distance_count)
            if prev_waypoint_idx == waypoint_idx and prev_waypoint_distance is not None:
                waypoint_progress_cm = prev_waypoint_distance - dist_to_waypoint
            else:
                waypoint_progress_cm = 0.0

            if goal_distance <= GOAL_REACHED_CM:
                status = "Goal reached"
                throttle_cmd = 0.0
                steering_cmd = 0.0
                desired_heading = heading
                heading_err = 0.0
                forward_pulse_start = None
                stop_rover(sock)
            else:
                desired_throttle_cmd, steering_cmd, desired_heading, heading_err = choose_drive_command(
                    x, y, heading, target_x, target_y
                )
                throttle_cmd, brake_cmd, forward_pulse_start = resolve_forward_pulse_command(
                    desired_throttle=desired_throttle_cmd,
                    now_monotonic=now,
                    pulse_start_monotonic=forward_pulse_start,
                )
                set_steering(sock, steering_cmd)
                set_brakes(sock, brake_cmd)
                set_throttle(sock, throttle_cmd)

            if not viewer.draw(
                planner=planner,
                rover_xy=(x, y),
                heading_deg=heading,
                goal_xy=(goal_x, goal_y),
                target_xy=(target_x, target_y),
                path_world=active_path,
                status=status,
                goal_distance_cm=goal_distance,
                throttle_cmd=throttle_cmd,
                steering_cmd=steering_cmd,
                waypoint_idx=waypoint_idx,
                waypoint_distance_cm=dist_to_waypoint,
                waypoint_distance_avg_cm=waypoint_distance_avg_cm,
                obstacle_total=obstacle_total,
                lidar_cm=lidar,
                lidar_debug_rows=lidar_debug_rows,
            ):
                break

            if status == "Goal reached":
                time.sleep(0.5)
                break

            heading_delta = heading_error_deg(prev_heading, heading)
            goal_progress_pct = max(0.0, min(100.0, (1.0 - goal_distance / initial_goal_distance) * 100.0))
            if STEP_LOGGING:
                log_step(
                    step_idx=step_idx,
                    elapsed_s=elapsed_s,
                    x_cm=x,
                    y_cm=y,
                    heading_deg=heading,
                    heading_delta_deg=heading_delta,
                    desired_heading_deg=desired_heading,
                    heading_error=heading_err,
                    throttle_cmd=throttle_cmd,
                    steering_cmd=steering_cmd,
                    waypoint_idx=waypoint_idx,
                    path_len=len(active_path),
                    dist_to_waypoint_cm=dist_to_waypoint,
                    waypoint_progress_cm=waypoint_progress_cm,
                    dist_to_goal_cm=goal_distance,
                    goal_progress_pct=goal_progress_pct,
                    new_obstacles=new_obstacles,
                    status=status,
                )
            if debug_writer is not None:
                rover_cell_x, rover_cell_y = planner.world_to_cell(x, y)
                target_cell_x, target_cell_y = planner.world_to_cell(target_x, target_y)
                usable_distances = [
                    float(row["planar_hit_cm"])
                    for row in lidar_debug_rows
                    if bool(row["usable_for_mark"]) and not math.isnan(float(row["planar_hit_cm"]))
                ]
                positive_raw_distances = [
                    float(row["raw_cm"])
                    for row in lidar_debug_rows
                    if float(row["raw_cm"]) > 0.0 and float(row["raw_cm"]) <= LIDAR_MAX_RANGE_CM
                ]
                closest_usable_lidar_cm = min(usable_distances) if usable_distances else float("nan")
                closest_raw_positive_lidar_cm = min(positive_raw_distances) if positive_raw_distances else float("nan")
                zero_lidar_sensor_count = sum(1 for row in lidar_debug_rows if float(row["raw_cm"]) == 0.0)
                usable_lidar_sensor_count = sum(1 for row in lidar_debug_rows if bool(row["usable_for_mark"]))
                debug_writer.log_step(
                    step_idx=step_idx,
                    elapsed_s=elapsed_s,
                    status=status,
                    rover_x_cm=x,
                    rover_y_cm=y,
                    rover_z_cm=z,
                    rover_heading_deg=heading,
                    goal_dist_cm=goal_distance,
                    next_waypoint_dist_cm=dist_to_waypoint,
                    next_waypoint_avg_cm=waypoint_distance_avg_cm,
                    target_x_cm=target_x,
                    target_y_cm=target_y,
                    waypoint_idx=waypoint_idx,
                    path_len=len(active_path),
                    throttle_cmd=throttle_cmd,
                    steering_cmd=steering_cmd,
                    telemetry_throttle=telemetry_throttle,
                    telemetry_steering=telemetry_steering,
                    telemetry_speed=telemetry_speed,
                    telemetry_brakes=telemetry_brakes,
                    telemetry_distance_traveled=telemetry_distance_traveled,
                    new_obstacles=new_obstacles,
                    obstacle_total=obstacle_total,
                    rover_cell_x=rover_cell_x,
                    rover_cell_y=rover_cell_y,
                    target_cell_x=target_cell_x,
                    target_cell_y=target_cell_y,
                    viewer_scale_x=viewer.scale_x,
                    viewer_scale_y=viewer.scale_y,
                    closest_usable_lidar_cm=closest_usable_lidar_cm,
                    closest_raw_positive_lidar_cm=closest_raw_positive_lidar_cm,
                    zero_lidar_sensor_count=zero_lidar_sensor_count,
                    usable_lidar_sensor_count=usable_lidar_sensor_count,
                )

            step_idx += 1
            prev_heading = heading
            prev_waypoint_idx = waypoint_idx
            prev_waypoint_distance = dist_to_waypoint

            time.sleep(CONTROL_PERIOD_SEC)

    except KeyboardInterrupt:
        pass
    finally:
        stop_rover(sock)
        close_rover_socket(sock)
        if debug_writer is not None:
            debug_writer.close()
        if viewer is not None:
            viewer.close()


if __name__ == "__main__":
    main()

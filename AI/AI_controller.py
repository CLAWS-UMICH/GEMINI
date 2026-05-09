import math
import re
import sys
import time
from pathlib import Path

import socketio

from predictive_warning_system import processTelemetry

# Add the rover control source files to this module's import path.
CONTROLFILES_DIR = Path(__file__).with_name("controlfiles")
if str(CONTROLFILES_DIR) not in sys.path:
    sys.path.insert(0, str(CONTROLFILES_DIR))

from dumbdrive import drive_to_goal, make_sanitized_telemetry
from dumblocate import (
    LAST_KNOWN_GOAL_REACHED_CM,
    SECOND_TRILOCATION_STRONG_PING_THRESHOLD,
    TRILATERATION_ROUNDS,
    raw_world_m_to_local_cm,
    run_trilateration_round,
    stop_then_try_sample_ping,
)
from main import parse_pose, plan_path_for_following, create_planner, stop_rover
from rover_control import (
    close_rover_socket,
    configure_remote_server,
    fetch_ltv_json,
    fetch_rover_json,
    open_rover_socket,
    set_lights,
    wait_for_dust,
)


# Initialize socket client for compatibility with older Socket.IO call sites.
sio = socketio.Client()


# -----------------------------
# MAIN AI CONTROLLER
# -----------------------------
class PRController:
    def __init__(self, remote_url: str | None = None):
        self.connected = False
        self.current_path = []
        self.lkp = None
        self.rover_pos = (0, 0)
        self.ping_budget = 10
        self.ltv_found = False
        self.timestamp = 0
        self.remote_url = remote_url
        self.sock = None
        self.run_state = None

        self.tss_json = {}
        self.ltv_json = {}

        self.warnings = []

    # -----------------------------
    # STEP 1: CONNECT TO INFRA
    # -----------------------------
    def connect_to_infra(self, timeout_seconds: float = 20.0):
        # Defaults to direct TSS/DUST UDP. Passing remote_url switches rover_control
        # into the remote Socket.IO bridge used by the PRCC backend.
        configure_remote_server(self.remote_url is not None, self.remote_url)
        self.sock = open_rover_socket()

        if not wait_for_dust(self.sock, timeout_seconds=timeout_seconds, poll_seconds=0.5):
            raise RuntimeError("DUST is not connected to TSS.")

        self.connected = True
        self.tss_json = fetch_rover_json(self.sock)
        print("Connected to simulation")

    # -----------------------------
    # STEP 2: GENERATE PATH TO LKP
    # -----------------------------
    def generate_path_to_lkp(self):
        # Fetch current TSS rover telemetry and LTV telemetry from the controlfiles
        # transport, then use the shared planner instead of the old straight-line mock.
        self._require_socket()
        self.tss_json = fetch_rover_json(self.sock)
        self.ltv_json = fetch_ltv_json(self.sock)

        location = self.ltv_json.get("location", {})
        last_known_x = float(location.get("last_known_x", 0.0))
        last_known_y = float(location.get("last_known_y", 0.0))
        goal_x, goal_y = raw_world_m_to_local_cm(last_known_x, last_known_y)

        telemetry = make_sanitized_telemetry(self.tss_json["pr_telemetry"])
        rover_x, rover_y, _z, _heading = parse_pose(telemetry)

        self.lkp = (goal_x, goal_y)
        self.rover_pos = (rover_x, rover_y)

        planner = create_planner(self.rover_pos, self.lkp)
        _raw_path, self.current_path = plan_path_for_following(planner, self.rover_pos, self.lkp)
        return self.current_path

    # -----------------------------
    # STEP 3: WARNING SYSTEM
    # -----------------------------
    def process_warnings(self, telemetry=None, estimated_path_time=None):
        """
        Process warnings using both instantaneous threshold checks and 
        predictive analysis based on resource trends.
        
        Parameters
        ----------
        telemetry : dict, optional
            Full telemetry object with 'pr_telemetry' key containing sensor readings.
            If omitted, uses the latest telemetry fetched by this controller.
        estimated_path_time : float, optional
            Estimated time (in timesteps) to complete the current path.
            If not provided, uses current remaining path length.
        """
        self.warnings = []
        if telemetry is not None:
            self.tss_json = telemetry
        if "pr_telemetry" not in self.tss_json:
            self.tss_json = {"pr_telemetry": self.tss_json}

        pr_telemetry = self.tss_json["pr_telemetry"]
        timestep = pr_telemetry.get(
            "rover_elapsed_time",
            self.tss_json.get("mission_elapsed_time", self.timestamp),
        )

        all_warnings = processTelemetry(self.tss_json, timestep)

        # If estimated_path_time is not provided, estimate it from current path.
        if estimated_path_time is None:
            estimated_path_time = self.estimate_path_completion_time()

        # Filter warnings to only include predictive failures that could occur
        # during path execution. Instantaneous warnings are always included.
        for warning in all_warnings:
            if warning["severity"] == "PREDICTIVE":
                # processTelemetry currently puts time-to-breach in the message.
                # Keep supporting an explicit field if the warning schema adds one.
                dt = warning.get("time_to_breach")
                if dt is None and "in ~" in warning.get("message", ""):
                    match = re.search(r"in ~([\d.]+) timesteps", warning["message"])
                    if match:
                        dt = float(match.group(1))
                if dt is None or dt <= estimated_path_time:
                    self.warnings.append(warning)
            else:
                self.warnings.append(warning)

        return self.warnings

    def estimate_path_completion_time(self, average_speed=1.0, timestep_duration=0.2):
        """
        Estimate the time (in timesteps) to complete the current path.
        
        Parameters
        ----------
        average_speed : float
            Estimated average speed of the rover in distance units per timestep.
        timestep_duration : float
            Kept for backward compatibility with the earlier controller API.
        
        Returns
        -------
        float
            Estimated number of timesteps to complete path.
        """
        if not self.current_path:
            return 0.0

        # Calculate total distance remaining.
        current_pos = self.rover_pos
        total_distance = 0.0

        for waypoint in self.current_path:
            distance = math.dist(current_pos, waypoint)
            total_distance += distance
            current_pos = waypoint

        if average_speed <= 0:
            return float("inf")

        # Estimate time in timesteps (distance / speed per timestep).
        return total_distance / average_speed

    # -----------------------------
    # STEP 4: NAVIGATION LOOP
    # -----------------------------
    def navigate_to_lkp(self, tss_json=None):
        # The old loop emitted throttle/steering directly and simulated movement.
        # The controlfiles drive loop now owns path following, obstacle handling,
        # recovery behavior, and TSS command output.
        self._require_socket()
        if self.lkp is None:
            self.generate_path_to_lkp()

        print("Starting navigation to LKP")
        self.run_state = drive_to_goal(
            self.sock,
            goal_xy=self.lkp,
            display_goal_xy=self.lkp,
            goal_label="LTV last known position",
            viewer=None,
            frontend_enabled=False,
            recorded_obstacle_points=[],
            obstacle_total=0,
            start_time=None,
            step_idx=0,
            total_traveled_cm=0.0,
            goals_reached=0,
            goal_reached_cm=LAST_KNOWN_GOAL_REACHED_CM,
            debug_logger=None,
            debug_mode="ai_controller_drive_lkp",
        )
        self.rover_pos = (self.run_state.pose_xyzh[0], self.run_state.pose_xyzh[1])
        self.tss_json = {"pr_telemetry": self.run_state.raw_telemetry}
        print("Reached LKP" if self.run_state.reached_goal else "Navigation stopped before LKP")
        return self.run_state

    # -----------------------------
    # STEP 5: LTV SEARCH (PING)
    # -----------------------------
    def search_for_ltv(self):
        # Use dumblocate's ping/trilateration flow instead of the previous
        # signal-biased random walk. It still runs headless and sends commands
        # through the same rover_control socket.
        self._require_socket()
        if self.run_state is None:
            self.navigate_to_lkp()

        print("Starting LTV search...")
        set_lights(self.sock, True)
        current_anchor_xy = self.run_state.goal_xy

        for round_config in TRILATERATION_ROUNDS:
            if self.ping_budget <= 0:
                break

            estimate_xy_m, self.run_state, _viewer, ok = run_trilateration_round(
                self.sock,
                round_config=round_config,
                anchor_xy=current_anchor_xy,
                run_state=self.run_state,
                viewer=None,
                telemetry_callback=None,
                debug_logger=None,
            )
            self.ping_budget = max(0, self.ping_budget - 3)
            if not ok or self.run_state.aborted or estimate_xy_m is None:
                break

            final_ping, ok = stop_then_try_sample_ping(
                self.sock,
                viewer=None,
                run_state=self.run_state,
                status="Stopping for estimate ping...",
                telemetry_callback=None,
                debug_logger=None,
                debug_mode="ai_controller_hold_verify_estimate",
            )
            self.ping_budget = max(0, self.ping_budget - 1)
            if not ok:
                break
            if final_ping is not None:
                print(f"Signal strength: {final_ping.ping_value}")
                if final_ping.ping_value >= SECOND_TRILOCATION_STRONG_PING_THRESHOLD:
                    self.ltv_found = True
                    print("LTV search drive complete")
                    break

            current_anchor_xy = raw_world_m_to_local_cm(*estimate_xy_m)

        self.rover_pos = (self.run_state.pose_xyzh[0], self.run_state.pose_xyzh[1])
        return self.run_state

    # -----------------------------
    # HELPERS
    # -----------------------------
    def generate_straight_path(self, start, goal):
        # Backward-compatible helper for tests or callers that still want a
        # simple path. Navigation uses the shared planner now.
        path = []
        steps = 10

        dx = (goal[0] - start[0]) / steps
        dy = (goal[1] - start[1]) / steps

        for i in range(1, steps + 1):
            path.append((start[0] + dx * i, start[1] + dy * i))

        return path

    def recalculate_path(self, start, goal):
        # Recalculate with the same planner used by the controlfiles drive loop.
        planner = create_planner(start, goal)
        _raw_path, path = plan_path_for_following(planner, start, goal)
        return path

    def compute_controls(self, current, target):
        # Backward-compatible wrapper around the shared drive command logic.
        from main import choose_drive_command

        throttle, steering, _desired_heading, _heading_error = choose_drive_command(
            current[0], current[1], 0.0, target[0], target[1]
        )
        return throttle, steering, False

    def detect_obstacle(self):
        # Obstacle detection is handled inside dumbdrive from live lidar.
        return False

    def at_position(self, pos1, pos2, threshold=1.0):
        return math.dist(pos1, pos2) < threshold

    def estimate_direction_from_signal(self, strength):
        # Direction estimation is handled by dumblocate trilateration.
        return (0.0, 0.0)

    def close(self):
        if self.sock is not None:
            stop_rover(self.sock)
            close_rover_socket(self.sock)
            self.sock = None

    def _require_socket(self):
        if self.sock is None:
            self.connect_to_infra()


if __name__ == "__main__":
    # Optional first CLI argument: remote PRCC Socket.IO URL. If omitted, control
    # defaults to direct TSS/DUST UDP through rover_control.py.
    remote_url = sys.argv[1] if len(sys.argv) > 1 else None

    # Initialize controller.
    controller = PRController(remote_url=remote_url)
    try:
        # Step 1: Connect to infra and wait for simulation to start.
        controller.connect_to_infra()

        # Step 2: Generate path to LKP.
        controller.generate_path_to_lkp()

        # Step 3: Process warnings before navigation and print them if any.
        warnings = controller.process_warnings()
        if warnings:
            print(f"Warnings: {warnings}")

        # Step 4: Navigate to LKP.
        controller.navigate_to_lkp()

        # Step 5: Search for LTV using ping/trilateration.
        controller.search_for_ltv()
    finally:
        controller.close()

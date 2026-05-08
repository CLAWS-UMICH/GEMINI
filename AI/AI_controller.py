import socketio
import time
import math
import random
from flask_socketio import SocketIO, emit

from predictive_warning_system import processTelemetry

# Initialize socket
sio = socketio.Client()

# -----------------------------
# MAIN AI CONTROLLER
# -----------------------------
class PRController:
    def __init__(self):
        self.connected = False
        self.current_path = []
        self.lkp = None
        self.rover_pos = (0, 0)
        self.ping_budget = 10
        self.ltv_found = False
        self.timestamp = 0

        self.tss_json = {}
        self.ltv_json = {}

        self.warnings = []

    # -----------------------------
    # STEP 1: CONNECT TO INFRA
    # -----------------------------
    def connect_to_infra(self):
        while not self.connected:
            sio.emit("rover-telemetry", self.tss_json, self.timestamp)

            sim_running = self.tss_json["pr_telemetry"]["sim_running"]
            dust_connected = self.tss_json["pr_telemetry"]["dust_connected"]

            if sim_running and dust_connected:
                self.connected = True
                print("Connected to simulation")
            else:
                print("Waiting for infra...")
                time.sleep(1)

    # -----------------------------
    # STEP 2: GENERATE PATH TO LKP
    # -----------------------------
    def generate_path_to_lkp(self):
        last_known_x = self.ltv_json["location"]["last_known_x"]
        last_known_y = self.ltv_json["location"]["last_known_y"]

        rover_x = self.tss_json["pr_telemetry"]["rover_pos_x"]
        rover_y = self.tss_json["pr_telemetry"]["rover_pos_y"]

        self.lkp = (last_known_x, last_known_y)
        self.rover_pos = (rover_x, rover_y)

        # FIXME: Replace with Sam's pathfinding
        # Simple straight-line path (replace with A*)
        self.current_path = self.generate_straight_path(self.rover_pos, self.lkp)

        # Send path to infra for visualization
        sio.emit("matrix", self.current_path)

    # -----------------------------
    # STEP 3: WARNING SYSTEM
    # -----------------------------
    def process_warnings(self, estimated_path_time=None):
        """
        Process warnings using both instantaneous threshold checks and 
        predictive analysis based on resource trends.
        
        Parameters
        ----------
        telemetry : dict
            Full telemetry object with 'pr_telemetry' key containing sensor readings
        estimated_path_time : float, optional
            Estimated time (in timesteps) to complete the current path.
            If not provided, uses current remaining path length.
        """
        self.warnings = []
        
        # Extract timestep from telemetry
        timestep = self.tss_json["pr_telemetry"].get("rover_elapsed_time", self.timestamp)
        
        # Use processTelemetry to get all warnings (both instantaneous and predictive)
        all_warnings = processTelemetry(self.tss_json, timestep)
        
        # If estimated_path_time not provided, estimate it from current path
        if estimated_path_time is None:
            estimated_path_time = self.estimate_path_completion_time()
        
        # Filter warnings to only include those that could occur during path execution
        for warning in all_warnings:
            if warning["severity"] == "PREDICTIVE":
                # For predictive warnings, check if the breach will occur before path completes
                dt = warning.get("time_to_breach")
                
                # If the warning doesn't have explicit time_to_breach, extract from message
                # (This is a safety check since time_to_breach isn't in the current schema)
                if dt is None and "in ~" in warning.get("message", ""):
                    try:
                        import re
                        match = re.search(r"in ~([\d.]+) timesteps", warning["message"])
                        if match:
                            dt = float(match.group(1))
                    except:
                        pass
                
                # Include warning if it occurs before or during path completion
                if dt is not None and dt <= estimated_path_time:
                    self.warnings.append(warning)
                elif dt is None:
                    # If we can't parse timing, include it to be safe
                    self.warnings.append(warning)
            else:
                # Always include instantaneous warnings
                self.warnings.append(warning)
        
        return self.warnings
    
    def estimate_path_completion_time(self, average_speed=1.0, timestep_duration=0.2):
        """
        Estimate the time (in timesteps) to complete the current path.
        
        Parameters
        ----------
        average_speed : float
            Estimated average speed of the rover in distance units per timestep
        timestep_duration : float
            Duration of each timestep in seconds (default 0.2s matches navigate_to_lkp)
        
        Returns
        -------
        float : Estimated number of timesteps to complete path
        """
        if not self.current_path:
            return 0.0
        
        # Calculate total distance remaining
        current_pos = self.rover_pos
        total_distance = 0.0
        
        for waypoint in self.current_path:
            distance = math.dist(current_pos, waypoint)
            total_distance += distance
            current_pos = waypoint
        
        # Estimate time in timesteps (distance / speed per timestep)
        if average_speed <= 0:
            return float('inf')
        
        timesteps_needed = total_distance / average_speed
        return timesteps_needed

    # -----------------------------
    # STEP 4: NAVIGATION LOOP
    # -----------------------------
    def navigate_to_lkp(self, tss_json):
        print("Starting navigation to LKP")

        while not self.at_position(self.rover_pos, self.lkp):
            # FIXME: Replace with Sam's pathfinding and control logic here

            # Follow next waypoint
            if not self.current_path:
                break

            next_wp = self.current_path.pop(0)

            throttle, steering, brakes = self.compute_controls(self.rover_pos, next_wp)

            sio.emit("rover-throttle", throttle)
            sio.emit("rover-steering", steering)
            sio.emit("rover-brakes", brakes)

            # Simulate movement
            self.rover_pos = next_wp

            sio.emit("rover-telemetry", tss_json)
            self.tss_json = tss_json["pr_telemetry"]

            # Obstacle detection (mock LIDAR)
            if self.detect_obstacle():
                print("Obstacle detected! Replanning...")

                self.current_path = self.recalculate_path(self.rover_pos, self.lkp)
                sio.emit("matrix", self.current_path)

                # Process warnings with full telemetry object
                self.process_warnings(self.tss_json)
                if self.warnings:
                    sio.emit("warnings", self.warnings)

                continue

            time.sleep(0.2)

        print("Reached LKP")

    # -----------------------------
    # STEP 5: LTV SEARCH (PING)
    # -----------------------------
    def search_for_ltv(self):
        print("Starting LTV search...")

        while not self.ltv_found and self.ping_budget > 0:
            # TODO: May need to check cooldown for ping (may be unnecesary given actual system)
            # Ping
            sio.emit("rover-ping")
            self.ping_budget -= 1

            # Receive LTV signal strength
            sio.emit("ltv-telemetry", self.ltv_json, self.timestamp)
            signal_strength = self.ltv_json["signal"]["strength"]
            print(f"Signal strength: {signal_strength}")

            # TODO: Update path given signal strength
            direction = self.estimate_direction_from_signal(signal_strength)

            # Move rover
            next_pos = (
                self.rover_pos[0] + direction[0],
                self.rover_pos[1] + direction[1]
            )

            self.rover_pos = next_pos

            sio.emit("rover-steering", direction[0])
            sio.emit("rover-throttle", 0.5)

            # Check if found
            if signal_strength > -5.0:  # FIXME: Threshold for "found" (needs tuning)
                self.ltv_found = True
                print("LTV FOUND!")

            time.sleep(0.5)

        if not self.ltv_found:
            print("Ping budget exhausted")

    # -----------------------------
    # HELPERS
    # -----------------------------
    def generate_straight_path(self, start, goal):
        path = []
        steps = 10

        dx = (goal[0] - start[0]) / steps
        dy = (goal[1] - start[1]) / steps

        for i in range(1, steps + 1):
            path.append((start[0] + dx * i, start[1] + dy * i))

        return path

    def recalculate_path(self, start, goal):
        print("Recalculating path...")
        return self.generate_straight_path(start, goal)

    def compute_controls(self, current, target):
        dx = target[0] - current[0]
        dy = target[1] - current[1]

        steering = max(min(dx * 0.1, 1), -1)
        throttle = 0.5
        brakes = 0

        return throttle, steering, brakes

    def detect_obstacle(self):
        return random.random() < 0.1  # 10% chance

    def at_position(self, pos1, pos2, threshold=1.0):
        return math.dist(pos1, pos2) < threshold

    def estimate_direction_from_signal(self, strength):
        # Random exploration + bias
        return (random.uniform(-1, 1), random.uniform(-1, 1))


# -----------------------------
# RUN SCRIPT
# -----------------------------
if __name__ == "__main__":
    # Connect socket
    sio.connect("http://35.2.123.225:5001")

    # Initialize controller
    controller = PRController()

    # Step 1: Connect to infra and wait for simulation to start
    controller.connect_to_infra()

    # Step 2: Generate path to LKP
    sio.emit("ltv-telemetry", controller.ltv_json, controller.timestamp)
    controller.generate_path_to_lkp()

    # Step 3: Process warnings before navigation and send to infra (if any)
    controller.process_warnings(controller.tss_json)
    if controller.warnings:
        sio.emit("warnings", controller.warnings)

    # Step 4: Navigate to LKP
    controller.navigate_to_lkp(controller.tss_json)

    # Step 5: Search for LTV using ping
    controller.search_for_ltv()
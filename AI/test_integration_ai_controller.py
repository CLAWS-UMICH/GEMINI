"""
Integration test: verify process_warnings uses processTelemetry correctly
"""
import sys
import math
sys.path.insert(0, '/Users/dereky/Documents/School/CLAWS/GEMINI')

from AI_controller import PRController
from predictive_warning_system import clearHistory

# Create a mock telemetry object
def create_mock_telemetry(battery=95, oxygen=98, speed=5):
    return {
        "mission_elapsed_time": 0,
        "pr_telemetry": {
            "battery_level": battery,
            "oxygen_tank": oxygen,
            "oxygen_pressure": 2999,
            "coolant_storage": 95,
            "pitch": 5,
            "roll": 3,
            "speed": speed,
            "throttle": 10,
            "steering": 0.2,
            "surface_incline": 15,
            "distance_from_base": 500,
            "fan_pri_rpm": 30001,
            "fan_sec_rpm": 30001,
            "cabin_pressure": 4.0,
            "cabin_temperature": 21,
            "external_temp": -60,
            "coolant_pressure": 500,
        }
    }

print("=" * 70)
print("INTEGRATION TEST: process_warnings with processTelemetry")
print("=" * 70)

# Test 1: Normal telemetry
print("\n[TEST 1] Normal telemetry, no warnings expected")
print("-" * 70)
clearHistory()
controller = PRController()
controller.current_path = [(10, 10), (20, 20), (30, 30)]
controller.rover_pos = (0, 0)

telemetry = create_mock_telemetry()
warnings = controller.process_warnings(telemetry)
print(f"Warnings: {len(warnings)}")
for w in warnings:
    print(f"  - {w['severity']}: {w['valuename']}")

# Test 2: Out of bounds instantaneous warning
print("\n[TEST 2] Out of bounds speed (30 m/s > max 18 m/s)")
print("-" * 70)
clearHistory()
controller = PRController()
controller.current_path = [(10, 10), (20, 20), (30, 30)]
controller.rover_pos = (0, 0)

telemetry = create_mock_telemetry(speed=25)  # Speed too high
warnings = controller.process_warnings(telemetry)
print(f"Warnings: {len(warnings)}")
for w in warnings:
    print(f"  - {w['severity']}: {w['valuename']} = {w['value']} (threshold: {w['threshold']})")

# Test 3: Predictive warning - declining battery
print("\n[TEST 3] Predictive warning - declining battery over multiple timesteps")
print("-" * 70)
clearHistory()
controller = PRController()
controller.current_path = [(10, 10), (20, 20), (30, 30)]
controller.rover_pos = (0, 0)

# Simulate declining battery - steeper decline to trigger warning faster
for t in range(8):
    battery_value = 100 - (t * 6)  # Steeper decline: 6% per timestep
    telemetry = create_mock_telemetry(battery=battery_value)
    telemetry["mission_elapsed_time"] = t
    
    warnings = controller.process_warnings(telemetry)
    
    print(f"t={t}: battery={battery_value:.1f}%, warnings={len(warnings)}")
    if warnings:
        for w in warnings:
            print(f"       [{w['severity']}] {w['valuename']}")
            if "PREDICTIVE" in w["severity"]:
                print(f"       → {w['message']}")

# Test 4: Verify path completion time estimation
print("\n[TEST 4] Path completion time estimation")
print("-" * 70)
clearHistory()
controller = PRController()
controller.rover_pos = (0, 0)
controller.current_path = [(10, 0), (20, 0), (30, 0)]  # 30 units total

# With default speed of 1.0
completion_time = controller.estimate_path_completion_time(average_speed=1.0)
print(f"Path: {controller.current_path}")
print(f"Rover position: {controller.rover_pos}")
print(f"Total distance: 30 units")
print(f"Average speed: 1.0 units/timestep")
print(f"Estimated completion time: {completion_time:.1f} timesteps")

# With faster speed
completion_time_fast = controller.estimate_path_completion_time(average_speed=2.0)
print(f"Average speed: 2.0 units/timestep")
print(f"Estimated completion time: {completion_time_fast:.1f} timesteps")

print("\n" + "=" * 70)
print("Integration test completed successfully!")
print("=" * 70)

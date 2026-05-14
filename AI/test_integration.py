"""
Test script to validate processTelemetry integration
"""
from predictive_warning_system import processTelemetry, getSlope, howLongUntilValue, clearHistory

# Test case 1: Normal telemetry with all values in nominal range
print("=" * 70)
print("TEST 1: Normal telemetry (all nominal)")
print("=" * 70)
clearHistory()

normal_telemetry = {
    "mission_elapsed_time": 0,
    "pr_telemetry": {
        "battery_level": 95,
        "oxygen_tank": 98,
        "oxygen_pressure": 2999,
        "coolant_storage": 95,
        "pitch": 5,
        "roll": 3,
        "speed": 10,
        "throttle": 50,
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

warnings = processTelemetry(normal_telemetry, 0)
print(f"Warnings: {len(warnings)}")
for w in warnings:
    print(f"  - {w['severity']}: {w['message']}")
print()

# Test case 2: Battery warning (out of bounds)
print("=" * 70)
print("TEST 2: Out of bounds telemetry (battery too low)")
print("=" * 70)
clearHistory()

low_battery_telemetry = {
    "mission_elapsed_time": 0,
    "pr_telemetry": normal_telemetry["pr_telemetry"].copy()
}
low_battery_telemetry["pr_telemetry"]["battery_level"] = 20
warnings = processTelemetry(low_battery_telemetry, 0)
print(f"Warnings: {len(warnings)}")
for w in warnings:
    print(f"  - {w['severity']}: {w['message']}")
print()

# Test case 3: Predictive warning - declining resource
print("=" * 70)
print("TEST 3: Predictive warning (declining battery)")
print("=" * 70)
clearHistory()

# Simulate battery declining over time
test_telemetry = {
    "mission_elapsed_time": 0,
    "pr_telemetry": normal_telemetry["pr_telemetry"].copy()
}

print("Recording declining battery over 15 timesteps...")
for t in range(15):
    # Battery declines by 3% per timestep
    battery_value = 100 - (t * 3)
    test_telemetry["pr_telemetry"]["battery_level"] = battery_value
    test_telemetry["mission_elapsed_time"] = t
    
    warnings = processTelemetry(test_telemetry, t)
    
    if t % 3 == 0:
        slope = getSlope("battery_level")
        dt = howLongUntilValue("battery_level", 30)  # warn at 30%
        slope_str = f"{slope:.2f}" if slope is not None else "N/A"
        dt_str = f"{dt:.1f}" if dt is not None else "N/A"
        print(f"t={t:2d}: battery={battery_value:5.1f}%, slope={slope_str}%/t, time_to_30%={dt_str}")
    
    if warnings:
        for w in warnings:
            if "PREDICTIVE" in w["severity"]:
                print(f"       ⚠  PREDICTIVE WARNING: {w['message']}")

print()
print("=" * 70)
print("All validation tests completed!")
print("=" * 70)

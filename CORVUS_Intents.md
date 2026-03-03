# CORVUS Intent Audit — TSS 2026

> Generated for CORVUS (NASA SUITS 2025–2026). Covers EVA spacesuit, Pressurized Rover (PR), and Lunar Terrain Vehicle (LTV) intents.
> Focus: PR and LTV are primary. EVA intents retained for spacesuit crew support.

---

## Legend

| Symbol | Meaning |
|--------|---------|
| 🔴 Critical | Safety-critical or mandatory scenario step |
| 🟠 High | Important operational utility |
| 🟡 Medium | Useful but not essential |
| 🟢 Low | Nice-to-have |
| 🆕 | Newly proposed intent for TSS 2026 |

---

## 1. Legacy EVA Intents

### 1a. Menu / UI

| Intent | Priority | Description |
|--------|----------|-------------|
| `open_menu_vitals` | 🔴 Critical | Opens the EVA suit vitals dashboard displaying life support telemetry |
| `open_menu_navigation` | 🔴 Critical | Opens the navigation panel showing 2D map, waypoints, and route |
| `open_menu_tasks` | 🔴 Critical | Opens the task/checklist panel for EVA procedure management |
| `open_menu_uia` | 🔴 Critical | Opens the UIA (Umbilical Interface Assembly) panel for egress/ingress procedures |
| `open_menu_messaging` | 🟠 High | Opens the messaging panel for LMCC/IVA communication |
| `open_menu_geosamples` | 🟡 Medium | Opens the geological samples tracking panel |
| `open_menu_rover` | 🟠 High | Opens the pressurized rover status monitoring panel |
| `open_menu_voice_assistant` | 🟡 Medium | Opens the CORVUS voice assistant settings or help panel |
| `close_menu` | 🟠 High | Closes the currently active menu or panel |
| `undo` | 🟡 Medium | Reverts the last action taken in the UI |
| `get_warnings` | 🔴 Critical | Retrieves active caution and warning alerts for the EVA crew member |

### 1b. Navigation

| Intent | Priority | Description |
|--------|----------|-------------|
| `Set_navigation_target` | 🔴 Critical | Sets a destination for the EVA crew member's navigation route |
| `reroute_navigation` | 🟠 High | Recalculates the navigation route, e.g. to avoid a hazard |
| `Get_coordinates` | 🟠 High | Retrieves the current GPS/IMU coordinates of the astronaut |
| `Add_waypoint` | 🟠 High | Adds a named waypoint to the navigation map |
| `Delete_waypoint` | 🟡 Medium | Removes a named waypoint from the navigation map |

### 1c. Task Management

| Intent | Priority | Description |
|--------|----------|-------------|
| `Add_task` | 🟡 Medium | Adds a new task item to the EVA checklist |
| `Complete_task` | 🟡 Medium | Marks a specified task as completed on the checklist |
| `Delete_task` | 🟢 Low | Removes a task item from the EVA checklist |

### 1d. Procedures

| Intent | Priority | Description |
|--------|----------|-------------|
| `start_procedure_uia_egress` | 🔴 Critical | Initiates the UIA egress procedure checklist for exiting the airlock |
| `start_procedure_uia_ingress` | 🔴 Critical | Initiates the UIA ingress procedure checklist for re-entering the airlock |
| `start_procedure_erm` | 🔴 Critical | Initiates the Exit Recovery Mode procedure for LTV repair |
| `start_procedure_system_diagnosis` | 🔴 Critical | Initiates the LTV system diagnosis procedure |
| `start_procedure_system_restart` | 🔴 Critical | Initiates the LTV nav system restart procedure |
| `start_procedure_physical_repair_task` | 🔴 Critical | Initiates the physical repair procedure (bus connector reconnection) |
| `start_procedure_final_system_checks` | 🟠 High | Initiates the final system checks procedure after LTV repair |

### 1e. Suit Vitals Queries

| Intent | Priority | Description |
|--------|----------|-------------|
| `vitals_heart_rate` | 🔴 Critical | Queries the astronaut's current heart rate (bpm) |
| `vitals_temperature` | 🔴 Critical | Queries the current suit internal temperature |
| `vitals_oxy_pri_storage` | 🔴 Critical | Queries primary oxygen tank storage level (%) |
| `vitals_oxy_sec_storage` | 🔴 Critical | Queries secondary oxygen tank storage level (%) |
| `vitals_oxy_pri_pressure` | 🔴 Critical | Queries primary oxygen tank pressure (psi) |
| `vitals_oxy_sec_pressure` | 🔴 Critical | Queries secondary oxygen tank pressure (psi) |
| `vitals_suit_pressure_total` | 🔴 Critical | Queries total suit pressure |
| `vitals_suit_pressure_oxy` | 🟠 High | Queries the oxygen component of suit pressure |
| `vitals_suit_pressure_co2` | 🟠 High | Queries the CO2 component of suit pressure |
| `vitals_suit_pressure_other` | 🟡 Medium | Queries the other/trace gas component of suit pressure |
| `vitals_helmet_pressure_co2` | 🔴 Critical | Queries CO2 pressure inside the helmet — critical safety metric |
| `vitals_fan_pri_rpm` | 🟠 High | Queries primary fan speed (RPM) for life support circulation |
| `vitals_fan_sec_rpm` | 🟠 High | Queries secondary fan speed (RPM) for life support circulation |
| `vitals_scrubber_a_co2_storage` | 🟠 High | Queries CO2 scrubber A storage capacity remaining (%) |
| `vitals_scrubber_b_co2_storage` | 🟠 High | Queries CO2 scrubber B storage capacity remaining (%) |
| `vitals_coolant_storage` | 🟠 High | Queries coolant fluid storage level (%) |
| `vitals_coolant_gas_pressure` | 🟡 Medium | Queries coolant gas pressure |
| `vitals_coolant_liquid_pressure` | 🟡 Medium | Queries coolant liquid pressure |
| `vitals_oxy_consumption` | 🟠 High | Queries current oxygen consumption rate |
| `vitals_co2_production` | 🟠 High | Queries current CO2 production rate |
| `vitals_oxy_time_left` | 🔴 Critical | Queries predicted time remaining on oxygen supply |
| `vitals_batt_time_left` | 🔴 Critical | Queries predicted time remaining on suit battery |

---

## 2. PR Telemetry Intents — New for TSS 2026

### 2a. Cabin Environment Controls

| Intent | Priority | Description |
|--------|----------|-------------|
| `get_cabin_heating` | 🟠 High | Queries whether cabin heating is currently active (on/off) |
| `set_cabin_heating` | 🟠 High | Toggles cabin heating on or off |
| `get_cabin_cooling` | 🟠 High | Queries whether cabin cooling is currently active (on/off) |
| `set_cabin_cooling` | 🟠 High | Toggles cabin cooling on or off |
| `get_co2_scrubber` | 🔴 Critical | Queries whether the rover CO2 scrubber is active (on/off) |
| `set_co2_scrubber` | 🔴 Critical | Toggles the rover CO2 scrubber on or off |
| `get_lights_on` | 🟡 Medium | Queries whether rover exterior lights are on (true/false) — relevant for night ops |
| `set_lights_on` | 🟡 Medium | Toggles rover exterior lights on or off |

### 2b. Driving & Motion State

| Intent | Priority | Description |
|--------|----------|-------------|
| `get_throttle` | 🟡 Medium | Queries the current throttle value of the pressurized rover |
| `get_steering` | 🟢 Low | Queries the current steering angle of the pressurized rover |
| `get_speed` | 🟠 High | Queries the rover's current speed — important for driving safety |
| `get_surface_incline` | 🟠 High | Queries the current terrain incline angle — tipping hazard awareness |
| `get_heading` 🆕 | 🟠 High | Queries the rover's current compass heading/bearing |
| `get_distance_traveled` | 🟡 Medium | Queries total distance traveled by the rover in the current session |
| `get_distance_from_base` | 🔴 Critical | Queries the rover's current distance from base — critical for range/return planning |
| `get_sunlight` | 🟡 Medium | Queries the current sunlight level — relevant for power and visibility planning |

### 2c. Rover Position

| Intent | Priority | Description |
|--------|----------|-------------|
| `get_rover_position` | 🟠 High | Queries the rover's current 2D/3D position as a combined coordinate |

### 2d. Rover Life Support & Systems

| Intent | Priority | Description |
|--------|----------|-------------|
| `get_oxygen_tank` | 🔴 Critical | Queries rover oxygen tank level (%) |
| `get_oxygen_pressure` | 🔴 Critical | Queries rover oxygen pressure |
| `get_fan_pri_rpm` | 🟠 High | Queries rover primary fan speed (RPM) |
| `get_fan_sec_rpm` | 🟠 High | Queries rover secondary fan speed (RPM) |
| `get_cabin_pressure` | 🔴 Critical | Queries rover cabin pressure — crew safety critical |
| `get_cabin_temperature` | 🟠 High | Queries rover cabin temperature |
| `get_battery_level` | 🔴 Critical | Queries rover battery charge level (%) |
| `get_external_temp` | 🟡 Medium | Queries the external (lunar surface) temperature |
| `get_coolant_pressure` | 🟠 High | Queries rover coolant system pressure |
| `get_coolant_storage` | 🟠 High | Queries rover coolant fluid storage level |
| `get_rover_elapsed_time` | 🟠 High | Queries how long the rover has been operational in the current EVA |

---

## 3. LTV Telemetry Intents — New for TSS 2026

### 3a. Location & Signal

| Intent | Priority | Description |
|--------|----------|-------------|
| `get_last_known_position` | 🔴 Critical | Retrieves the LTV's last known coordinates — primary input for search pattern |
| `get_signal_strength` | 🔴 Critical | Queries the current LTV beacon signal strength — used to narrow search radius |
| `get_signal_pings_left` | 🟠 High | Queries how many signal pings remain available to locate the LTV |
| `ping_ltv` 🆕 | 🔴 Critical | Actively sends a signal ping to the LTV to request a wake-up/location beacon |

### 3b. LTV Error States

| Intent | Priority | Description |
|--------|----------|-------------|
| `get_errors_recovery_mode` | 🔴 Critical | Queries whether the LTV is currently in recovery/sleep mode |
| `get_errors_dust_sensor` | 🟠 High | Queries whether the LTV dust sensor is reporting an error (optional repair task) |
| `get_errors_power_distribution` | 🔴 Critical | Queries whether the LTV power distribution system has an error |
| `get_errors_nav_system` | 🔴 Critical | Queries whether the LTV navigation system has an error — nav restart is mandatory |
| `get_errors_electronic_heater` | 🟠 High | Queries whether the LTV electronic heater is reporting an error |
| `get_errors_comms` | 🔴 Critical | Queries whether the LTV communications system has an error |
| `get_errors_fuse` | 🟠 High | Queries whether the LTV fuse has blown or is reporting an error |

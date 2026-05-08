//########### ROVER.json DATA SHAPE ###########//

interface PrTelemetryData {
  cabin_heating: boolean;
  cabin_cooling: boolean;
  lights_on: boolean;
  brakes: boolean;
  throttle: number;
  steering: number;
  rover_pos_x: number;
  rover_pos_y: number;
  rover_pos_z: number;
  heading: number;
  pitch: number;
  roll: number;
  distance_traveled: number;
  speed: number;
  sunlight: number;
  surface_incline: number;
  lidar: number[];
  oxygen_storage: number;
  oxygen_pressure: number;
  cabin_pressure: number;
  cabin_temperature: number;
  external_temp: number;
  coolant_pressure: number;
  coolant_storage: number;
  primary_battery_level: number;
  secondary_battery_level: number;
  rover_elapsed_time: number;
  sim_running: boolean;
  dust_connected: boolean;
  distance_from_base: number;
  oxygen_tank: number;
  battery_level: number;
  fan_pri_rpm: number;
  fan_sec_rpm: number;
  scrubber_a_co2_storage: number;
  scrubber_b_co2_storage: number;
  cabin_temperature_target: number;
}

export interface RoverData {
  pr_telemetry: PrTelemetryData;
}
//########### EVA.json DATA SHAPE ###########//

// EVA telemetry data
interface EvaTelemetryData {
  primary_battery_level?:	number
  secondary_battery_level?:	number
  battery_level?: number
  oxy_pri_storage:	number
  oxy_sec_storage:	number
  oxy_pri_pressure:	number
  oxy_sec_pressure:	number
  suit_pressure_oxy:	number
  suit_pressure_co2:	number
  suit_pressure_other:	number
  suit_pressure_total:	number
  helmet_pressure_co2:	number
  fan_pri_rpm:	number
  fan_sec_rpm:	number
  scrubber_a_co2_storage:	number
  scrubber_b_co2_storage:	number
  temperature:	number
  coolant_storage:	number
  coolant_gas_pressure:	number
  coolant_liquid_pressure:	number
  heart_rate:	number
  oxy_consumption:	number
  co2_production:	number
  eva_elapsed_time:	number
}

// DCU data

interface DcuBatt {
  lu?: boolean
  ps?: boolean
}

interface EvaDcu1Data {
  oxy?: boolean
  fan?: boolean
  pump?: boolean
  co2?: boolean
  batt?: DcuBatt
}

interface EvaDcu2Data {
  batt?: boolean
  oxy?: boolean
  comm?: boolean
  fan?: boolean
  pump?: boolean
  co2?: boolean
}

interface EvaImuData {
    posx: number
    posy: number
    heading: number
}

interface EvaUiaData {
  eva1_power?: boolean
  eva1_oxy?: boolean
  eva1_water_supply?: boolean
  eva1_water_waste?: boolean
  eva2_power?: boolean
  eva2_oxy?: boolean
  eva2_water_supply?: boolean
  eva2_water_waste?: boolean
  oxy_vent?: boolean
  depress?: boolean
}


export interface EvaData {
  telemetry: {
    //eva_time: number
    eva1: EvaTelemetryData
    eva2: EvaTelemetryData
  }
  status: {
    started: boolean
  }
  dcu: {
    eva1: EvaDcu1Data
    eva2: EvaDcu2Data
  }
  error: {
    fan_error: boolean
    oxy_error: boolean
    power_error: boolean
    scrubber_error: boolean
  }
  imu: {
    eva1: EvaImuData
    eva2: EvaImuData
  }
  uia: EvaUiaData
  local_timestamp?: string
}
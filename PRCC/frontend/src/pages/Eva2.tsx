// pages/eva2.tsx
import { useSocket } from '../context/SocketContext'

export default function eva2Page() {
  const { evaData } = useSocket()

  return (
    <div>
      <h1>eva2 Telemetry</h1>
      <div>
        <div>Primary Battery Level: {evaData?.telemetry.eva2.primary_battery_level ?? 'N/A'}</div>
        <div>Secondary Battery Level: {evaData?.telemetry.eva2.secondary_battery_level ?? 'N/A'}</div>
        <div>Battery Level: {evaData?.telemetry.eva2.battery_level ?? 'N/A'}</div>
        <div>Oxygen Primary Storage: {evaData?.telemetry.eva2.oxy_pri_storage ?? 'N/A'}</div>
        <div>Oxygen Secondary Storage: {evaData?.telemetry.eva2.oxy_sec_storage ?? 'N/A'}</div>
        <div>Oxygen Primary Pressure: {evaData?.telemetry.eva2.oxy_pri_pressure ?? 'N/A'}</div>
        <div>Oxygen Secondary Pressure: {evaData?.telemetry.eva2.oxy_sec_pressure ?? 'N/A'}</div>
        <div>Suit Pressure O2: {evaData?.telemetry.eva2.suit_pressure_oxy ?? 'N/A'}</div>
        <div>Suit Pressure CO2: {evaData?.telemetry.eva2.suit_pressure_co2 ?? 'N/A'}</div>
        <div>Suit Pressure Other: {evaData?.telemetry.eva2.suit_pressure_other ?? 'N/A'}</div>
        <div>Suit Pressure Total: {evaData?.telemetry.eva2.suit_pressure_total ?? 'N/A'}</div>
        <div>Helmet Pressure CO2: {evaData?.telemetry.eva2.helmet_pressure_co2 ?? 'N/A'}</div>
        <div>Fan Primary RPM: {evaData?.telemetry.eva2.fan_pri_rpm ?? 'N/A'}</div>
        <div>Fan Secondary RPM: {evaData?.telemetry.eva2.fan_sec_rpm ?? 'N/A'}</div>
        <div>Scrubber A CO2 Storage: {evaData?.telemetry.eva2.scrubber_a_co2_storage ?? 'N/A'}</div>
        <div>Scrubber B CO2 Storage: {evaData?.telemetry.eva2.scrubber_b_co2_storage ?? 'N/A'}</div>
        <div>Temperature: {evaData?.telemetry.eva2.temperature ?? 'N/A'}</div>
        <div>Coolant Storage: {evaData?.telemetry.eva2.coolant_storage ?? 'N/A'}</div>
        <div>Coolant Gas Pressure: {evaData?.telemetry.eva2.coolant_gas_pressure ?? 'N/A'}</div>
        <div>Coolant Liquid Pressure: {evaData?.telemetry.eva2.coolant_liquid_pressure ?? 'N/A'}</div>
        <div>Heart Rate: {evaData?.telemetry.eva2.heart_rate ?? 'N/A'}</div>
        <div>Oxygen Consumption: {evaData?.telemetry.eva2.oxy_consumption ?? 'N/A'}</div>
        <div>CO2 Production: {evaData?.telemetry.eva2.co2_production ?? 'N/A'}</div>
        <div>EVA Elapsed Time: {evaData?.telemetry.eva2.eva_elapsed_time ?? 'N/A'}</div>
      </div>
    </div>
  )
}
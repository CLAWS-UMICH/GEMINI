import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Eva1Page from './pages/Eva1'
import Eva2Page from './pages/Eva2'
import RoverPage from './pages/Rover'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/eva1" element={<Eva1Page />} />
        <Route path="/eva2" element={<Eva2Page />} />
        <Route path="/rover" element={<RoverPage />} />
      </Routes>
    </BrowserRouter>
  )
}
















// import { useState, useEffect, useRef } from 'react'
// import { io, Socket } from 'socket.io-client'
// import type {RoverData, EvaData, LtvData, LtvErrorsData } from './types'
// const SOCKET_URL = 'http://localhost:5001'


// function App() {
//   const [roverData, setRoverData] = useState<RoverData | null>(null)
//   const [evaData, setEvaData] = useState<EvaData | null>(null)
//   const [ltvData, setLtvData] = useState<LtvData | null>(null)
//   const [ltvErrorsData, setLtvErrorsData] = useState<LtvErrorsData | null>(null)
//   const socketRef = useRef<Socket | null>(null)

//   useEffect(() => {
//     const socket = io(SOCKET_URL, {
//       transports: ['websocket', 'polling'],
//       reconnection: true,
//       reconnectionDelay: 1000,
//       reconnectionAttempts: 5
//     })
    
//     socket.on('connect', () => {
//       console.log('Socket.IO connected')
//     })

//     socket.on('rover-telemetry', (data: RoverData) => {
//       setRoverData(data)
//     })

//     socket.on('eva-telemetry', (data: EvaData) => {
//       setEvaData(data)
//     })

//     socket.on('ltv', (data: LtvData) => {
//       setLtvData(data)
//     })

//     socket.on('ltv-errors', (data: LtvErrorsData) => {
//       setLtvErrorsData(data)
//     })

//     socket.on('error', (errorData: { error: string; local_timestamp?: string }) => {
//       console.error('Error:', errorData.error)
//     })

//     socket.on('disconnect', () => {
//       console.log('Socket.IO disconnected')
//     })

//     socket.on('connect_error', (error: Error) => {
//       console.error('Connection error:', error)
//     })

//     socketRef.current = socket

//     return () => {
//       if (socketRef.current) {
//         socketRef.current.disconnect()
//       }
//     }
//   }, [])

// //   useEffect(() => {
// //   const socket = io(SOCKET_URL, {
// //     transports: ['websocket', 'polling'],
// //     reconnection: true,
// //     reconnectionDelay: 1000,
// //     reconnectionAttempts: 5,
// //   })

// //   const eventMap: Record<string, Function> = {
// //     'rover-telemetry': setRoverTelemetryData,
// //     'telemetry': setTelemetryData,
// //     'eva': setEvaStatusData,
// //     'dcu': setDcuData,
// //     'error': (data: any) => console.error('Error:', data.error),
// //   }

// //   Object.entries(eventMap).forEach(([event, handler]) => {
// //     socket.on(event, handler)
// //   })

// //   socketRef.current = socket

// //   return () => {
// //     socketRef.current?.disconnect()
// //   }
// // }, [])

//   const formatValue = (value: number | undefined): string => {
//     if (value === undefined || value === null) return 'N/A'
//     return typeof value === 'number' ? value.toFixed(2) : String(value)
//   }

//   const renderEvaData = (eva: EvaData | undefined, label: string) => {
//     if (!eva) return <div><h2>{label}</h2><div>No data available</div></div>
    
//     return (
//       <div>
//         <h2>{label}</h2>
//         <div>Battery Time Left: {formatValue(eva.batt_time_left)}</div>
//         <div>Oxygen Primary Storage: {formatValue(eva.oxy_pri_storage)}</div>
//         <div>Oxygen Secondary Storage: {formatValue(eva.oxy_sec_storage)}</div>
//         <div>Oxygen Primary Pressure: {formatValue(eva.oxy_pri_pressure)}</div>
//         <div>Oxygen Secondary Pressure: {formatValue(eva.oxy_sec_pressure)}</div>
//         <div>Oxygen Time Left: {eva.oxy_time_left ?? 'N/A'}</div>
//         <div>Heart Rate: {formatValue(eva.heart_rate)}</div>
//         <div>Oxygen Consumption: {formatValue(eva.oxy_consumption)}</div>
//         <div>CO2 Production: {formatValue(eva.co2_production)}</div>
//         <div>Suit Pressure O2: {formatValue(eva.suit_pressure_oxy)}</div>
//         <div>Suit Pressure CO2: {formatValue(eva.suit_pressure_co2)}</div>
//         <div>Suit Pressure Other: {formatValue(eva.suit_pressure_other)}</div>
//         <div>Suit Pressure Total: {formatValue(eva.suit_pressure_total)}</div>
//         <div>Fan Primary RPM: {formatValue(eva.fan_pri_rpm)}</div>
//         <div>Fan Secondary RPM: {formatValue(eva.fan_sec_rpm)}</div>
//         <div>Helmet Pressure CO2: {formatValue(eva.helmet_pressure_co2)}</div>
//         <div>Scrubber A CO2 Storage: {formatValue(eva.scrubber_a_co2_storage)}</div>
//         <div>Scrubber B CO2 Storage: {formatValue(eva.scrubber_b_co2_storage)}</div>
//         <div>Temperature: {formatValue(eva.temperature)}</div>
//         <div>Coolant ML: {formatValue(eva.coolant_ml)}</div>
//         <div>Coolant Gas Pressure: {formatValue(eva.coolant_gas_pressure)}</div>
//         <div>Coolant Liquid Pressure: {formatValue(eva.coolant_liquid_pressure)}</div>
//       </div>
//     )
//   }

//   return (
//     <div>
//       <h1>Telemetry Data</h1>
//       {telemetryData?.telemetry ? (
//         <div>
//           <div>EVA Time: {telemetryData.telemetry.eva_time ?? 'N/A'}</div>
//           {renderEvaData(telemetryData.telemetry.eva1, 'EVA1')}
//           {renderEvaData(telemetryData.telemetry.eva2, 'EVA2')}
//           {telemetryData.local_timestamp && (
//             <div>Last Update: {telemetryData.local_timestamp}</div>
//           )}
//         </div>
//       ) : (
//         <div>Waiting for data...</div>
//       )}
//     </div>
//   )
// }

// export default App

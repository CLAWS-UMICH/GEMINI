// context/SocketContext.tsx
import { createContext, useContext, useEffect, useRef, useState } from 'react'
import { io, Socket } from 'socket.io-client'
import type { RoverData, EvaData, LtvData, LtvErrorsData } from '../types'

interface SocketContextType {
  roverData: RoverData | null
  evaData: EvaData | null
  ltvData: LtvData | null
  ltvErrorsData: LtvErrorsData | null
}

const SocketContext = createContext<SocketContextType | null>(null)

export function SocketProvider({ children }: { children: React.ReactNode }) {
  const [roverData, setRoverData] = useState<RoverData | null>(null)
  const [evaData, setEvaData] = useState<EvaData | null>(null)
  const [ltvData, setLtvData] = useState<LtvData | null>(null)
  const [ltvErrorsData, setLtvErrorsData] = useState<LtvErrorsData | null>(null)
  const socketRef = useRef<Socket | null>(null)

  useEffect(() => {
    const socket = io('http://localhost:5001', {
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionAttempts: 5
    })

    socket.on('rover-telemetry', (data: RoverData) => setRoverData(data))
    socket.on('eva-telemetry', (data: EvaData) => setEvaData(data))
    socket.on('ltv-telemetry', (data: LtvData) => setLtvData(data))
    socket.on('ltv-errors-telemetry', (data: LtvErrorsData) => setLtvErrorsData(data))

    socketRef.current = socket
    return () => { socket.disconnect() }
  }, [])

  return (
    <SocketContext.Provider value={{ roverData, evaData, ltvData, ltvErrorsData }}>
      {children}
    </SocketContext.Provider>
  )
}

export function useSocket() {
  const context = useContext(SocketContext)
  if (!context) throw new Error('useSocket must be used within a SocketProvider')
  return context
}
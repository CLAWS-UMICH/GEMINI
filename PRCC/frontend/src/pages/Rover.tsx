// pages/Rover.tsx
import { useSocket } from '../context/SocketContext'
//import { useState, useRef } from 'react'
import { TransformWrapper, TransformComponent } from 'react-zoom-pan-pinch'
import mapImage from '../assets/dust-map.png'
import LeftPanel from '../components/LeftPanel'

const IMAGE_WIDTH = 2452
const IMAGE_HEIGHT = 1551

export default function RoverPage() {
  const { roverData } = useSocket()

  const scaleX = window.innerWidth / IMAGE_WIDTH
  const scaleY = window.innerHeight / IMAGE_HEIGHT
  const fitScale = Math.min(scaleX, scaleY)

  return (
    <div style={{ display: 'flex', width: '100vw', height: '100vh' }}>

      {/* Left Panel */}
      <LeftPanel />

      {/* Map - takes up remaining space */}
      <div style={{ flex: 1, overflow: 'hidden' }}>
        <TransformWrapper
          initialScale={fitScale}
          minScale={fitScale}
          maxScale={10}
          wheel={{ step: 0.1 }}
        >
          <TransformComponent wrapperStyle={{ width: '100%', height: '100%' }}>
            <div style={{ position: 'relative', width: IMAGE_WIDTH, height: IMAGE_HEIGHT }}>
              <img src={mapImage} alt="Rover Map" draggable={false} />
              {/* markers */}
            </div>
          </TransformComponent>
        </TransformWrapper>
      </div>


    </div>
  )
}
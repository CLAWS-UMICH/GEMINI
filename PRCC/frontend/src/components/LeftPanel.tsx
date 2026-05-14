// components/LeftPanel.tsx
//import { useSocket } from '../context/SocketContext'

export default function LeftPanel() {
  //const { roverData, ltvData } = useSocket()

  return (
    <div style={{
      width: 400,
      height: '100%',
      background: '#0a0a0a',
      color: 'white',
      padding: 16,
      flexShrink: 0,
      overflow: 'hidden',
      display: 'flex',
      flexDirection: 'column',
      gap: 24,
      fontFamily: 'sans-serif',
    }}>

      {/* Route Section */}
      <div>
        <h2 style={{ margin: '0 0 12px 0', fontSize: 16, fontWeight: 600 }}>Route</h2>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>

          {/* Timeline + Cards */}
          <div style={{ display: 'flex', gap: 8 }}>
            {/* Timeline dots */}
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', paddingTop: 20 }}>
              <div style={{ width: 10, height: 10, borderRadius: '50%', background: 'white' }} />
              <div style={{ width: 2, height: 45, background: '#444' }} />
              <div style={{ width: 10, height: 10, borderRadius: '50%', background: 'white' }} />
              <div style={{ width: 2, height: 45, borderLeft: '2px dashed #444', marginLeft: 2.4 }} />
              <div style={{ width: 10, height: 10, borderRadius: '50%', background: '#4488ff' }} />
            </div>

            {/* Route Cards */}
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8 }}>

              {/* The Hub */}
              <div style={{ background: '#1e1e1e', borderRadius: 8, padding: '10px 12px', display: 'flex', alignItems: 'center', gap: 10 }}>
                <div style={{ width: 28, height: 28, borderRadius: 6, background: '#3355ff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 13 }}>H</div>
                <span style={{ flex: 1, fontSize: 14 }}>The Hub</span>
                <span style={{ fontSize: 12, color: '#888' }}>∨</span>
              </div>

              {/* Automotive Vehicle */}
              <div style={{ background: '#1e1e1e', borderRadius: 8, padding: '10px 12px', display: 'flex', alignItems: 'center', gap: 10 }}>
                <div style={{ width: 28, height: 28, borderRadius: 6, background: '#cc8800', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 13 }}>L</div>
                <span style={{ flex: 1, fontSize: 14 }}>Automotive Vehicle (Last Seen)</span>
                <span style={{ fontSize: 12, color: '#888' }}>∨</span>
              </div>

              {/* Waypoint 1 - expanded */}
              <div style={{ background: '#1e1e1e', borderRadius: 8, padding: '10px 12px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                  <div style={{ width: 28, height: 28, borderRadius: 6, background: '#cc4400', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 13 }}>PR</div>
                  <span style={{ flex: 1, fontSize: 14, fontWeight: 600 }}>Waypoint 1</span>
                  <span style={{ fontSize: 12, color: '#888' }}>∧</span>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 13, color: '#ccc' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>&nbsp;&nbsp;&nbsp;&nbsp;Location</span>
                    <span style={{ color: 'white' }}>42.265869, -83.750031</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>&nbsp;&nbsp;&nbsp;&nbsp;Distance from PR</span>
                    <span style={{ color: 'white' }}>3 mi</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>&nbsp;&nbsp;&nbsp;&nbsp;Navigation time</span>
                    <span style={{ color: 'white' }}>14:21:12</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>&nbsp;&nbsp;&nbsp;&nbsp;Slope</span>
                    <span style={{ color: 'white' }}>Avg. 7.5°</span>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    <span>&nbsp;&nbsp;&nbsp;&nbsp;Notes</span>
                    <span style={{ color: 'white' }}>Example</span>
                  </div>
                  <button style={{
                    marginTop: 4,
                    background: '#3366ff',
                    color: 'white',
                    border: 'none',
                    borderRadius: 6,
                    padding: '8px 0',
                    fontSize: 14,
                    cursor: 'pointer',
                    width: '100%',
                  }}>
                    Sending Message ➤
                  </button>
                </div>
              </div>

            </div>
          </div>
        </div>
      </div>

      {/* Divider */}
      <div style={{ height: 1, background: '#333' }} />

      {/* PR Vitals Section */}
      <div>
        <h2 style={{ margin: '0 0 12px 0', fontSize: 16, fontWeight: 600 }}>PR Vitals</h2>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>

          {/* Automotive Vehicle */}
          <div style={{ background: '#1e1e1e', borderRadius: 8, padding: '10px 12px', display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ width: 28, height: 28, borderRadius: 6, background: '#cc8800', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 13 }}>L</div>
            <span style={{ flex: 1, fontSize: 14 }}>Automotive Vehicle</span>
            <span style={{ background: '#cc2222', color: 'white', fontSize: 11, padding: '2px 8px', borderRadius: 4 }}>Offline</span>
            <span style={{ fontSize: 12, color: '#888', marginLeft: 8 }}>∨</span>
          </div>

          {/* Pressurized Vehicle */}
          <div style={{ background: '#1e1e1e', borderRadius: 8, padding: '10px 12px', display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ width: 28, height: 28, borderRadius: 6, background: '#3355ff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 13 }}>P</div>
            <span style={{ flex: 1, fontSize: 14 }}>Pressurized Vehicle</span>
            <span style={{ fontSize: 12, color: '#888' }}>∨</span>
          </div>

        </div>
      </div>

    </div>
  )
}
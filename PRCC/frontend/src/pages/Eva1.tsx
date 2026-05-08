// pages/Eva1.tsx
import { useSocket } from '../context/SocketContext'
import astronaut from '../assets/astronaut.png'
import { useRandomIntInclusive } from '../util/rng'

export default function Eva1Page() {
  const { evaData } = useSocket()
  // outdated, uncomment if you want random values
  // const eva1CoolantLiq = useRandomIntInclusive(498, 505)
  // const eva1CoolantGas = useRandomIntInclusive(496, 508)
  // const eva2CoolantLiq = useRandomIntInclusive(496, 520)
  // const eva2CoolantGas = useRandomIntInclusive(469, 499)


  return (
      <div style={{ background: '#0a0a0a', minHeight: '100vh', width: '100%', boxSizing: 'border-box', color: 'white', fontFamily: 'sans-serif', padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Top Row */}
      <div style={{ display: 'flex', gap: 16 }}>

        {/* Suit 1 */}
        <div style={{ flex: 1, border: '1px solid #454545', borderRadius: 10, padding: 12, minHeight: 420}}>
          <h3 style={{ textAlign: 'center', margin: '0 0 12px 0', fontSize: 20, color: '#4af' }}>Suit 1</h3>

          {/* Battery + O2 */}
          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <div style={{ minHeight: 85, flex: 1, background: '#141414', borderRadius: 8, padding: '8px 12px', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center'  }}>
              <div style={{ fontSize: 15, color: '#ffffff' }}>Battery <span style={{ color: '#4af', fontWeight: 700, fontSize:20 }}>{evaData?.telemetry.eva1.primary_battery_level ?? 'N/A'}%</span></div>
              <div style={{ fontSize: 11, color: '#aaa' }}>2h to full charge</div>
            </div>
            <div style={{ minHeight: 85, flex: 1, background: '#141414', borderRadius: 8, padding: '8px 12px', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center'  }}>
              <div style={{ fontSize: 15, color: '#ffffff' }}>O₂ <span style={{ color: '#4af', fontWeight: 700, fontSize:20 }}>{evaData?.telemetry.eva1.oxy_pri_storage ?? 'N/A'}%</span></div>
              <div style={{ fontSize: 11, color: '#aaa' }}>2h to full charge</div>
            </div>
          </div>

          {/* Suit Conditions */}
          <div style={{ fontSize: 12, color: '#ffffff', marginBottom: 8, textAlign: 'center'  }}>Suit Conditions</div>
          <div style={{ display: 'flex', gap: 8 }}>
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div style={{ minHeight: 85, background: '#141414', borderRadius: 8, padding: '8px 12px', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center'  }}>
                <div style={{ fontSize: 30, fontWeight: 700, color: '#4af' }}>{(evaData?.telemetry.eva1.temperature)?.toFixed(0) ?? 'N/A'} <span style={{ fontSize: 15, color: '#ffffff' }}>°F</span></div>
                <div style={{ fontSize: 15, color: '#ffffff' }}>Temperature</div>
              </div>
              <div style={{ minHeight: 85, background: '#141414', borderRadius: 8, padding: '8px 12px', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center'  }}>
                <div style={{ fontSize: 30, fontWeight: 700, color: '#4af' }}>{evaData?.telemetry.eva1.coolant_liquid_pressure ?? 'N/A'} <span style={{ fontSize: 15, color: '#ffffff' }}>PSI</span></div>
                <div style={{ fontSize: 15, color: '#ffffff' }}>Coolant Liq Ps</div>
              </div>
              <div style={{ minHeight: 85, background: '#141414', borderRadius: 8, padding: '8px 12px', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center'  }}>
                <div style={{ fontSize: 30, fontWeight: 700, color: '#4af' }}>{evaData?.telemetry.eva1.coolant_gas_pressure ?? 'N/A'} <span style={{ fontSize: 15, color: '#ffffff' }}>PSI</span></div>
                <div style={{ fontSize: 15, color: '#ffffff' }}>Coolant Gas Ps</div>
              </div>
            </div>
            <div style={{ width: 250, minHeight: 272, background: '#141414', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <img src={astronaut} alt="Astronaut" style={{ width: 80, objectFit: 'contain' }} />
            </div>
          </div>
        </div>

        {/* Suit 2 */}
        <div style={{ flex: 1, border: '1px solid #454545', borderRadius: 10, padding: 12, minHeight: 420}}>
          <h3 style={{ textAlign: 'center', margin: '0 0 12px 0', fontSize: 20, color: '#22cc55' }}>Suit 2</h3>

          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <div style={{ minHeight: 85, flex: 1, background: '#141414', borderRadius: 8, padding: '8px 12px', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center'  }}>
              <div style={{ fontSize: 15, color: '#ffffff' }}>Battery <span style={{ color: '#22cc55', fontWeight: 700, fontSize:20 }}>{evaData?.telemetry.eva2.battery_level ?? 'N/A'}%</span></div>
              <div style={{ fontSize: 11, color: '#aaa' }}>2h to full charge</div>
            </div>
            <div style={{ minHeight: 85, flex: 1, background: '#141414', borderRadius: 8, padding: '8px 12px', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center'  }}>
              <div style={{ fontSize: 15, color: '#ffffff' }}>O₂ <span style={{ color: '#22cc55', fontWeight: 700, fontSize:20 }}>{evaData?.telemetry.eva2.oxy_sec_storage ?? 'N/A'}%</span></div>
              <div style={{ fontSize: 11, color: '#aaa' }}>2h to full charge</div>
            </div>
          </div>

          <div style={{ fontSize: 12, color: '#ffffff', marginBottom: 8, textAlign: 'center'  }}>Suit Conditions</div>
          <div style={{ display: 'flex', gap: 8 }}>
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div style={{ minHeight: 85, background: '#141414', borderRadius: 8, padding: '8px 12px', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center'  }}>
                <div style={{ fontSize: 30, fontWeight: 700, color: '#22cc55' }}>{(evaData?.telemetry.eva1.temperature)?.toFixed(0) ?? 'N/A'} <span style={{ fontSize: 15, color: '#ffffff' }}>°F</span></div>
                <div style={{ fontSize: 15, color: '#ffffff' }}>Temperature</div>
              </div>
              <div style={{ minHeight: 85, background: '#141414', borderRadius: 8, padding: '8px 12px', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center'  }}>
                <div style={{ fontSize: 30, fontWeight: 700, color: '#22cc55' }}>{evaData?.telemetry.eva2.coolant_liquid_pressure ?? 'N/A'} <span style={{ fontSize: 15, color: '#ffffff' }}>PSI</span></div>
                <div style={{ fontSize: 15, color: '#ffffff' }}>Coolant Liq Ps</div>
              </div>
              <div style={{ minHeight: 85, background: '#141414', borderRadius: 8, padding: '8px 12px', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center'  }}>
                <div style={{ fontSize: 30, fontWeight: 700, color: '#22cc55' }}>{evaData?.telemetry.eva2.coolant_gas_pressure ?? 'N/A'} <span style={{ fontSize: 15, color: '#ffffff' }}>PSI</span></div>
                <div style={{ fontSize: 15, color: '#ffffff' }}>Coolant Gas Ps</div>
              </div>
            </div>
            <div style={{ width: 250, minHeight: 272, background: '#141414', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <img src={astronaut} alt="Astronaut" style={{ width: 80, objectFit: 'contain' }} />
            </div>
          </div>
        </div>

        {/* Alerts + AIA */}
        <div style={{ width: 400, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ border: '1px solid #454545', borderRadius: 10, padding: 12, flex: 1 }}>
            <h3 style={{ margin: '0 0 10px 0', fontSize: 20 }}>Alerts</h3>
            <div style={{ background: '#2a0a0a', border: '1px solid #550000', borderRadius: 6, padding: '8px 12px', fontSize: 13, color: '#ffffff' }}>
              Suit 1 battery is not charging
            </div>
          </div>
          <div style={{ border: '1px solid #454545', borderRadius: 10, padding: 12, display: 'flex', alignItems: 'center', gap: 12, cursor: 'pointer' }}>
            <div style={{ width: 36, height: 36, borderRadius: '50%', background: 'radial-gradient(circle at 40% 40%, #6688ff, #0022aa)', flexShrink: 0 }} />
            <span style={{ fontSize: 14, fontWeight: 600 }}>AIA Quick Access</span>
          </div>
        </div>

      </div>

      {/* Task Row */}
      <div style={{ border: '1px solid #454545', borderRadius: 10, padding: 12, height: 300 }}>

        {/* Task Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
          <span style={{ fontSize: 20, fontWeight: 700 }}>Task</span>
          <div style={{ flex: 1, background: '#222', borderRadius: 20, height: 60, overflow: 'hidden', position: 'relative' }}>
            <div style={{ width: '65%', height: '100%', background: '#445', borderRadius: 20 }} />
            <span style={{ position: 'absolute', left: '50%', top: '50%', transform: 'translate(-50%, -50%)', fontSize: 13, fontWeight: 700 }}>65%</span>
          </div>
          <span style={{ fontSize: 15, color: '#aaa', whiteSpace: 'nowrap' }}>2/3 done</span>
          <button style={{ background: '#1a1a2e', border: '1px solid #444', color: 'white', borderRadius: 8, padding: '6px 14px', fontSize: 13, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}>
            📋 New Task
          </button>
        </div>

        {/* Up Next */}
        <hr style={{ paddingTop: 25, border: 'none', borderTop: '1px solid #454545', margin: 'auto 0 8px 0' }} />
        <div style={{ height: 120, border: '1px solid #454545', borderRadius: 8, padding: 12, display: 'flex', gap: 12, alignItems: 'center', background: 'linear-gradient(to bottom, #3d3d43, #393b93)' }}>
          <div style={{ width: 90, height: 70, background: '#222', borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, color: '#666', flexShrink: 0 }}>
            [map preview]
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 18, fontWeight: 600, marginBottom: 4 }}>Travel to Zone B</div>
            <div style={{ fontSize: 15, color: '#888', marginBottom: 8 }}>📍 Moon</div>
            <div style={{ display: 'flex', gap: 4 }}>
              <div style={{ width: 20, height: 20, borderRadius: '50%', background: '#3355ff', fontSize: 10, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>A</div>
              <div style={{ width: 20, height: 20, borderRadius: '50%', background: '#33aa55', fontSize: 10, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>B</div>
            </div>
          </div>
          <button style={{ background: '#1a1a1a', border: '1px solid #444', color: 'white', borderRadius: 6, padding: '6px 14px', fontSize: 13, cursor: 'pointer' }}>
            START
          </button>
        </div>

      </div>

    </div>
  )
}
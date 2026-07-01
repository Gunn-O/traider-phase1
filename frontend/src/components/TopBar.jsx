import { useEffect, useState } from 'react'
import { useTicks } from '../hooks/useTicks'
import { Glyph, I } from './ui/primitives'
import { AddBotModal } from './office/OfficeScene'
import { FMT } from '../utils/format'

// Command Deck top bar — status chips, live XAUUSD price, clock, alert bell,
// operator, and compact Add-Bot / Stop-All / Exit controls. The full bot config
// lives in the Live Trade control bar; this keeps a quick "+ Add Bot" handy.
export default function TopBar({ bots = [], onAddBot, onEmergencyStop, onExit, alertCount = 0, isConnected = true }) {
  const [clock, setClock] = useState('')
  const [adding, setAdding] = useState(false)
  const { ticks } = useTicks()

  useEffect(() => {
    const tick = () => {
      const d = new Date()
      const p = (n) => String(n).padStart(2, '0')
      setClock(`${p(d.getMonth() + 1)}/${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`)
    }
    tick(); const id = setInterval(tick, 1000); return () => clearInterval(id)
  }, [])

  const running = bots.filter((b) => b.status === 'running')
  const sym = running[0]?.symbol || 'XAUUSDc'
  const price = ticks?.[sym]?.bid

  return (
    <header className="topbar">
      <div className="tb-status">
        <span className={`status-chip ${isConnected ? 'on' : 'warn'}`} title={isConnected ? 'WebSocket connected' : 'WebSocket disconnected — backend running?'}>
          <span className="led" style={{ background: isConnected ? 'var(--c-green)' : 'var(--c-red)', boxShadow: `0 0 8px ${isConnected ? 'var(--c-green)' : 'var(--c-red)'}` }} />
          {isConnected ? 'WS LIVE' : 'WS OFF'}
        </span>
        <span className={`status-chip ${running.length ? 'on' : ''}`}>
          <span className="led" style={{ background: running.length ? 'var(--c-green)' : 'var(--muted)', boxShadow: running.length ? '0 0 8px var(--c-green)' : 'none' }} />
          {running.length} ACTIVE
        </span>
        <span className="status-chip"><Glyph d={I.target} size={14} /> XAUUSD <b className="gold mono">{price != null ? FMT.px(price) : '—'}</b></span>
      </div>
      <div className="tb-right">
        <span className="tb-clock mono">{clock}</span>
        <button className="cd-btn btn-primary" style={{ padding: '7px 13px' }} onClick={() => setAdding(true)}>+ Add Bot</button>
        {running.length > 0 && (
          <button className="cd-btn btn-stopall" style={{ padding: '7px 13px' }} onClick={onEmergencyStop}>⛔ Stop All</button>
        )}
        <button className="tb-bell"><Glyph d={I.bell} size={16} />{alertCount > 0 && <span className="bell-dot mono">{alertCount}</span>}</button>
        <div className="tb-user">
          <span className="tb-avatar">C</span>
          <div className="tb-user-info"><b>Operator</b><span className="mono dim">COMMANDER</span></div>
        </div>
        {onExit && <button className="cd-btn btn-exit" onClick={onExit}>EXIT</button>}
      </div>
      {adding && (
        <>
          <div className="os-backdrop" style={{ position: 'fixed', zIndex: 2000 }} onClick={() => setAdding(false)} />
          <div style={{ position: 'fixed', inset: 0, zIndex: 2001, pointerEvents: 'none' }}>
            <div style={{ pointerEvents: 'auto' }}><AddBotModal onClose={() => setAdding(false)} onAddBot={onAddBot} /></div>
          </div>
        </>
      )}
    </header>
  )
}

import { useEffect, useRef, useState } from 'react'
import { OSTATUS, OTONE, STATIONS, AGENT_PROPS } from './agents'
import { Pill } from '../ui/primitives'
import { FMT } from '../../utils/format'

const CITY = [38, 62, 50, 78, 44, 90, 58, 70, 48, 84, 54]

function OfficeProp({ type }) {
  switch (type) {
    case 'command': return <div className="p-command"><span className="c-screen" /></div>
    case 'cctv': return <div className="p-cctv"><i /><i /><i /><i /><span className="rec" /></div>
    case 'news': return <div className="p-news"><span className="nt">NEWS</span><span className="ticker" /></div>
    case 'robot': return <div className="p-robot"><span className="r-head" /><span className="r-body" /><span className="spark" /></div>
    case 'stage': return <div className="p-stage"><span className="riser" /><span className="mic" /></div>
    case 'holo': return <div className="p-holo"><span className="h-globe" /><span className="h-base" /></div>
    case 'lectern': return <div className="p-lectern"><span className="l-top" /><span className="l-post" /></div>
    case 'board': return <div className="p-board"><span className="b-screen"><i /><i /><i /></span><span className="b-leg" /></div>
    default: return null
  }
}

function OfficeRoom({ agents, goal, compact, onSelect }) {
  const seated = agents.filter((a) => a.id !== 'analyst')
  const luffy = agents.find((a) => a.id === 'analyst')
  const H = compact ? 108 : 132

  // Luffy oversees from the command deck (mezzanine) and descends to patrol
  // every 15 minutes — exactly the design behaviour.
  const DECK = { x: 50, y: 49 }
  const [lp, setLp] = useState({ x: DECK.x, y: DECK.y, dur: 0, dir: 1, moving: false, onDeck: true })
  const lpRef = useRef(lp); lpRef.current = lp
  const [sel, setSel] = useState(null)
  const timers = useRef({})

  useEffect(() => {
    const T = timers.current
    const moveTo = (x, y, deck, cb) => {
      const cur = lpRef.current
      const dist = Math.hypot(x - cur.x, (y - cur.y) * 1.4)
      const dur = Math.min(7000, Math.max(2200, dist * 130))
      setLp({ x, y, dur, dir: x < cur.x ? -1 : 1, moving: true, onDeck: false })
      T.mv = setTimeout(() => { setLp((p) => ({ ...p, moving: false, onDeck: deck })); cb && cb() }, dur)
    }
    const patrol = () => {
      moveTo(38, 80, false, () => {
        T.p1 = setTimeout(() => moveTo(72, 84, false, () => {
          T.p2 = setTimeout(() => moveTo(DECK.x, DECK.y, true), 1800)
        }), 1800)
      })
    }
    T.cycle = setInterval(patrol, 15 * 60 * 1000)
    return () => { Object.values(T).forEach((t) => { clearTimeout(t); clearInterval(t) }) }
  }, [])

  const pick = (a) => { setSel(a.id); onSelect(a) }
  const g = goal || { target: 3000, progress: 0, remaining: 3000, pct: 0 }

  return (
    <div className={`office-scene ${compact ? 'os-compact' : 'os-tall'}`}>
      <div className="os-hud">
        <div className="hint">▸ คลิกตัวละครเพื่อดูสถานะ · Luffy คุมจากห้องบัญชาการ ลงตรวจทุก 15 นาที</div>
        <div className="os-legend">
          <span><i className="led" style={{ background: 'var(--c-green)', boxShadow: '0 0 6px var(--c-green)' }} /> active</span>
          <span><i className="led" style={{ background: 'var(--c-magenta)', boxShadow: '0 0 6px var(--c-magenta)' }} /> review</span>
          <span><i className="led" style={{ background: 'var(--muted)' }} /> standby</span>
        </div>
      </div>

      <div className="os-ceiling"><span className="os-neon a" /><span className="os-neon b" /><span className="os-neon c" /></div>

      <div className="os-backwall" />
      <div className="os-wallscreen">
        <div className="ws-title">▤ MISSION 2026 · GOAL TRACKER</div>
        <div className="ws-quote">
          <span className="wq-tag">// THE WHY</span>
          <span className="wq-text">SKI THE SWISS ALPS</span>
        </div>
        <div className="ws-goal">
          <div className="wg-rem">
            <span className="wg-num mono">{FMT.usd(g.remaining)}</span>
            <span className="wg-lbl">TO TARGET · เหลือถึงเป้า</span>
          </div>
          <div className="wg-bar"><div className="wg-fill" style={{ width: Math.min(100, Math.max(0, g.pct)) + '%' }} /></div>
          <div className="wg-foot mono">
            <span>P/L {FMT.signed(g.progress)}</span>
            <span className="wg-tgt">TARGET {FMT.usd(g.target, 0)}</span>
          </div>
        </div>
      </div>
      <div className="os-windows">
        <div className="city">{CITY.map((h, i) => <b key={i} style={{ height: h + '%' }} />)}</div>
      </div>
      <div className="os-plant-big" style={{ left: '95.5%', top: '52%', transform: 'translate(-50%,-100%)' }}>
        <span className="leaf" style={{ transform: 'translateX(-50%) rotate(-22deg)' }} />
        <span className="leaf" style={{ transform: 'translateX(-50%) rotate(0deg)' }} />
        <span className="leaf" style={{ transform: 'translateX(-50%) rotate(22deg)' }} />
        <span className="pot" />
      </div>

      <div className="os-floor" />
      <div className="os-rug" />

      {/* command deck (mezzanine) */}
      <div className="os-deck" style={{ top: '49%' }}>
        <div className="deck-screen l" /><div className="deck-screen r" />
        <div className="deck-glow" />
        <div className="deck-top" />
        <div className="deck-rail">{Array.from({ length: 11 }).map((_, i) => <i key={i} />)}</div>
        <div className="deck-leg" style={{ left: '16%' }} /><div className="deck-leg" style={{ right: '16%' }} />
      </div>

      {/* themed background stations */}
      {seated.map((a) => {
        const st = STATIONS[a.id]; const pr = AGENT_PROPS[a.id]
        if (!st || !pr) return null
        const px = st.x + (pr.dx || 0), py = st.y + (pr.dy || 0)
        return (
          <div className="os-prop2" key={'prop-' + a.id} style={{ left: px + '%', top: py + '%', zIndex: Math.round(py * 10) }}>
            <OfficeProp type={pr.type} />
          </div>
        )
      })}

      {/* seated/standing agents */}
      {seated.map((a) => {
        const st = STATIONS[a.id]; if (!st) return null
        const status = OSTATUS[a.status] || OSTATUS.idle
        return (
          <div key={a.id} className={`os-char ${sel === a.id ? 'sel' : ''}`} onClick={() => pick(a)}
            style={{ left: st.x + '%', top: st.y + '%', zIndex: Math.round(st.y * 10) + 2, '--ac': OTONE[a.tone] }}>
            <div className="os-char-depth">
              <div className="os-tag">
                <span className="led-sm" style={{ background: status.col, boxShadow: `0 0 6px ${status.col}` }} />
                <span className="tag-char">{a.char}</span><span>· {a.name}</span>
              </div>
              <div className="os-bob"><img src={a.img} alt={a.name} style={{ height: H, width: H }} /></div>
              <div className="os-shadow" />
            </div>
          </div>
        )
      })}

      {/* Luffy — command deck inspector */}
      {luffy && (
        <div className={`os-char ${lp.moving ? 'walking' : ''} ${sel === 'analyst' ? 'sel' : ''}`} onClick={() => pick(luffy)}
          style={{ left: lp.x + '%', top: lp.y + '%', zIndex: lp.onDeck ? 485 : Math.round(lp.y * 10) + 5, transitionDuration: lp.dur + 'ms', '--ac': OTONE[luffy.tone] }}>
          <div className="os-char-depth">
            <div className="os-tag">
              <span className="led-sm" style={{ background: 'var(--c-green)', boxShadow: '0 0 6px var(--c-green)' }} />
              <span className="tag-char">{luffy.char}</span><span>· {lp.onDeck ? 'บัญชาการ' : 'ตรวจงาน'}</span>
            </div>
            <div className="os-flip" style={{ transform: `scaleX(${lp.dir})` }}>
              <div className="os-bob"><img src={luffy.img} alt={luffy.name} style={{ height: H, width: H }} /></div>
            </div>
            {!lp.onDeck && <div className="os-shadow" />}
          </div>
        </div>
      )}
    </div>
  )
}

export function AgentDrawer({ a, onClose }) {
  const st = OSTATUS[a.status] || OSTATUS.idle
  const ac = OTONE[a.tone]
  return (
    <div className="os-drawer" style={{ '--ac': ac }}>
      <button className="dr-close" onClick={onClose}>×</button>
      <div className="dr-portrait"><div className="dr-grid" /><img src={a.img} alt={a.name} /></div>
      <div className="dr-char mono">{a.char.toUpperCase()} · AGENT</div>
      <div className="dr-name">{a.name}</div>
      <div className="dr-row">
        <Pill tone={a.status === 'review' ? 'magenta' : a.status === 'idle' ? 'cyan' : 'green'} solid={a.status === 'active'}>{st.label}</Pill>
        <span className="mono dim" style={{ fontSize: 11 }}>{a.nameTh}</span>
      </div>
      <div className="dr-role">{a.role}</div>
      <div className="dr-desc">{a.desc}</div>
      <div className="dr-metrics">
        {a.metrics.map((m, i) => (
          <div className="dr-metric" key={i}>
            <div className="v">{m.v}{m.u && <em>{m.u}</em>}</div>
            <div className="k">{m.k}</div><div className="kth">{m.kth}</div>
          </div>
        ))}
      </div>
      <div className="dr-logline"><span className="lbl">LIVE LOG · {a.char.toUpperCase()}</span>› {a.log}</div>
    </div>
  )
}

export function AgentRoster({ agents }) {
  const [sel, setSel] = useState(null)
  const stCol = { active: 'var(--c-green)', review: 'var(--c-magenta)', idle: 'var(--muted)' }
  return (
    <>
      <div className="roster-grid">
        {agents.map((a, i) => (
          <button className="roster-card" key={a.id} style={{ '--ac': OTONE[a.tone] }} onClick={() => setSel(i)}>
            <div className="rc-thumb"><img src={a.img} alt={a.name} /></div>
            <div className="rc-info">
              <div className="rc-name">{a.name}</div>
              <div className="rc-char mono">{a.char}</div>
              <div className="rc-role">{a.nameTh}</div>
            </div>
            <span className="led-sm rc-led" style={{ background: stCol[a.status], boxShadow: `0 0 6px ${stCol[a.status]}` }} />
          </button>
        ))}
      </div>
      {sel !== null && (
        <div className="os-backdrop" style={{ position: 'fixed', zIndex: 1000 }} onClick={() => setSel(null)}>
          <div onClick={(e) => e.stopPropagation()} style={{ position: 'fixed', top: 0, right: 0, bottom: 0 }}>
            <AgentDrawer a={agents[sel]} onClose={() => setSel(null)} />
          </div>
        </div>
      )}
    </>
  )
}

export function AddBotModal({ onClose, onAddBot }) {
  const [tf, setTf] = useState('M5')
  const [mode, setMode] = useState('paper')
  const [source, setSource] = useState('auto')
  const [symbol, setSymbol] = useState('XAUUSDc')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const TFS = ['M1', 'M5', 'M15', 'M30', 'H1', 'H4']

  const start = async () => {
    if (!onAddBot) { onClose(); return }
    setBusy(true); setErr('')
    try {
      await onAddBot({ tf, symbol, mode, data_source: source })
      onClose()
    } catch (e) {
      setErr(e.message || 'failed to start bot')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="ab-modal-card">
      <button className="dr-close" onClick={onClose}>×</button>
      <h3>ADD BOT · เปิดบอทใหม่</h3>
      <div className="ab-sub">ตั้งค่าแล้วกดเริ่มรัน · start a bot with this config</div>
      <div className="ab-field"><label>TIMEFRAME · กรอบเวลา</label>
        <div className="tf-pills">{TFS.map((t) => <button key={t} className={`tf-pill ${tf === t ? 'on' : ''}`} onClick={() => setTf(t)}>{t}</button>)}</div>
      </div>
      <div className="ab-field"><label>MODE · โหมด</label>
        <select value={mode} onChange={(e) => setMode(e.target.value)}>
          <option value="paper">Simulation (paper)</option>
          <option value="micro">Broker · Cent (micro)</option>
          <option value="live">Broker · Live</option>
        </select>
      </div>
      <div className="ab-field"><label>DATA SOURCE · แหล่งข้อมูล</label>
        <select value={source} onChange={(e) => setSource(e.target.value)}>
          <option value="auto">Auto</option><option value="mt5">MT5</option>
          <option value="yf">yfinance</option><option value="tv">TradingView</option>
        </select>
      </div>
      <div className="ab-field"><label>SYMBOL · สัญลักษณ์</label>
        <select value={symbol} onChange={(e) => setSymbol(e.target.value)}>
          <option value="XAUUSDc">XAUUSDc (Cent)</option><option value="XAUUSDm">XAUUSDm (Micro)</option>
          <option value="XAUUSD">XAUUSD (Standard)</option>
        </select>
      </div>
      {err && <div className="neg" style={{ fontSize: 11, marginBottom: 8 }}>{err}</div>}
      <button className="cd-btn btn-primary" style={{ width: '100%', marginTop: 6 }} disabled={busy} onClick={start}>
        {busy ? 'starting…' : `+ ADD BOT · เริ่มรัน (${tf})`}
      </button>
    </div>
  )
}

// Floating Add-Bot modal portal (fixed overlay)
function AddBotOverlay({ onClose, onAddBot }) {
  return (
    <>
      <div className="os-backdrop" style={{ position: 'fixed', zIndex: 2000 }} onClick={onClose} />
      <div style={{ position: 'fixed', inset: 0, zIndex: 2001, pointerEvents: 'none' }}>
        <div style={{ pointerEvents: 'auto' }}><AddBotModal onClose={onClose} onAddBot={onAddBot} /></div>
      </div>
    </>
  )
}

export function OfficeScene({ agents, goal, compact, onAddBot }) {
  const [drawer, setDrawer] = useState(null)
  return (
    <div className="office-scene-wrap">
      <OfficeRoom agents={agents} goal={goal} compact={compact} onSelect={setDrawer} />
      {drawer && (
        <>
          <div className="os-backdrop" onClick={() => setDrawer(null)} />
          <AgentDrawer a={drawer} onClose={() => setDrawer(null)} />
        </>
      )}
    </div>
  )
}

// VirtualOffice panel — used by Command Center + Office page.
export function VirtualOffice({ agents, goal, compact, onAddBot }) {
  const active = agents.filter((a) => a.status === 'active').length
  const [adding, setAdding] = useState(false)
  return (
    <section className="panel office-panel">
      <div className="panel-head">
        <div className="ph-title">
          <span className="ph-bar" />
          <div>
            <h2>VIRTUAL OFFICE</h2>
            <span className="ph-sub">ห้องปฏิบัติการเอเจนต์ · คลิกตัวละครเพื่อดูสถานะ</span>
          </div>
        </div>
        <div className="office-stats mono">
          <span><b style={{ color: 'var(--c-green)' }}>{active}</b>/{agents.length} active</span>
          <span className="chip-live">● LIVE</span>
          {onAddBot && (
            <button className="cd-btn btn-primary" style={{ padding: '7px 13px', fontSize: 11 }} onClick={() => setAdding(true)}>+ ADD BOT</button>
          )}
        </div>
      </div>
      <OfficeScene agents={agents} goal={goal} compact={compact} />
      {adding && <AddBotOverlay onClose={() => setAdding(false)} onAddBot={onAddBot} />}
    </section>
  )
}

export default VirtualOffice

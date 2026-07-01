import { useEffect, useState } from 'react'
import { Panel, Pill } from '../components/ui/primitives'

const MODES = [
  { key: 'micro', label: 'Micro (Cent)', tone: 'gold' },
  { key: 'live', label: 'Live (Real)', tone: 'red' },
  { key: 'paper', label: 'Paper (Sim)', tone: 'cyan' },
  { key: 'backtest', label: 'Backtest', tone: 'magenta' },
]

export default function Settings({ botState }) {
  return (
    <div className="view">
      <div className="view-head"><div><h1>SETTINGS</h1><p>ตั้งค่าระบบ · จัดการข้อมูลแยกตามโหมด</p></div></div>

      <ResetData />

      <div className="grid-2">
        <Panel title="BOT CONFIGURATION" titleTh="ค่าตั้งต้นบอท" accent="cyan">
          <table className="data-table">
            <tbody>
              <tr><td>Default TF</td><td className="mono" style={{ textAlign: 'right' }}>{botState?.trading_tf || 'M5'}</td></tr>
              <tr><td>Default Symbol</td><td className="mono" style={{ textAlign: 'right' }}>{botState?.symbol || 'XAUUSDc'}</td></tr>
              <tr><td>Data Source</td><td className="mono" style={{ textAlign: 'right' }}>{botState?.data_source_actual || 'Auto'}</td></tr>
            </tbody>
          </table>
        </Panel>
        <Panel title="RISK MANAGEMENT" titleTh="การจัดการความเสี่ยง" accent="gold">
          <table className="data-table">
            <tbody>
              <tr><td>Risk per plan</td><td className="mono" style={{ textAlign: 'right' }}>10%</td></tr>
              <tr><td>Min R:R</td><td className="mono" style={{ textAlign: 'right' }}>1.0</td></tr>
              <tr><td>Max consecutive loss</td><td className="mono" style={{ textAlign: 'right' }}>3</td></tr>
            </tbody>
          </table>
        </Panel>
      </div>

      <Panel title="SYSTEM" titleTh="ระบบ" accent="green">
        <table className="data-table">
          <tbody>
            <tr><td>Backend</td><td className="mono" style={{ textAlign: 'right' }}>http://127.0.0.1:8080</td></tr>
            <tr><td>Architecture</td><td className="mono" style={{ textAlign: 'right' }}>Per-mode DB · MT5 backfill</td></tr>
            <tr><td>Version</td><td className="mono" style={{ textAlign: 'right' }}>Phase II</td></tr>
          </tbody>
        </table>
      </Panel>
    </div>
  )
}

function ResetData() {
  const [counts, setCounts] = useState({})
  const [mode, setMode] = useState('micro')
  const [confirmText, setConfirmText] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)

  const loadCounts = async () => {
    try {
      const r = await fetch('/api/data/counts')
      if (r.ok) setCounts((await r.json()).counts || {})
    } catch { /* ignore */ }
  }
  useEffect(() => { loadCounts() }, [])

  const needed = `RESET ${mode}`
  const doReset = async () => {
    if (confirmText !== needed) return
    setBusy(true); setMsg(null)
    try {
      const r = await fetch('/api/data/reset', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode, confirm: true }),
      })
      const body = await r.json().catch(() => ({}))
      if (!r.ok) throw new Error(body.detail || `HTTP ${r.status}`)
      setMsg({ ok: true, text: `Reset ${mode}: ${body.db?.trades ?? 0} trades wiped · sheets ${body.sheets}` })
      setConfirmText('')
      loadCounts()
    } catch (e) {
      setMsg({ ok: false, text: e.message })
    } finally { setBusy(false) }
  }

  return (
    <Panel title="RESET DATA" titleTh="ล้างข้อมูลตามโหมด · กู้คืนไม่ได้ — import MT5 history ก่อนถ้าต้องการเก็บ" accent="magenta">
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
        {MODES.map((m) => (
          <button key={m.key} className={`tf-tab ${mode === m.key ? 'active' : ''}`} onClick={() => { setMode(m.key); setConfirmText('') }}>
            {m.label} <span className="dim">({counts[m.key] ?? 0})</span>
          </button>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <span className="dim" style={{ fontSize: 12.5 }}>
          พิมพ์ <b className="mono" style={{ color: 'var(--c-magenta)' }}>{needed}</b> เพื่อยืนยันการล้าง <Pill tone="gold">{mode}</Pill> DB + Sheets tab
        </span>
        <input
          className="control-select" style={{ minWidth: 160 }}
          value={confirmText} onChange={(e) => setConfirmText(e.target.value)} placeholder={needed}
        />
        <button className="cd-btn btn-danger" disabled={busy || confirmText !== needed} onClick={doReset}>
          {busy ? 'resetting…' : '⚠ RESET'}
        </button>
      </div>
      {msg && (
        <div className={msg.ok ? 'pos' : 'neg'} style={{ marginTop: 12, fontSize: 12.5 }}>{msg.text}</div>
      )}
      <div className="dim" style={{ marginTop: 10, fontSize: 11 }}>
        ⓘ ล้างไม่ได้ถ้าบอทโหมดนั้นกำลังรัน — หยุดก่อน · Micro/Live เก็บข้อมูลจริงจาก MT5 ไว้วิเคราะห์
      </div>
    </Panel>
  )
}

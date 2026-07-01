import { useState } from 'react'
import { AddBotModal } from './office/OfficeScene'

// BotControlBar — the design's Live-Trade control bar, wired to the REAL
// multi-bot API: active count, TF tabs (dot = a bot runs on that TF),
// + Add Bot (config modal → startBot), per-TF Stop (stop the bot on the
// selected TF), and Stop All (emergency-stop).
const TFS = ['M1', 'M5', 'M15', 'M30', 'H1', 'H4']

export default function BotControlBar({ bots = [], onAddBot, onEmergencyStop, onStop }) {
  const [tf, setTf] = useState('M5')
  const [adding, setAdding] = useState(false)
  const [busy, setBusy] = useState(false)

  const running = bots.filter((b) => b.status === 'running')
  const botForTf = (t) => running.find((b) => b.tf === t)
  const selectedBot = botForTf(tf)

  const stopSelected = async () => {
    if (!selectedBot || !onStop) return
    if (!confirm(`Stop bot on ${tf} (${selectedBot.bot_id})?`)) return
    setBusy(true)
    try { await onStop(selectedBot.bot_id) } finally { setBusy(false) }
  }

  return (
    <div className="botbar">
      <div className="bb-status">
        <span className="led" style={{ background: running.length ? 'var(--c-green)' : 'var(--muted)', boxShadow: running.length ? '0 0 8px var(--c-green)' : 'none' }} />
        <b className="mono">{running.length} active</b>
      </div>
      <div className="bb-tabs">
        {TFS.map((t) => (
          <button
            key={t}
            className={`tf-tab ${tf === t ? 'active' : ''} ${botForTf(t) ? 'has-bot' : ''}`}
            onClick={() => setTf(t)}
            title={botForTf(t) ? `${t} bot is active — select then Stop ${t}` : `Select ${t}`}
          >
            {t}{botForTf(t) && <span className="tf-dot">●</span>}
          </button>
        ))}
      </div>
      <div className="bb-controls">
        <button className="cd-btn btn-primary" onClick={() => setAdding(true)} title="Start a bot with this config">+ Add Bot</button>
        {selectedBot && (
          <button className="cd-btn btn-danger" onClick={stopSelected} disabled={busy} title={`Stop the bot running on ${tf}`}>
            {busy ? '…' : `⏹ Stop ${tf}`}
          </button>
        )}
        <button className="cd-btn btn-stopall" onClick={onEmergencyStop} title="Stop ALL bots immediately">⛔ Stop All</button>
      </div>
      {adding && (
        <>
          <div className="os-backdrop" style={{ position: 'fixed', zIndex: 2000 }} onClick={() => setAdding(false)} />
          <div style={{ position: 'fixed', inset: 0, zIndex: 2001, pointerEvents: 'none' }}>
            <div style={{ pointerEvents: 'auto' }}>
              <AddBotModal onClose={() => setAdding(false)} onAddBot={onAddBot} />
            </div>
          </div>
        </>
      )}
    </div>
  )
}

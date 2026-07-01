import { useEffect, useState } from 'react'
import { Pill } from './ui/primitives'
import { fmtTime, FMT } from '../utils/format'

// LiveSnapshot — the REAL per-cycle signal view. Most cycles emit only a
// heartbeat (not a discrete signal event), so this reads b.heartbeat: what each
// running bot saw this candle (chart_type / detected signal) and WHY each
// strategy didn't fire (per-strategy skip_reasons). This is why the old
// event-only "Signal Feed" looked empty while the bot was clearly running.
export default function LiveSnapshot({ bots = [] }) {
  // tick so the "x ago" age stays fresh between heartbeats
  const [, bump] = useState(0)
  useEffect(() => {
    const t = setInterval(() => bump((n) => n + 1), 2000)
    return () => clearInterval(t)
  }, [])

  const running = bots.filter((b) => b.status === 'running')
  if (running.length === 0) {
    return <div className="empty-state">No active bots — start one to see live signal scanning</div>
  }

  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>BOT</th><th>LAST</th><th>CANDLE</th><th>CLOSE</th><th>R55</th>
          <th>SESSION</th><th>STATE</th><th>ACTIVE PLAN</th>
        </tr>
      </thead>
      <tbody>
        {running.map((b) => {
          const hb = b.heartbeat || {}
          const fired = hb.signal_pattern
          const stateText = fired
            ? `${hb.signal_pattern} ${hb.signal_direction || ''}${hb.signal_rr ? ` · R:R ${FMT.px(hb.signal_rr, 2)}` : ''}`
            : (hb.skip_reason || hb.chart_type || 'scanning…')
          const skipPairs = Object.entries(hb.skip_reasons || {})
          return (
            <tr key={b.bot_id}>
              <td className="mono">{b.bot_id}</td>
              <td className="mono dim"><Ago ts={hb.ts || b.last_updated} /></td>
              <td className="mono dim">{fmtTime(hb.candle_time)}</td>
              <td className="mono">{FMT.px(hb.candle_close)}</td>
              <td className="mono">{hb.R55_pip != null ? FMT.px(hb.R55_pip, 0) : '—'}</td>
              <td className="mono dim">{hb.session || '—'}</td>
              <td>
                {fired
                  ? <Pill tone="green">{stateText}</Pill>
                  : <span className="dim" style={{ fontSize: 12 }}>{stateText}</span>}
                {skipPairs.length > 0 && (
                  <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 2 }}>
                    {skipPairs.map(([pat, reason]) => (
                      <div key={pat} style={{ fontSize: 10.5 }}>
                        <span className="mono" style={{ color: 'var(--c-cyan)' }}>{pat}</span>
                        <span className="dim"> · {reason}</span>
                      </div>
                    ))}
                  </div>
                )}
              </td>
              <td className="mono dim">{shortPlan(hb.active_plan)}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

function Ago({ ts }) {
  if (!ts) return <span className="dim">—</span>
  const then = new Date(ts).getTime()
  if (!Number.isFinite(then)) return <span className="dim">—</span>
  const sec = Math.max(0, Math.floor((Date.now() - then) / 1000))
  const cls = sec < 90 ? 'pos' : sec < 300 ? 'gold' : 'neg'
  const label = sec < 5 ? 'now' : sec < 90 ? `${sec}s` : `${Math.floor(sec / 60)}m`
  return <span className={cls}>{label}</span>
}

function shortPlan(id) {
  if (!id) return '—'
  const m = String(id).match(/(\d{2})(\d{2})(\d{2})-?\d*$/)
  return m ? `${m[1]}:${m[2]}:${m[3]}` : String(id).slice(-10)
}

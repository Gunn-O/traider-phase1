import { Pill } from './ui/primitives'
import { fmtTime, FMT } from '../utils/format'

// SignalFeed — renders aggregated signal_detected / signal_skipped events in
// the Command Deck "sig-feed" style. Wired to real bot events.
export default function SignalFeed({ events = [] }) {
  if (!events.length) {
    return <div className="empty-state">No signals yet — bots report SIGNAL / SKIP here</div>
  }
  return (
    <div className="sig-feed">
      {events.map((e, i) => {
        const d = e.data || {}
        const detected = e.type === 'signal_detected'
        const pattern = d.pattern || d.chart_type || (e.msg || '').split(' ')[0] || 'SIGNAL'
        return (
          <div className="sig-row" key={i}>
            <span className="mono sig-t">{fmtTime(e.ts)}</span>
            <span className="sig-code">
              {String(pattern).toUpperCase()}
              <em className="mono">{d.direction || ''} {d.entry != null ? `· ${FMT.px(d.entry)}` : ''}</em>
            </span>
            <div className="sig-conf">
              <div className="conf-track"><div className="conf-fill" style={{ width: `${Math.min(100, (Number(d.rr) || 0) * 50)}%` }} /></div>
              <span className="mono">{d.rr != null ? `R:R ${FMT.px(d.rr, 2)}` : '—'}</span>
            </div>
            <Pill tone={detected ? 'green' : 'red'}>{detected ? 'SIGNAL' : 'SKIP'}</Pill>
            <span className="mono dim sig-stage">{e.bot_id || ''}</span>
          </div>
        )
      })}
    </div>
  )
}

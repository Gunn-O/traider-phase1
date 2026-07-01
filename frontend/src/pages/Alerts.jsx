import { useMemo } from 'react'
import { Panel, Pill } from '../components/ui/primitives'
import { fmtTime } from '../utils/format'

// Alert Center — derives a feed from real bot events. No mock data: maps event
// types to severities and surfaces the most recent across all bots.
const SEV = {
  subprocess_died: 'CRITICAL', emergency_stopped: 'CRITICAL', stopped: 'HIGH',
  plan_closed: 'INFO', plan_cancelled: 'HIGH', signal_skipped: 'INFO',
  plan_opened: 'INFO', signal_detected: 'INFO', started: 'INFO',
}
const sevTone = (s) => (s === 'CRITICAL' ? 'red' : s === 'HIGH' ? 'gold' : 'cyan')

export default function Alerts({ bots = [] }) {
  const alerts = useMemo(() => {
    const all = []
    for (const b of bots) {
      for (const e of (b.events || [])) {
        const sev = SEV[e.type] || 'INFO'
        all.push({ sev, type: e.type, msg: e.msg, ts: e.ts, bot_id: b.bot_id })
      }
    }
    // Surface non-trivial first, newest first
    return all
      .sort((a, b) => String(b.ts || '').localeCompare(String(a.ts || '')))
      .slice(0, 60)
  }, [bots])

  return (
    <div className="view">
      <div className="view-head"><div><h1>ALERT CENTER</h1><p>ศูนย์แจ้งเตือน · เหตุการณ์จากเอเจนต์และระบบ (เรียลไทม์)</p></div></div>
      <Panel title="ACTIVE ALERTS" titleTh="การแจ้งเตือนที่ทำงานอยู่" live accent="magenta">
        {alerts.length === 0 ? (
          <div className="empty-state">No alerts — events from running bots appear here</div>
        ) : (
          <table className="data-table alerts-table">
            <thead><tr><th>TIME</th><th>SEVERITY</th><th>EVENT</th><th>SOURCE</th></tr></thead>
            <tbody>
              {alerts.map((a, i) => (
                <tr key={i}>
                  <td className="mono dim">{fmtTime(a.ts)}</td>
                  <td><Pill tone={sevTone(a.sev)} solid={a.sev === 'CRITICAL'}>{a.sev}</Pill></td>
                  <td><div className="al-title">{a.msg || a.type}</div><div className="al-en mono dim">{a.type}</div></td>
                  <td><Pill tone="cyan">{a.bot_id}</Pill></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  )
}

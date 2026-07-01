import { VirtualOffice, AgentRoster } from '../components/office/OfficeScene'
import { useAgents } from '../components/office/useAgents'
import { useTradeStats } from '../hooks/useTradeStats'
import { Panel } from '../components/ui/primitives'
import { Meter } from '../components/ui/charts'
import { computeGoal } from '../utils/goal'

// Virtual Office — full page: walkable agent scene + roster + pipeline throughput
// + activity log. All agent status is live (useAgents derives from bots + REST).
export default function Office({ bots = [], account, onAddBot }) {
  const agents = useAgents(bots)
  const stats = useTradeStats()
  // Goal = $3000 REALIZED profit (closed trades only) → 0 right after a reset
  // until a trade closes. Floating P/L of still-open positions is intentionally
  // NOT counted (it's unrealized + volatile; shown separately in stat tiles).
  const realizedPnl = Number(stats?.total_pnl_usd) || 0
  const goal = computeGoal(realizedPnl)
  const active = agents.filter((a) => a.status === 'active').length

  // Pipeline throughput derived from aggregate signal/plan events.
  const ev = bots.flatMap((b) => b.events || [])
  const signals = ev.filter((e) => e.type === 'signal_detected').length
  const skipped = ev.filter((e) => e.type === 'signal_skipped').length
  const opened = ev.filter((e) => e.type === 'plan_opened').length
  const closed = ev.filter((e) => e.type === 'plan_closed').length
  const maxThru = Math.max(signals, 1)
  const flow = [
    { s: 'Signals detected', v: signals, tone: 'cyan' },
    { s: 'Skipped (G2/filter)', v: skipped, tone: 'magenta' },
    { s: 'Plans opened', v: opened, tone: 'gold' },
    { s: 'Plans closed', v: closed, tone: 'green' },
  ]

  // Activity log — newest first, across bots.
  const log = ev
    .filter((e) => e.ts)
    .sort((a, b) => String(b.ts).localeCompare(String(a.ts)))
    .slice(0, 14)

  return (
    <div className="view">
      <div className="view-head">
        <div>
          <h1>VIRTUAL OFFICE</h1>
          <p>ห้องปฏิบัติการเอเจนต์ · เอเจนต์ {agents.length} ตัวทำงานร่วมกัน — คลิกตัวละครเพื่อดูสถานะและงานที่กำลังทำ</p>
        </div>
        <div className="vh-stats mono"><span><b style={{ color: 'var(--c-green)' }}>{active}</b>/{agents.length} ACTIVE</span></div>
      </div>

      <VirtualOffice agents={agents} goal={goal} onAddBot={onAddBot} />

      <Panel title="AGENT ROSTER" titleTh="รายชื่อเอเจนต์ · คลิกการ์ดเพื่อดูรายละเอียด" accent="cyan">
        <AgentRoster agents={agents} />
      </Panel>

      <div className="grid-2">
        <Panel title="PIPELINE THROUGHPUT" titleTh="ปริมาณงานในสายการผลิต" accent="cyan">
          <div className="flow-stages">
            {flow.map((f, i) => (
              <div className="flow-stage" key={i}>
                <span className="fs-label">{f.s}</span>
                <Meter value={f.v} max={maxThru} tone={f.tone} unit="" />
              </div>
            ))}
          </div>
        </Panel>
        <Panel title="AGENT ACTIVITY LOG" titleTh="บันทึกการทำงาน" live accent="magenta">
          {log.length === 0 ? (
            <div className="empty-state">No agent activity yet</div>
          ) : (
            <div className="act-log mono">
              {log.map((e, i) => (
                <div className="act-row" key={i}>
                  <span className="dim">{new Date(e.ts).toLocaleTimeString()}</span>
                  <span className="act-agent" style={{ color: e.type === 'plan_closed' ? 'var(--c-gold)' : e.type === 'signal_skipped' ? 'var(--c-magenta)' : 'var(--c-cyan)' }}>
                    [{(e.type || 'evt').replace('signal_', '').replace('plan_', '').toUpperCase().slice(0, 6)}]
                  </span>
                  <span className="act-msg">{e.msg}</span>
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>
    </div>
  )
}

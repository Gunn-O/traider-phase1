import { useState } from 'react'
import { groupByPlan } from '../utils/groupByPlan'
import { Pill } from './ui/primitives'
import { FMT, fmtDateTime } from '../utils/format'

// PositionsTable — the triple-log fix made visible.
// Collapses orders into ONE row per plan_id (a MaiRuay plan with 3 entries
// shows as a single line). Click a plan to expand its child entries, each with
// its own FILLED / PENDING / CANCELLED status. The plan's rolled-up status
// follows broker reality: OPEN while any entry is live, else WIN/LOSS/CANCELLED.

const STATUS_TONE = {
  OPEN: 'warning', WIN: 'success', LOSS: 'error', CANCELLED: 'info', PENDING: 'warning', EXPIRED: 'info',
}

function shortPattern(p) {
  if (!p) return '—'
  const u = String(p).toUpperCase()
  if (u.startsWith('UPTREND')) return 'Uptrend'
  if (u.startsWith('DOWNTREND')) return 'Downtrend'
  if (u.startsWith('MOUNTAIN')) return 'Mountain'
  if (u.startsWith('MAI_RUAY') || u.startsWith('MAIRUAY')) return 'MaiRuay'
  return u
}

function EntryRow({ e }) {
  const tone = STATUS_TONE[e.result] || 'info'
  return (
    <tr className="plan-entry">
      <td className="entry-indent mono">#{e.order_num ?? '–'} · {e.order_type}</td>
      <td className="mono dim">{e.trade_id ? e.trade_id.slice(-6) : '—'}</td>
      <td><Pill tone={e.action === 'BUY' ? 'green' : 'red'}>{e.action || '—'}</Pill></td>
      <td className="mono">{FMT.px(e.entry)}</td>
      <td className="mono dim">{FMT.px(e.sl)}</td>
      <td className="mono dim">{FMT.px(e.tp)}</td>
      <td className="mono">{FMT.px(e.lot, 2)}</td>
      <td className="mono">{e.result === 'WIN' || e.result === 'LOSS' ? FMT.px(e.close_price) : '—'}</td>
      <td className={`mono ${e.pnl >= 0 ? 'pos' : 'neg'}`}>{e.result === 'PENDING' ? '—' : FMT.signed(e.pnl)}</td>
      <td><Pill tone={tone} solid={e.result === 'WIN'}>{e.result}</Pill></td>
    </tr>
  )
}

function PlanRow({ g }) {
  const [open, setOpen] = useState(false)
  const multi = g.entry_count > 1
  const tone = STATUS_TONE[g.status] || 'info'
  return (
    <>
      <tr className={`plan-row ${open ? 'expanded' : ''}`} onClick={() => multi && setOpen((o) => !o)}>
        <td className="mono dim">
          {multi && <span className="plan-caret">▶</span>}
          {fmtDateTime(g.open_time)}
        </td>
        <td className="mono">
          {shortPattern(g.pattern)}
          {multi && <span className="plan-count-chip">{g.filled_count}F·{g.pending_count}P·{g.cancelled_count}X / {g.entry_count}</span>}
        </td>
        <td><Pill tone={g.action === 'BUY' ? 'green' : 'red'}>{g.action || '—'}</Pill></td>
        <td className="mono">{FMT.px(g.entry)}</td>
        <td className="mono dim">{FMT.px(g.sl)}</td>
        <td className="mono dim">{FMT.px(g.tp)}</td>
        <td className="mono">{FMT.px(g.lot_total, 2)}</td>
        <td className="mono dim">{g.bot_id || '—'}</td>
        <td className={`mono ${g.pnl_total >= 0 ? 'pos' : 'neg'}`}>{g.status === 'OPEN' && g.pnl_total === 0 ? '—' : FMT.signed(g.pnl_total)}</td>
        <td><Pill tone={tone} solid={g.status === 'WIN'}>{g.status}</Pill></td>
      </tr>
      {open && multi && g.entries.map((e, i) => <EntryRow key={e.trade_id || i} e={e} />)}
    </>
  )
}

export default function PositionsTable({ open = [], closed = [], showClosed = true }) {
  const groups = groupByPlan(open, closed)
  const openGroups = groups.filter((g) => g.isOpen)
  const closedGroups = groups.filter((g) => !g.isOpen)

  if (groups.length === 0) {
    return <div className="empty-state">No positions yet</div>
  }

  return (
    <div className="positions-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <th>OPEN TIME</th><th>STRATEGY</th><th>DIR</th><th>ENTRY</th>
            <th>SL</th><th>TP</th><th>LOT</th><th>BOT</th><th>P&L</th><th>STATUS</th>
          </tr>
        </thead>
        <tbody>
          {openGroups.length > 0 && (
            <tr className="plan-entry"><td colSpan={10} className="label-dim" style={{ paddingTop: 8 }}>OPEN · {openGroups.length} plan(s)</td></tr>
          )}
          {openGroups.map((g) => <PlanRow key={g.plan_id} g={g} />)}
          {showClosed && closedGroups.length > 0 && (
            <tr className="plan-entry"><td colSpan={10} className="label-dim" style={{ paddingTop: 8 }}>CLOSED · {closedGroups.length} plan(s)</td></tr>
          )}
          {showClosed && closedGroups.map((g) => <PlanRow key={g.plan_id} g={g} />)}
        </tbody>
      </table>
    </div>
  )
}

// groupByPlan.js — collapse a flat order list into plan groups.
//
// Why: MaiRuay creates ONE plan with up to 3 entries (order_num 1/2/3) — one
// MARKET fill plus LIMIT entries that may never fill. Logged individually they
// render as 3 rows ("triple"), while MT5 shows a single real position. Grouping
// by plan_id collapses each plan to ONE row (expandable to its entries), so the
// Positions view matches broker reality: a plan is OPEN while any entry is live,
// and its unfilled LIMITs show as CANCELLED rather than phantom open rows.

const TERMINAL = new Set(['WIN', 'LOSS', 'CANCELLED', 'EXPIRED'])

const num = (v) => {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// Normalise one raw order dict (DB row or event payload) to a stable shape.
// DB hydration and live events use slightly different field names, so read both.
function normEntry(o, isOpen) {
  const result = isOpen ? 'PENDING' : (o.result || 'PENDING')
  return {
    trade_id: o.trade_id || '',
    plan_id: o.plan_id || '',
    order_num: o.order_num ?? null,
    order_type: o.order_type || (o.filled === false ? 'LIMIT' : 'MARKET'),
    action: o.action || '',
    pattern: o.pattern || o.chart_type || '',
    entry: o.entry ?? o.entry_price ?? null,
    sl: o.sl ?? o.sl_price ?? null,
    tp: o.tp ?? o.tp_price ?? null,
    lot: o.lot ?? o.lot_size ?? null,
    close_price: o.close_price ?? null,
    pnl: num(o.pnl ?? o.pnl_usd),
    result,
    close_reason: o.close_reason || '',
    open_time: o.open_time || o.timestamp_open || o.candle_time || '',
    close_time: o.close_time || o.timestamp_close || '',
    bot_id: o.bot_id || '',
    tf: o.tf || '',
    raw: o,
  }
}

// Derive a plan's rolled-up status from its entries.
//   OPEN      — at least one entry still live (PENDING/FILLED, not terminal)
//   WIN/LOSS  — all entries terminal; sign of net pnl decides
//   CANCELLED — all entries terminal and none ever produced pnl (all cancelled)
function deriveStatus(entries) {
  const anyLive = entries.some((e) => !TERMINAL.has(e.result))
  if (anyLive) return 'OPEN'
  const traded = entries.filter((e) => e.result === 'WIN' || e.result === 'LOSS')
  if (traded.length === 0) return 'CANCELLED'
  const net = traded.reduce((s, e) => s + e.pnl, 0)
  return net >= 0 ? 'WIN' : 'LOSS'
}

/**
 * Group a mixed open+closed order list into plan groups.
 * @param {Array} open   - open orders (treated as PENDING unless they carry a result)
 * @param {Array} closed - closed orders (WIN/LOSS/CANCELLED)
 * @returns {Array} plan groups, newest first
 */
export function groupByPlan(open = [], closed = []) {
  const norm = [
    ...open.map((o) => normEntry(o, true)),
    ...closed.map((o) => normEntry(o, false)),
  ]

  const byPlan = new Map()
  for (const e of norm) {
    // Orders with no plan_id (shouldn't happen, but be safe) become singletons
    // keyed by their own trade_id so they still render.
    const key = e.plan_id || `__solo__${e.trade_id || Math.random()}`
    if (!byPlan.has(key)) byPlan.set(key, [])
    byPlan.get(key).push(e)
  }

  const groups = []
  for (const [plan_id, rawEntries] of byPlan.entries()) {
    // Dedup entries that arrived from both DB hydration and a live event
    // (same trade_id, possibly prefix-truncated). Keep the most "resolved" one.
    const seen = new Map()
    for (const e of rawEntries) {
      const k = e.trade_id || `${e.order_num}`
      const prev = seen.get(k)
      if (!prev || (TERMINAL.has(e.result) && !TERMINAL.has(prev.result))) {
        seen.set(k, e)
      }
    }
    const entries = [...seen.values()].sort(
      (a, b) => (a.order_num ?? 99) - (b.order_num ?? 99)
    )

    const status = deriveStatus(entries)
    const filled = entries.filter(
      (e) => e.result === 'WIN' || e.result === 'LOSS' ||
             (status === 'OPEN' && e.order_type === 'MARKET')
    )
    const pending = entries.filter((e) => e.result === 'PENDING')
    const cancelled = entries.filter(
      (e) => e.result === 'CANCELLED' || e.result === 'EXPIRED'
    )
    const lead = entries[0] || {}

    groups.push({
      plan_id: plan_id.startsWith('__solo__') ? (lead.plan_id || '') : plan_id,
      pattern: lead.pattern,
      action: lead.action,
      bot_id: lead.bot_id,
      tf: lead.tf,
      open_time: entries.map((e) => e.open_time).filter(Boolean).sort()[0] || '',
      close_time: entries.map((e) => e.close_time).filter(Boolean).sort().slice(-1)[0] || '',
      entries,
      entry_count: entries.length,
      filled_count: filled.length,
      pending_count: pending.length,
      cancelled_count: cancelled.length,
      lot_total: entries.reduce((s, e) => s + num(e.lot), 0),
      pnl_total: entries.reduce((s, e) => s + e.pnl, 0),
      // Representative levels for the collapsed row — use the first entry.
      entry: lead.entry,
      sl: lead.sl,
      tp: lead.tp,
      status,
      isOpen: status === 'OPEN',
    })
  }

  // Newest first by open_time, then plan_id (which encodes the timestamp).
  return groups.sort((a, b) =>
    String(b.open_time || b.plan_id).localeCompare(String(a.open_time || a.plan_id))
  )
}

export default groupByPlan

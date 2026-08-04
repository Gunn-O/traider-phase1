import { useState, useEffect, useMemo, useCallback } from 'react'
import MetricCard from '../components/MetricCard'

// Relative URLs → vite proxy (dev) / same origin (prod). No hardcoded host:port.
const COLOR = {
  card:   '#12121a',
  border: '#2a2a3a',
  text:   '#e0e0e0',
  muted:  '#888888',
  green:  '#00ff88',
  red:    '#ff4444',
  yellow: '#ffaa00',
  blue:   '#00aaff',
  gray:   '#555566',
}

// Alert thresholds — MUST mirror agents/g4_reflector.py
const MIN_SAMPLE = 30
const REJECT_WARN_PCT = 5.0
const ASYMMETRY_FACTOR = 3

const POLL_MS = 30000  // Step 3: 30s polling (no dedicated WS event yet)

// ─── formatters ──────────────────────────────────────────────────────
const fmt = (v, n = 2) => {
  if (v === null || v === undefined || v === '') return '—'
  const x = Number(v)
  return Number.isFinite(x) ? x.toFixed(n) : '—'
}
const fmtInt = (v) => (v === null || v === undefined ? '—' : String(v))
const fmtTime = (iso) => (!iso ? '—' : String(iso).slice(0, 19).replace('T', ' '))
const slipColor = (v) => {
  if (v === null || v === undefined) return COLOR.muted
  const x = Number(v)
  if (!Number.isFinite(x) || x === 0) return COLOR.muted
  return x > 0 ? COLOR.red : COLOR.green   // + adverse = red, − favorable = green
}
const fmtSlip = (v) => {
  if (v === null || v === undefined) return '—'
  const x = Number(v)
  if (!Number.isFinite(x)) return '—'
  return `${x > 0 ? '+' : ''}${x.toFixed(1)}`
}

export default function ExecutionQuality() {
  // ── filters ──
  const [month, setMonth] = useState('')       // '' = current/all (summary=all)
  const [event, setEvent] = useState('all')
  const [mode, setMode] = useState('all')

  // ── data ──
  const [summary, setSummary] = useState(null)
  const [records, setRecords] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [refreshKey, setRefreshKey] = useState(0)

  const fetchAll = useCallback(async () => {
    setError(null)
    try {
      const sumQs = month ? `?months=${encodeURIComponent(month)}` : ''
      const recParams = new URLSearchParams({ limit: '200' })
      if (month) recParams.set('month', month)
      if (event !== 'all') recParams.set('event', event)

      const [sRes, rRes] = await Promise.all([
        fetch(`/api/execution/summary${sumQs}`),
        fetch(`/api/execution/records?${recParams.toString()}`),
      ])
      if (!sRes.ok || !rRes.ok) throw new Error(`HTTP ${sRes.status}/${rRes.status}`)
      const sJson = await sRes.json()
      const rJson = await rRes.json()
      setSummary(sJson)
      setRecords(rJson.records || [])
    } catch (e) {
      setError(e.message || String(e))
    } finally {
      setLoading(false)
    }
  }, [month, event])

  useEffect(() => { fetchAll() }, [fetchAll, refreshKey])

  // Step 3: poll every 30s to pick up new execution records.
  useEffect(() => {
    const id = setInterval(() => setRefreshKey(k => k + 1), POLL_MS)
    return () => clearInterval(id)
  }, [])

  const availableMonths = summary?.available_months || []

  // Client-side mode filter for the table (records endpoint doesn't filter mode).
  const viewRecords = useMemo(() => {
    if (mode === 'all') return records
    return records.filter(r => (r.mode || '') === mode)
  }, [records, mode])

  const hasData = summary && (summary.n_records > 0 || availableMonths.length > 0)

  return (
    <div style={{ padding: 24, maxWidth: 1280, margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
        <h1 style={{ fontSize: 22, fontWeight: 600 }}>⚡ Execution Quality</h1>
        <span style={{ color: COLOR.muted, fontSize: 12, fontFamily: 'monospace' }}>
          {loading ? 'loading…' : `${summary?.n_orders ?? 0} orders · ${records.length} records`}
        </span>
        <div style={{ marginLeft: 'auto' }}>
          <button onClick={() => setRefreshKey(k => k + 1)} style={btnSecondary}>↻ Refresh</button>
        </div>
      </div>

      {error && <ErrorBox message={error} />}

      {loading && !summary ? (
        <div style={{ color: COLOR.muted, fontFamily: 'monospace', padding: 40 }}>loading…</div>
      ) : !hasData ? (
        <EmptyState />
      ) : (
        <>
          <MetricRow summary={summary} />
          <AsymmetryPanel summary={summary} />
          <RecordsPanel
            records={viewRecords}
            month={month} setMonth={setMonth}
            event={event} setEvent={setEvent}
            mode={mode} setMode={setMode}
            availableMonths={availableMonths}
          />
        </>
      )}
    </div>
  )
}

// ─── Row 1: metric cards ─────────────────────────────────────────────
function MetricRow({ summary }) {
  const n = summary.n_orders || 0
  const lowSample = n < MIN_SAMPLE
  const badge = lowSample ? 'sample น้อย — ยังสรุปไม่ได้' : null

  const rej = Number(summary.rejection_rate_pct || 0)
  const asym = summary.slippage_asymmetry || {}
  const adverse = asym.adverse_count || 0
  const favorable = asym.favorable_count || 0

  // Warn colors ONLY when sample is sufficient.
  const rejWarn = !lowSample && rej > REJECT_WARN_PCT
  const asymWarn = !lowSample && adverse > favorable * ASYMMETRY_FACTOR

  const lat = summary.latency_ms || {}
  const slip = summary.slippage_pip || {}
  const entry = slip.entry || {}
  const exit = slip.exit || {}
  const spread = summary.spread_pip || {}

  return (
    <div style={{
      display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
      gap: 12, marginBottom: 20,
    }}>
      <MetricCard
        label="Orders"
        value={fmtInt(n)}
        sub={`${summary.n_closes || 0} closes · ${summary.n_paper_signals || 0} paper`}
        badge={badge} badgeColor={COLOR.gray}
      />
      <MetricCard
        label="Rejection Rate"
        value={`${fmt(rej, 1)}%`}
        sub={`${summary.n_rejected || 0} rejected`}
        color={lowSample ? COLOR.text : (rejWarn ? COLOR.yellow : COLOR.green)}
        badge={rejWarn ? `> ${REJECT_WARN_PCT}%` : null}
        badgeColor={COLOR.yellow}
      />
      <MetricCard
        label="Latency p50 / p95"
        value={`${fmt(lat.p50, 0)} / ${fmt(lat.p95, 0)}`}
        sub="ms · fill time"
        color={COLOR.blue}
      />
      <MetricCard
        label="Entry Slippage mean / p95"
        value={`${fmtSlip(entry.mean)} / ${fmtSlip(entry.p95)}`}
        sub={`pip · n=${entry.n || 0}`}
        color={slipColor(entry.mean)}
      />
      <MetricCard
        label="Close Slippage mean"
        value={fmtSlip(exit.mean)}
        sub={`pip · n=${exit.n || 0}`}
        color={slipColor(exit.mean)}
      />
      <MetricCard
        label="Spread p50 / p95"
        value={`${fmt(spread.p50, 1)} / ${fmt(spread.p95, 1)}`}
        sub={`pip · n=${spread.n || 0}`}
        color={COLOR.text}
      />
    </div>
  )
}

// ─── Row 2: slippage asymmetry ───────────────────────────────────────
function AsymmetryPanel({ summary }) {
  const asym = summary.slippage_asymmetry || {}
  const adverse = asym.adverse_count || 0
  const favorable = asym.favorable_count || 0
  const total = adverse + favorable
  const advPct = total ? (adverse / total) * 100 : 0
  const favPct = total ? (favorable / total) * 100 : 0

  return (
    <div style={panelStyle}>
      <div style={panelTitle}>Slippage Asymmetry <span style={{ color: COLOR.muted, textTransform: 'none', letterSpacing: 0 }}>· ทิศทางที่โดนปฏิบัติ</span></div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
        <SideStat
          title="Adverse · เสียเปรียบ"
          count={adverse}
          mean={asym.adverse_mean}
          color={COLOR.red}
        />
        <SideStat
          title="Favorable · ได้เปรียบ"
          count={favorable}
          mean={asym.favorable_mean}
          color={COLOR.green}
        />
      </div>

      {/* two comparison bars */}
      <Bar label="Adverse" pct={advPct} count={adverse} fill="rgba(255,68,68,0.55)" />
      <Bar label="Favorable" pct={favPct} count={favorable} fill="rgba(0,255,136,0.45)" />

      {total === 0 && (
        <div style={{ color: COLOR.muted, fontSize: 12, marginTop: 8 }}>
          ยังไม่มี slippage ที่วัดได้ (ยังไม่มีไม้ที่ fill จริง)
        </div>
      )}
    </div>
  )
}

function SideStat({ title, count, mean, color }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: COLOR.muted, marginBottom: 6 }}>{title}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
        <div style={{ fontSize: 26, fontWeight: 700, color, fontFamily: 'monospace' }}>{count}</div>
        <div style={{ fontSize: 12, color: COLOR.muted }}>ไม้</div>
        <div style={{ fontSize: 13, color, fontFamily: 'monospace', marginLeft: 'auto' }}>
          {mean === null || mean === undefined ? '—' : `${Number(mean) > 0 ? '+' : ''}${fmt(mean, 1)} pip`}
        </div>
      </div>
    </div>
  )
}

function Bar({ label, pct, count, fill }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
      <div style={{ width: 80, fontSize: 11, color: COLOR.muted }}>{label}</div>
      <div style={{ flex: 1, background: '#0d0d14', borderRadius: 4, height: 18, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: fill, transition: 'width .3s' }} />
      </div>
      <div style={{ width: 40, textAlign: 'right', fontSize: 12, color: COLOR.text, fontFamily: 'monospace' }}>
        {count}
      </div>
    </div>
  )
}

// ─── Row 3: records table ────────────────────────────────────────────
function RecordsPanel({ records, month, setMonth, event, setEvent, mode, setMode, availableMonths }) {
  return (
    <div style={panelStyle}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 14, flexWrap: 'wrap' }}>
        <div style={panelTitle}>Execution Records ({records.length})</div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <Field label="Month">
            <select value={month} onChange={e => setMonth(e.target.value)} style={inputStyle}>
              <option value="">Current</option>
              {availableMonths.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
          </Field>
          <Field label="Event">
            <select value={event} onChange={e => setEvent(e.target.value)} style={inputStyle}>
              <option value="all">All</option>
              <option value="order_send">order_send</option>
              <option value="close">close</option>
              <option value="paper_signal">paper_signal</option>
            </select>
          </Field>
          <Field label="Mode">
            <select value={mode} onChange={e => setMode(e.target.value)} style={inputStyle}>
              <option value="all">All</option>
              <option value="paper">Paper</option>
              <option value="micro">Micro</option>
              <option value="live">Live</option>
            </select>
          </Field>
        </div>
      </div>

      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ borderBottom: `1px solid ${COLOR.border}` }}>
              {['Time', 'Event', 'Mode', 'Dir', 'Req → Fill', 'Slippage', 'Spread', 'Latency', 'Retcode / Type']
                .map(h => (
                  <th key={h} style={{
                    padding: '8px 8px', textAlign: 'left', fontSize: 10,
                    color: COLOR.muted, fontWeight: 500, letterSpacing: 0.5, whiteSpace: 'nowrap',
                  }}>{h}</th>
                ))}
            </tr>
          </thead>
          <tbody>
            {records.map((r, i) => <RecordRow key={i} r={r} />)}
            {!records.length && (
              <tr><td colSpan={9} style={{ padding: 40, color: COLOR.muted, textAlign: 'center' }}>
                No records match these filters
              </td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function RecordRow({ r }) {
  const isPaper = r.event === 'paper_signal'
  const reqFill = isPaper
    ? '—'
    : `${fmt(r.requested_price, 2)} → ${fmt(r.filled_price ?? r.actual_price, 2)}`

  // Right-most col: retcode (order_send) | close_type (close) | — (paper)
  let lastCol = '—'
  if (r.event === 'order_send') {
    lastCol = r.rejected ? `⛔ ${fmtInt(r.retcode)}` : fmtInt(r.retcode)
  } else if (r.event === 'close') {
    lastCol = r.close_type || '—'
  }

  return (
    <tr style={{ borderBottom: '1px solid #1a1a1a' }}>
      <td style={cellMono}>{fmtTime(r.wall_time)}</td>
      <td>
        <span style={{
          ...badgeStyle,
          background: 'rgba(0,170,255,0.12)', color: COLOR.blue,
        }}>{r.event || '—'}</span>
      </td>
      <td style={cellMuted}>{r.mode || '—'}</td>
      <td style={cellMuted}>{r.direction || '—'}</td>
      <td style={cellMono}>{reqFill}</td>
      <td style={{ ...cellMono, color: slipColor(r.slippage_pip), fontWeight: 600 }}>
        {fmtSlip(r.slippage_pip)}
      </td>
      <td style={cellMono}>{fmt(r.spread_pip, 1)}</td>
      <td style={cellMono}>{isPaper ? '—' : fmt(r.latency_ms, 0)}</td>
      <td style={{ ...cellMono, color: r.rejected ? COLOR.red : COLOR.text }}>{lastCol}</td>
    </tr>
  )
}

// ─── shared bits ─────────────────────────────────────────────────────
const panelStyle = {
  background: COLOR.card, border: `1px solid ${COLOR.border}`,
  borderRadius: 12, padding: 16, marginBottom: 20,
}
const panelTitle = {
  fontSize: 11, color: COLOR.muted, letterSpacing: 1.5,
  textTransform: 'uppercase', marginBottom: 12,
}
const inputStyle = {
  background: '#1a1a1a', border: `1px solid ${COLOR.border}`,
  borderRadius: 6, padding: '7px 10px', color: '#fff', fontSize: 13,
}
const btnSecondary = {
  background: '#1a1a1a', border: `1px solid ${COLOR.border}`,
  borderRadius: 6, padding: '6px 14px', color: COLOR.text, fontSize: 13,
  cursor: 'pointer', fontFamily: 'inherit',
}
const cellMono = { padding: '8px 8px', fontFamily: 'monospace', color: COLOR.text, whiteSpace: 'nowrap' }
const cellMuted = { padding: '8px 8px', color: COLOR.muted, whiteSpace: 'nowrap' }
const badgeStyle = {
  display: 'inline-block', padding: '2px 8px', borderRadius: 4,
  fontSize: 10, fontWeight: 600, letterSpacing: 0.5,
}

function Field({ label, children }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: COLOR.muted, marginBottom: 4 }}>{label}</div>
      {children}
    </div>
  )
}

function EmptyState() {
  return (
    <div style={{
      background: COLOR.card, border: `1px solid ${COLOR.border}`,
      borderRadius: 12, padding: 60, textAlign: 'center',
    }}>
      <div style={{ fontSize: 32, marginBottom: 12 }}>⚡</div>
      <div style={{ fontSize: 14, color: COLOR.muted, fontFamily: 'monospace' }}>
        ยังไม่มีข้อมูล execution — ระบบเริ่มเก็บอัตโนมัติเมื่อบอทรัน
      </div>
    </div>
  )
}

function ErrorBox({ message }) {
  return (
    <div style={{
      background: 'rgba(255,68,68,0.1)', border: `1px solid ${COLOR.red}`,
      borderRadius: 8, padding: 12, marginBottom: 16, color: COLOR.red, fontSize: 13,
    }}>
      ⚠ {message}
    </div>
  )
}

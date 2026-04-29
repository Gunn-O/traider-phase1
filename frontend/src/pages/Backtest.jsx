import { useState, useEffect, useRef } from "react"
import { LineChart, Line, XAxis, YAxis, Tooltip,
         ResponsiveContainer, ReferenceLine } from "recharts"
import { Play, RefreshCw, TrendingUp, TrendingDown, Mountain } from "lucide-react"

const API = "http://127.0.0.1:8080"
const MAX_DAYS = 60  // yfinance 5m data limit

// ── Pattern icon helper ──────────────────────────────
const PatternIcon = ({ pattern }) => {
  if (pattern?.includes("mountain")) return <span>🏔</span>
  if (pattern?.includes("uptrend"))  return <span>📈</span>
  if (pattern?.includes("downtrend"))return <span>📉</span>
  return <span>📊</span>
}

// ── Summary Card ─────────────────────────────────────
const SummaryCard = ({ data }) => {
  if (!data) return null
  const { total, wins, losses, expired, wr_pct, net_pnl, avg_win, avg_loss } = data
  const closed = (wins||0) + (losses||0)

  return (
    <div style={{
      background: "#111", border: "1px solid #222",
      borderRadius: 12, padding: 24, marginBottom: 20
    }}>
      <h3 style={{ color: "#aaa", fontSize: 13, marginBottom: 16,
                   letterSpacing: 2, textTransform: "uppercase" }}>
        สรุปรวม
      </h3>

      {/* Stats row */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 16, marginBottom: 20 }}>
        {[
          { label: "เทรดทั้งหมด", value: total, sub: `${closed} closed` },
          { label: "Win Rate",    value: `${(wr_pct||0).toFixed(1)}%`,
            color: wr_pct >= 60 ? "#00ff88" : wr_pct >= 45 ? "#ffaa00" : "#ff4444" },
          { label: "ชนะ", value: wins||0, color: "#00ff88" },
          { label: "แพ้", value: losses||0, color: "#ff4444" },
        ].map(({ label, value, sub, color }) => (
          <div key={label} style={{
            background: "#1a1a1a", borderRadius: 8, padding: "16px 12px", textAlign: "center"
          }}>
            <div style={{ fontSize: 28, fontWeight: 700, color: color || "#fff",
                          fontFamily: "monospace" }}>{value}</div>
            <div style={{ fontSize: 12, color: "#666", marginTop: 4 }}>{label}</div>
            {sub && <div style={{ fontSize: 11, color: "#444" }}>{sub}</div>}
          </div>
        ))}
      </div>

      {/* P&L row */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 16 }}>
        {[
          { label: "กำไรสุทธิ (Net P&L)",
            value: `${net_pnl >= 0 ? "+" : ""}$${(net_pnl||0).toFixed(2)}`,
            color: net_pnl >= 0 ? "#00ff88" : "#ff4444" },
          { label: "เฉลี่ยชนะ / trade",
            value: `+$${(avg_win||0).toFixed(2)}`, color: "#00ff88" },
          { label: "เฉลี่ยแพ้ / trade",
            value: `-$${Math.abs(avg_loss||0).toFixed(2)}`, color: "#ff4444" },
        ].map(({ label, value, color }) => (
          <div key={label} style={{
            background: "#1a1a1a", borderRadius: 8, padding: "12px 16px",
            display: "flex", justifyContent: "space-between", alignItems: "center"
          }}>
            <span style={{ fontSize: 13, color: "#666" }}>{label}</span>
            <span style={{ fontSize: 18, fontWeight: 700, color, fontFamily: "monospace" }}>
              {value}
            </span>
          </div>
        ))}
      </div>

      {expired > 0 && (
        <div style={{ marginTop: 12, padding: "8px 12px", background: "#1a1500",
                      borderRadius: 6, fontSize: 12, color: "#888" }}>
          ⚠️ {expired} trades หมดเวลา (PENDING_EXPIRED) — เปิดใกล้สิ้นสุด backtest
        </div>
      )}
    </div>
  )
}

// ── Pattern Breakdown Table ───────────────────────────
const PatternTable = ({ data }) => {
  if (!data?.length) return null
  return (
    <div style={{
      background: "#111", border: "1px solid #222",
      borderRadius: 12, padding: 24, marginBottom: 20
    }}>
      <h3 style={{ color: "#aaa", fontSize: 13, marginBottom: 16,
                   letterSpacing: 2, textTransform: "uppercase" }}>
        แยกตามลักษณะกราฟ
      </h3>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ borderBottom: "1px solid #222" }}>
            {["Pattern","ทั้งหมด","ชนะ","แพ้","WR%","Net USD"].map(h => (
              <th key={h} style={{ padding: "8px 12px", textAlign: h === "Pattern" ? "left" : "right",
                                   fontSize: 12, color: "#555", fontWeight: 500 }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map(p => {
            const wr = p.total ? (p.wins / p.total * 100) : 0
            return (
              <tr key={p.pattern} style={{ borderBottom: "1px solid #1a1a1a" }}>
                <td style={{ padding: "12px 12px", color: "#ddd" }}>
                  <PatternIcon pattern={p.pattern} />
                  {" "}{p.pattern}
                </td>
                <td style={{ padding: "12px 12px", textAlign: "right", color: "#888" }}>
                  {p.total}
                </td>
                <td style={{ padding: "12px 12px", textAlign: "right", color: "#00ff88" }}>
                  {p.wins}
                </td>
                <td style={{ padding: "12px 12px", textAlign: "right", color: "#ff4444" }}>
                  {p.losses}
                </td>
                <td style={{ padding: "12px 12px", textAlign: "right",
                             color: wr >= 60 ? "#00ff88" : wr >= 45 ? "#ffaa00" : "#ff4444",
                             fontWeight: 600 }}>
                  {wr.toFixed(1)}%
                </td>
                <td style={{ padding: "12px 12px", textAlign: "right", fontFamily: "monospace",
                             color: p.net_pnl_usd >= 0 ? "#00ff88" : "#ff4444" }}>
                  {p.net_pnl_usd >= 0 ? "+" : ""}${(p.net_pnl_usd||0).toFixed(2)}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ── Equity Curve ─────────────────────────────────────
const EquityCurve = ({ data }) => {
  if (!data?.length) return null
  const minVal = Math.min(...data.map(d => d.balance))
  const maxVal = Math.max(...data.map(d => d.balance))

  return (
    <div style={{
      background: "#111", border: "1px solid #222",
      borderRadius: 12, padding: 24, marginBottom: 20
    }}>
      <h3 style={{ color: "#aaa", fontSize: 13, marginBottom: 16,
                   letterSpacing: 2, textTransform: "uppercase" }}>
        Equity Curve
      </h3>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data}>
          <XAxis dataKey="timestamp" hide />
          <YAxis domain={[minVal * 0.98, maxVal * 1.02]}
                 tickFormatter={v => `$${v.toFixed(0)}`}
                 tick={{ fill: "#555", fontSize: 11 }} width={70} />
          <Tooltip
            formatter={(v) => [`$${v.toFixed(2)}`, "Balance"]}
            contentStyle={{ background: "#1a1a1a", border: "1px solid #333",
                            borderRadius: 6, fontSize: 12 }}
          />
          <ReferenceLine y={1000} stroke="#333" strokeDasharray="4 4" />
          <Line type="monotone" dataKey="balance"
                stroke="#00ff88" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

// ── Trade List ────────────────────────────────────────
const TradeList = ({ trades }) => {
  const [expanded, setExpanded] = useState(null)
  if (!trades?.length) return null

  return (
    <div style={{
      background: "#111", border: "1px solid #222",
      borderRadius: 12, padding: 24
    }}>
      <h3 style={{ color: "#aaa", fontSize: 13, marginBottom: 16,
                   letterSpacing: 2, textTransform: "uppercase" }}>
        Trade List ({trades.length})
      </h3>
      <div style={{ maxHeight: 400, overflowY: "auto" }}>
        {trades.map((t, i) => (
          <div key={t.trade_id || i}
               onClick={() => setExpanded(expanded === i ? null : i)}
               style={{
                 borderBottom: "1px solid #1a1a1a", padding: "10px 8px",
                 cursor: "pointer", borderRadius: 4,
                 background: expanded === i ? "#1a1a1a" : "transparent"
               }}>
            {/* Row */}
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span style={{ fontSize: 11, color: "#555", width: 140, flexShrink: 0 }}>
                {t.timestamp_open?.slice(0,16).replace("T"," ")}
              </span>
              <PatternIcon pattern={t.chart_type} />
              <span style={{ fontSize: 12, color: "#888", flex: 1 }}>
                {t.chart_type?.toUpperCase()} {t.action}
              </span>
              <span style={{ fontFamily: "monospace", fontSize: 12,
                             color: t.result === "WIN" ? "#00ff88"
                                  : t.result === "LOSS" ? "#ff4444"
                                  : "#555" }}>
                {t.result === "WIN" ? `+$${t.pnl_usd?.toFixed(2)}`
               : t.result === "LOSS" ? `-$${Math.abs(t.pnl_usd)?.toFixed(2)}`
               : t.result}
              </span>
            </div>

            {/* Expanded detail */}
            {expanded === i && (
              <div style={{ marginTop: 10, padding: "10px 8px",
                            background: "#141414", borderRadius: 6,
                            display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 8 }}>
                {[
                  ["Entry",  `$${t.entry_price?.toFixed(2)}`],
                  ["SL",     `$${t.sl_price?.toFixed(2)}`],
                  ["TP",     `$${t.tp_price?.toFixed(2)}`],
                  ["Lot",    t.lot_size?.toFixed(2)],
                  ["R:R",    t.rr_ratio?.toFixed(2)],
                  ["Session",t.session],
                ].map(([label, value]) => (
                  <div key={label}>
                    <div style={{ fontSize: 10, color: "#555" }}>{label}</div>
                    <div style={{ fontSize: 13, color: "#ccc", fontFamily: "monospace" }}>
                      {value}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────
export default function Backtest() {
  const [startDate, setStartDate] = useState("2026-04-01")
  const [endDate,   setEndDate]   = useState("2026-04-21")
  const [results,   setResults]   = useState(null)
  const [loading,   setLoading]   = useState(false)
  const [polling,   setPolling]   = useState(false)
  const [dateError, setDateError] = useState("")
  const pollRef = useRef(null)

  const fetchResults = async () => {
    const res = await fetch(`${API}/api/backtest/results`)
    if (res.ok) setResults(await res.json())
  }

  const handleRun = async () => {
    // Validate dates
    const s = new Date(startDate)
    const e = new Date(endDate)
    const days = Math.round((e - s) / 86400000)

    if (e <= s) {
      setDateError("End date ต้องมากกว่า Start date")
      return
    }
    if (days > MAX_DAYS) {
      setDateError(`สูงสุด ${MAX_DAYS} วัน (เลือก ${days} วัน)`)
      return
    }
    setDateError("")

    setLoading(true)
    setResults(null)
    const res = await fetch(`${API}/api/backtest/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ start: startDate, end: endDate })
    })

    const data = await res.json()
    if (data.status === "error") {
      setDateError(data.message)
      setLoading(false)
      return
    }

    // Poll status ทุก 3 วินาที
    setPolling(true)
    pollRef.current = setInterval(async () => {
      const s = await fetch(`${API}/api/backtest/status`).then(r => r.json())
      if (!s.is_running) {
        clearInterval(pollRef.current)
        setPolling(false)
        setLoading(false)
        await fetchResults()
      }
    }, 3000)
  }

  useEffect(() => {
    fetchResults()  // load ผลล่าสุดเมื่อเปิดหน้า
    return () => clearInterval(pollRef.current)
  }, [])

  return (
    <div style={{ padding: 24, maxWidth: 960, margin: "0 auto" }}>
      {/* Header */}
      <h2 style={{ color: "#fff", marginBottom: 24, fontSize: 22, fontWeight: 600 }}>
        📊 Backtest
      </h2>

      {/* Controls */}
      <div style={{
        background: "#111", border: "1px solid #222",
        borderRadius: 12, padding: 20, marginBottom: 20,
        display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap"
      }}>
        {[
          { label: "Start Date", value: startDate, set: setStartDate },
          { label: "End Date",   value: endDate,   set: setEndDate },
        ].map(({ label, value, set }) => (
          <div key={label}>
            <div style={{ fontSize: 11, color: "#555", marginBottom: 4 }}>{label}</div>
            <input type="date" value={value}
                   onChange={e => {
                     set(e.target.value)
                     setDateError("")
                   }}
                   style={{
                     background: "#1a1a1a", border: "1px solid #333",
                     borderRadius: 6, padding: "8px 12px",
                     color: "#fff", fontSize: 14
                   }} />
          </div>
        ))}

        {/* Day count indicator */}
        {startDate && endDate && (() => {
          const days = Math.round(
            (new Date(endDate) - new Date(startDate)) / 86400000
          )
          const color = days > MAX_DAYS ? "#ff4444"
                      : days > MAX_DAYS * 0.8 ? "#ffaa00"
                      : "#00ff88"
          return (
            <div style={{ marginTop: 18, fontSize: 12, color }}>
              {days} วัน {days > MAX_DAYS ? `(เกิน limit ${MAX_DAYS} วัน)` : ""}
            </div>
          )
        })()}

        {/* Preset buttons */}
        <div style={{ marginTop: 18 }}>
          <div style={{ fontSize: 11, color: "#555", marginBottom: 6 }}>
            Preset
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            {[
              { label: "1W",  days: 7  },
              { label: "2W",  days: 14 },
              { label: "1M",  days: 30 },
              { label: "2M",  days: 60 },
            ].map(({ label, days }) => {
              const end   = new Date()
              const start = new Date(end - days * 86400000)
              const fmt   = d => d.toISOString().slice(0,10)
              const currentDays = Math.round(
                (new Date(endDate) - new Date(startDate)) / 86400000
              )
              const active = currentDays === days
              return (
                <button key={label}
                  onClick={() => {
                    setStartDate(fmt(start))
                    setEndDate(fmt(end))
                    setDateError("")
                  }}
                  style={{
                    padding: "4px 12px",
                    background: active ? "#00ff88" : "#1a1a1a",
                    color: active ? "#000" : "#888",
                    border: `1px solid ${active ? "#00ff88" : "#333"}`,
                    borderRadius: 4, fontSize: 12, cursor: "pointer"
                  }}>
                  {label}
                </button>
              )
            })}
          </div>
        </div>

        {/* Error message */}
        {dateError && (
          <div style={{
            width: "100%",
            marginTop: 12, padding: "8px 12px",
            background: "#1a0000", border: "1px solid #440000",
            borderRadius: 6, fontSize: 12, color: "#ff4444"
          }}>
            ❌ {dateError}
          </div>
        )}

        <button onClick={handleRun} disabled={loading}
                style={{
                  marginTop: 18, padding: "9px 24px",
                  background: loading ? "#333" : "#00ff88",
                  color: loading ? "#888" : "#000",
                  border: "none", borderRadius: 6,
                  fontSize: 14, fontWeight: 600, cursor: loading ? "not-allowed" : "pointer",
                  display: "flex", alignItems: "center", gap: 8
                }}>
          {loading
            ? <><RefreshCw size={14} style={{ animation: "spin 1s linear infinite" }} /> รัน Backtest...</>
            : <><Play size={14} /> รัน Backtest</>}
        </button>

        {polling && (
          <div style={{ fontSize: 12, color: "#ffaa00" }}>
            ⏳ กำลังประมวลผล...
          </div>
        )}
      </div>

      {/* Results */}
      {results ? (
        <>
          <SummaryCard   data={results.summary} />
          <PatternTable  data={results.by_pattern} />
          <EquityCurve   data={results.equity_curve} />
          <TradeList     trades={results.trades} />
        </>
      ) : !loading ? (
        <div style={{
          textAlign: "center", padding: 60,
          color: "#444", fontSize: 14
        }}>
          กด "รัน Backtest" เพื่อเริ่มต้น
        </div>
      ) : null}

      <style>{`
        @keyframes spin { to { transform: rotate(360deg) } }
        input[type=date]::-webkit-calendar-picker-indicator { filter: invert(0.5) }
      `}</style>
    </div>
  )
}

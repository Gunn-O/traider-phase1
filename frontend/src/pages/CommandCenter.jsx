import { useMemo, useState, lazy, Suspense } from 'react'
import { useTradeStats } from '../hooks/useTradeStats'
import { Panel, StatTile, Pill, Glyph, I } from '../components/ui/primitives'
import { EquityCurve, Donut, Meter } from '../components/ui/charts'
import PositionsTable from '../components/PositionsTable'
import SignalFeed from '../components/SignalFeed'
import LiveSnapshot from '../components/LiveSnapshot'
import RunningBotsTable from '../components/RunningBotsTable'
import ChartPanel from '../components/ChartPanel'
import { FMT } from '../utils/format'

// three.js is heavy — keep it out of the initial bundle / isolate WebGL.
const MarketModel3D = lazy(() => import('../components/MarketModel3D'))

export default function CommandCenter({ bots = [], account, onAddBot, onStop, isConnected = true }) {
  const stats = useTradeStats()
  const [filterBotId, setFilterBotId] = useState('')

  const running = bots.filter((b) => b.status === 'running')
  const visibleBots = useMemo(
    () => (filterBotId ? bots.filter((b) => b.bot_id === filterBotId) : bots),
    [bots, filterBotId]
  )

  const open = useMemo(() => visibleBots.flatMap((b) => (b.open_orders || []).map((o) => ({ ...o, bot_id: b.bot_id }))), [visibleBots])
  const closed = useMemo(() => visibleBots.flatMap((b) => (b.closed_orders || []).map((o) => ({ ...o, bot_id: b.bot_id }))), [visibleBots])

  const signalEvents = useMemo(() => {
    const all = []
    for (const b of visibleBots) {
      for (const e of (b.events || [])) {
        if (e.type === 'signal_detected' || e.type === 'signal_skipped') all.push({ ...e, bot_id: b.bot_id })
      }
    }
    return all.sort((a, b) => String(b.ts || '').localeCompare(String(a.ts || ''))).slice(0, 12)
  }, [visibleBots])

  const bal = account?.balance, eq = account?.equity, floating = account?.floating
  const wr = stats?.wr_pct
  const dd = stats?.max_drawdown_pct ?? stats?.max_dd_pct
  const wins = stats?.wins ?? 0, losses = stats?.losses ?? 0
  const equityCurve = (stats?.equity_curve || []).map((p) => ({ label: p.t, equity: p.balance ?? p.equity }))
  const openPos = open.length
  const health = account?.connected ? 96 : 40

  // Newest heartbeat across running bots → proves the WS/poll is live.
  const newestHb = running.map((b) => b.heartbeat?.ts).filter(Boolean).sort().slice(-1)[0]
  const hbAge = newestHb ? Math.max(0, Math.floor((Date.now() - new Date(newestHb).getTime()) / 1000)) : null

  return (
    <div className="view">
      <div className="status-banner">
        <div className="sb-left">
          <Glyph d={I.bolt} size={22} />
          <div>
            <b>{running.length > 0 ? 'LIVE · XAUUSD AGENT FLOOR' : 'STANDBY · NO BOTS ACTIVE'}</b>
            <span> · ระบบเอเจนต์อัตโนมัติ · 3D market model + live scan</span>
          </div>
        </div>
        <div className="sb-right">
          <Pill tone="gold" solid>{running[0]?.mode?.toUpperCase() || 'IDLE'}</Pill>
          <Pill tone="cyan">{account?.connected ? 'MT5 LINKED' : 'MT5 OFFLINE'}</Pill>
        </div>
      </div>

      {/* System health strip — tells "connected + scanning" apart from "broken" */}
      <HealthStrip isConnected={isConnected} activeCount={running.length} hbAge={hbAge} />

      {/* 1) 3D MARKET MODEL (replaces the Virtual Office on the dashboard) */}
      <Panel title="MARKET EVOLUTION · 3D" titleTh="พื้นผิว 3 มิติ · volume@price heatmap (เวลา × ราคา) · ลากเพื่อหมุน" live accent="cyan">
        <Suspense fallback={<div className="market3d-fallback">Loading 3D engine…</div>}>
          <MarketModel3D bots={visibleBots} />
        </Suspense>
      </Panel>

      {/* Restored 2D candlestick chart */}
      <ChartPanel bots={visibleBots} />

      {/* Running bots — with per-bot Stop + filter */}
      <Panel title="BOTS" titleTh="บอททั้งหมด · กดเพื่อกรอง / หยุดทีละตัว" accent="cyan">
        <RunningBotsTable bots={bots} onStop={onStop} filterBotId={filterBotId} onFilterChange={setFilterBotId} />
      </Panel>

      {/* Live snapshot — the real per-cycle signal scanning view (heartbeat) */}
      <Panel title="LIVE SNAPSHOT" titleTh="สแกนสัญญาณสด · เหตุผลที่แต่ละกลยุทธ์ยังไม่เข้า (อัปเดตทุก candle)" live accent="green">
        <LiveSnapshot bots={visibleBots} />
      </Panel>

      {/* STAT TILES */}
      <div className="stat-row">
        <StatTile icon={<Glyph d={I.wallet} />} label="BALANCE" labelTh="ยอดเงิน" value={bal != null ? FMT.usd(bal) : '—'} tone="cyan" sub="USD" />
        <StatTile icon={<Glyph d={I.chart} />} label="EQUITY" labelTh="ทุนสุทธิ" value={eq != null ? FMT.usd(eq) : '—'} tone="cyan" sub="USD" />
        <StatTile icon={<Glyph d={I.pulse} />} label="FLOATING" labelTh="กำไรลอยตัว" value={floating != null ? FMT.usd(floating) : '—'}
          tone={floating >= 0 ? 'green' : 'red'} sub={eq && floating != null ? FMT.pct((floating / eq) * 100) : ''} trend={floating >= 0 ? 'up' : 'down'} />
        <StatTile icon={<Glyph d={I.target} />} label="WIN RATE" labelTh="อัตราชนะ" value={wr != null ? wr.toFixed(1) : '—'} unit="%" tone="green"
          sub={`${wins}W ${losses}L`} />
        <StatTile icon={<Glyph d={I.shield} />} label="MAX DD" labelTh="ดรอว์ดาวน์" value={dd != null ? dd.toFixed(1) : '—'} unit="%" tone="gold" />
        <StatTile icon={<Glyph d={I.layers} />} label="OPEN POS" labelTh="ออเดอร์เปิด" value={openPos} tone="magenta" sub={`${running.length} bot(s)`} />
      </div>

      {/* charts grid */}
      <div className="grid-3">
        <Panel title="EQUITY CURVE" titleTh="เส้นทุน · realized" live className="span-2" accent="cyan">
          <div className="legend mono"><span><i className="dot dot-cyan" /> Equity</span></div>
          <EquityCurve data={equityCurve} />
        </Panel>
        <Panel title="HEALTH" titleTh="สุขภาพระบบ" accent="green">
          <div className="health-donut">
            <Donut value={health} label={health} sub={account?.connected ? '/100 GOOD' : '/100 LINK?'} tone={account?.connected ? 'green' : 'gold'} size={140} />
          </div>
          <div className="health-bars">
            <div className="health-row"><span className="hr-k">MT5 Link<em>เชื่อมต่อ</em></span><Meter value={account?.connected ? 99.9 : 0} tone="cyan" /></div>
            <div className="health-row"><span className="hr-k">Bots Active<em>บอททำงาน</em></span><Meter value={running.length} max={Math.max(running.length, 6)} tone="green" unit="" /></div>
            <div className="health-row"><span className="hr-k">WebSocket<em>เรียลไทม์</em></span><Meter value={isConnected ? 100 : 0} tone={isConnected ? 'magenta' : 'red'} /></div>
          </div>
        </Panel>
      </div>

      <Panel title="POSITIONS" titleTh="ออเดอร์ · จัดกลุ่มตามแผน (1 แผน = 1 แถว)" live accent="magenta">
        <PositionsTable open={open} closed={closed} />
      </Panel>

      <Panel title="SIGNAL FEED" titleTh="ฟีดสัญญาณ · เฉพาะตอนที่ setup ยิงจริง (ดูการสแกนสดที่ Live Snapshot ด้านบน)" live accent="cyan">
        <SignalFeed events={signalEvents} />
      </Panel>
    </div>
  )
}

function HealthStrip({ isConnected, activeCount, hbAge }) {
  const state = !isConnected ? 'down' : activeCount === 0 ? 'idle' : 'live'
  const dot = state === 'live' ? 'var(--c-green)' : state === 'idle' ? 'var(--c-gold)' : 'var(--c-red)'
  const text = state === 'down'
    ? '⚠ WS DISCONNECTED — backend ทำงานอยู่ไหม? (เปิด api_server / launcher)'
    : state === 'idle'
      ? 'CONNECTED · ไม่มีบอททำงาน — กด + Add Bot เพื่อเริ่มสแกน'
      : `LIVE · ${activeCount} active · scanning`
  return (
    <div className={`health-strip ${state}`}>
      <span className="hs-item">
        <span className="led" style={{ background: dot, boxShadow: `0 0 8px ${dot}` }} />
        <b>{text}</b>
      </span>
      <span className="hs-sep" />
      <span className="hs-item"><span className="mono">WS</span> {isConnected ? <span className="pos">connected</span> : <span className="neg">offline</span>}</span>
      {state === 'live' && (
        <>
          <span className="hs-sep" />
          <span className="hs-item"><span className="mono">last heartbeat</span> {hbAge != null ? <span className={hbAge < 90 ? 'pos' : 'neg'}>{hbAge < 90 ? `${hbAge}s ago` : `${Math.floor(hbAge / 60)}m ago`}</span> : <span className="dim">—</span>}</span>
        </>
      )}
    </div>
  )
}

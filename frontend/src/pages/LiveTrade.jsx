import { useMemo } from 'react'
import BotControlBar from '../components/BotControlBar'
import { Panel, StatTile, Glyph, I } from '../components/ui/primitives'
import { EquityCurve } from '../components/ui/charts'
import PositionsTable from '../components/PositionsTable'
import SignalFeed from '../components/SignalFeed'
import LiveSnapshot from '../components/LiveSnapshot'
import ChartPanel from '../components/ChartPanel'
import { useTradeStats } from '../hooks/useTradeStats'
import { FMT } from '../utils/format'

// Live Trade — bot control bar + live stats + grouped OPEN POSITIONS +
// closed TRADE LOG + signal feed + equity curve.
export default function LiveTrade({ bots = [], account, onAddBot, onEmergencyStop, onStop }) {
  const stats = useTradeStats()
  const running = bots.filter((b) => b.status === 'running')

  const open = useMemo(() => bots.flatMap((b) => (b.open_orders || []).map((o) => ({ ...o, bot_id: b.bot_id }))), [bots])
  const closed = useMemo(() => bots.flatMap((b) => (b.closed_orders || []).map((o) => ({ ...o, bot_id: b.bot_id }))), [bots])

  const signalEvents = useMemo(() => {
    const all = []
    for (const b of bots) for (const e of (b.events || [])) {
      if (e.type === 'signal_detected' || e.type === 'signal_skipped') all.push({ ...e, bot_id: b.bot_id })
    }
    return all.sort((a, b) => String(b.ts || '').localeCompare(String(a.ts || ''))).slice(0, 20)
  }, [bots])

  const equityCurve = (stats?.equity_curve || []).map((p) => ({ label: p.t, equity: p.balance ?? p.equity }))
  const eq = account?.equity, floating = account?.floating

  return (
    <div className="view">
      <div className="view-head">
        <div><h1>LIVE TRADE · XAUUSD</h1><p>คำสั่งซื้อขายสด · จัดการโดย Signal Engine → G3 Risk Gate → G4 Monitor</p></div>
      </div>

      <BotControlBar bots={bots} onAddBot={onAddBot} onEmergencyStop={onEmergencyStop} onStop={onStop} />

      <ChartPanel bots={bots} />

      <div className="stat-row five">
        <StatTile icon={<Glyph d={I.target} />} label="EQUITY" labelTh="ทุนสุทธิ" value={eq != null ? FMT.usd(eq) : '—'} tone="gold" />
        <StatTile icon={<Glyph d={I.layers} />} label="OPEN POS" labelTh="ออเดอร์เปิด" value={open.length} tone="magenta" sub={`${running.length} bot(s)`} />
        <StatTile icon={<Glyph d={I.pulse} />} label="FLOATING" labelTh="ลอยตัว" value={floating != null ? FMT.usd(floating) : '—'} tone={floating >= 0 ? 'green' : 'red'} trend={floating >= 0 ? 'up' : 'down'} />
        <StatTile icon={<Glyph d={I.shield} />} label="MARGIN" labelTh="มาร์จิน" value={account?.marginUsed != null ? FMT.usd(account.marginUsed) : '—'} tone="cyan" sub={account?.freeMargin != null ? `free ${FMT.usd(account.freeMargin, 0)}` : ''} />
        <StatTile icon={<Glyph d={I.power} />} label="MODE" labelTh="โหมด" value={(running[0]?.mode || 'IDLE').toUpperCase()} tone="green" sub={account?.connected ? 'MT5 linked' : 'offline'} />
      </div>

      <Panel title="LIVE SNAPSHOT" titleTh="สแกนสัญญาณสด · เหตุผลที่แต่ละกลยุทธ์ยังไม่เข้า" live accent="green">
        <LiveSnapshot bots={bots} />
      </Panel>

      <Panel title="OPEN POSITIONS" titleTh="ออเดอร์ที่เปิดอยู่ · จัดกลุ่มตามแผน (MaiRuay 3 ไม้ = 1 แถว)" live accent="magenta">
        <PositionsTable open={open} closed={[]} showClosed={false} />
      </Panel>

      <Panel title="TRADE LOG" titleTh="บันทึกการเทรดที่ปิดแล้ว" accent="gold">
        <PositionsTable open={[]} closed={closed} />
      </Panel>

      <div className="grid-2">
        <Panel title="SIGNAL FEED" titleTh="ฟีดสัญญาณล่าสุด" live accent="cyan"><SignalFeed events={signalEvents} /></Panel>
        <Panel title="EQUITY CURVE" titleTh="เส้นทุน" accent="cyan"><EquityCurve data={equityCurve} height={260} /></Panel>
      </div>
    </div>
  )
}

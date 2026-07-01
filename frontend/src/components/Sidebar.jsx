import { NavLink } from 'react-router-dom'
import { Glyph, I } from './ui/primitives'
import { FMT } from '../utils/format'

// Command Deck sidebar — bilingual nav + live account tile.
const NAV = [
  { section: 'FLOOR · ชั้นปฏิบัติการ', items: [
    { path: '/dashboard', label: 'Command Center', th: 'ศูนย์บัญชาการ', icon: I.grid, live: true },
    { path: '/office', label: 'Virtual Office', th: 'ห้องเอเจนต์', icon: I.cpu, badge: '9' },
    { path: '/trade', label: 'Live Trade', th: 'เทรดสด', icon: I.chart, live: true },
  ] },
  { section: 'STRATEGY · กลยุทธ์', items: [
    { path: '/strategy', label: 'Strategy', th: 'กลยุทธ์', icon: I.layers },
    { path: '/backtest', label: 'Backtest', th: 'ทดสอบย้อนหลัง', icon: I.flask },
    { path: '/history', label: 'Trade History', th: 'ประวัติเทรด', icon: I.history },
  ] },
  { section: 'SYSTEM · ระบบ', items: [
    { path: '/alerts', label: 'Alert Center', th: 'แจ้งเตือน', icon: I.bell, countKey: 'alerts' },
    { path: '/proposals', label: 'Proposals', th: 'ข้อเสนอกลยุทธ์', icon: I.doc, countKey: 'proposals' },
    { path: '/settings', label: 'Settings', th: 'ตั้งค่า', icon: I.settings },
  ] },
]

export default function Sidebar({ account, isConnected, counts = {} }) {
  const bal = account?.balance
  const eq = account?.equity
  const floating = account?.floating ?? (eq != null && bal != null ? eq - bal : null)
  const meterPct = bal && eq ? Math.min(100, Math.max(0, (eq / bal) * 100)) : 0

  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-logo"><span className="mono">TR</span></div>
        <div>
          <div className="brand-name">TRA<span className="i">(i)</span>DER</div>
          <div className="brand-sub mono">XAUUSD · AGENT OS</div>
        </div>
      </div>

      <div className="side-account">
        <div className="sa-row"><span className="label-dim">ACCOUNT</span><span className="mono">{account?.login || '—'}</span></div>
        <div className="sa-bal mono">{bal != null ? FMT.usd(bal) : '—'}</div>
        <div className="sa-eq mono">
          EQ {eq != null ? FMT.usd(eq) : '—'}
          {floating != null && <> · <span className={floating >= 0 ? 'pos' : 'neg'}>{FMT.signed(floating)}</span></>}
        </div>
        <div className="sa-meter"><div className="sa-meter-fill" style={{ width: `${meterPct}%` }} /></div>
      </div>

      <nav className="nav">
        {NAV.map((sec) => (
          <div key={sec.section}>
            <div className="nav-label mono">{sec.section}</div>
            {sec.items.map((n) => (
              <NavLink key={n.path} to={n.path} className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
                <span className="ni-icon"><Glyph d={n.icon} size={18} /></span>
                <span className="ni-text"><span className="ni-en">{n.label}</span><span className="ni-th">{n.th}</span></span>
                {n.live && <span className="ni-live mono">LIVE</span>}
                {n.badge && <span className="ni-badge mono">{n.badge}</span>}
                {n.countKey && counts[n.countKey] > 0 && <span className="ni-count mono">{counts[n.countKey]}</span>}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>

      <div className="side-foot mono">
        <div>TRAIDER · {isConnected ? 'LIVE LINK' : 'OFFLINE'}</div>
        <div className="dim">PHASE II · MT5 TWIN</div>
      </div>
    </aside>
  )
}

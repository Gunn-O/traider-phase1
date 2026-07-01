import { useState } from 'react'
import { Glyph, I } from '../components/ui/primitives'

// Login — cyberpunk command-deck entry gate (demo; click to enter).
export default function Login({ onEnter }) {
  const [u, setU] = useState('commander')
  const [p, setP] = useState('traider26')
  const stats = [
    ['9', 'AGENTS', 'เอเจนต์'], ['3', 'STRATEGIES', 'กลยุทธ์'], ['MT5', 'LIVE LINK', 'เชื่อมต่อ'],
    ['XAUUSD', 'SYMBOL', 'สัญลักษณ์'], ['1:1', 'REAL TWIN', 'เรียลไทม์'], ['24/7', 'MONITOR', 'เฝ้าระวัง'],
  ]
  return (
    <div className="login-screen">
      <div className="login-rain" />
      <div className="login-grid-bg" />
      <div className="login-card">
        <div className="login-left">
          <div className="login-brand">
            <div className="brand-logo lg"><span className="mono">TR</span></div>
            <div>
              <div className="login-title">TRA<span className="i">(i)</span>DER</div>
              <div className="login-tag mono">XAUUSD · AGENT TRADING OS</div>
            </div>
          </div>
          <p className="login-lede">
            ระบบเทรดทองอัตโนมัติ ขับเคลื่อนด้วยเอเจนต์ <b>Signal Engine → G2 Prefilter → G3 Risk Gate → G4 Monitor</b>
          </p>
          <div className="login-stats">
            {stats.map((s, i) => (
              <div className="ls-tile" key={i}><div className="mono ls-v">{s[0]}</div><div className="ls-k">{s[1]}</div><div className="ls-kth">{s[2]}</div></div>
            ))}
          </div>
          <div className="login-foot mono dim">TRAIDER PHASE II · MT5 TWIN</div>
        </div>
        <div className="login-right">
          <div className="lr-head">
            <h2>OPERATOR LOGIN</h2>
            <span className="status-chip on"><span className="led" style={{ background: 'var(--c-green)', boxShadow: '0 0 8px var(--c-green)' }} /> ONLINE</span>
          </div>
          <p className="lr-sub">เข้าสู่ห้องบัญชาการเทรด</p>
          <label className="field-label mono">USERNAME</label>
          <div className="field"><Glyph d={I.cpu} size={17} /><input value={u} onChange={(e) => setU(e.target.value)} /></div>
          <label className="field-label mono">PASSWORD</label>
          <div className="field"><Glyph d={I.shield} size={17} /><input type="password" value={p} onChange={(e) => setP(e.target.value)} /></div>
          <button className="cd-btn btn-enter" onClick={onEnter}>→ ENTER COMMAND DECK</button>
          <div className="lr-demo mono dim">DEMO · คลิกปุ่มเพื่อเข้าสู่ระบบ</div>
        </div>
      </div>
    </div>
  )
}

// primitives.jsx — shared Command Deck UI primitives (Panel, StatTile, Pill, Glyph + icons).
// Ported from the design bundle's ui.jsx. Theme-aware via CSS vars.

const TONE = {
  cyan: 'var(--c-cyan)',
  magenta: 'var(--c-magenta)',
  gold: 'var(--c-gold)',
  green: 'var(--c-green)',
  red: 'var(--c-red)',
}
const tone = (t) => TONE[t] || TONE.cyan

export function Panel({ title, titleTh, live, right, children, className = '', accent = 'cyan' }) {
  return (
    <section className={`panel ${className}`}>
      {(title || right) && (
        <div className="panel-head">
          <div className="ph-title">
            <span className={`ph-bar bar-${accent}`} />
            <div>
              {title && <h2>{title}</h2>}
              {titleTh && <span className="ph-sub">{titleTh}</span>}
            </div>
            {live && <span className="chip-live">● LIVE</span>}
          </div>
          {right && <div className="ph-right">{right}</div>}
        </div>
      )}
      {children}
    </section>
  )
}

export function StatTile({ icon, label, labelTh, value, unit, sub, tone: t = 'cyan', trend }) {
  const col = tone(t)
  return (
    <div className="stat-tile" style={{ '--tc': col }}>
      <span className="hud-corner tl" /><span className="hud-corner br" />
      <div className="st-top">
        <span className="st-icon" style={{ color: col, borderColor: col }}>{icon}</span>
        <div className="st-labels">
          <div className="st-label">{label}</div>
          {labelTh && <div className="st-label-th">{labelTh}</div>}
        </div>
      </div>
      <div className="st-value mono">
        {value}{unit && <span className="st-unit">{unit}</span>}
      </div>
      {sub && (
        <div
          className="st-sub mono"
          style={{ color: trend === 'up' ? 'var(--c-green)' : trend === 'down' ? 'var(--c-red)' : 'var(--muted)' }}
        >
          {sub}
        </div>
      )}
    </div>
  )
}

export function Pill({ children, tone: t = 'cyan', solid }) {
  const col = tone(t)
  const style = solid
    ? { background: col, color: '#04070e', borderColor: col }
    : { color: col, borderColor: col, background: `color-mix(in srgb, ${col} 12%, transparent)` }
  return <span className="pill" style={style}>{children}</span>
}

export function Glyph({ d, size = 18 }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor"
      strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{d}</svg>
  )
}

// icon path sets (JSX fragments)
export const I = {
  wallet: <><rect x="3" y="6" width="18" height="13" rx="2" /><path d="M16 12h3M3 9h13a2 2 0 0 1 2 2" /></>,
  chart: <><path d="M4 19V5M4 19h16M8 15l3-4 3 2 4-6" /></>,
  target: <><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="3" /></>,
  layers: <><path d="M12 3 3 8l9 5 9-5-9-5zM3 13l9 5 9-5M3 17l9 5 9-5" /></>,
  shield: <><path d="M12 3 5 6v5c0 4 3 7 7 9 4-2 7-5 7-9V6l-7-3z" /></>,
  pulse: <><path d="M3 12h4l2-6 4 12 2-6h6" /></>,
  bell: <><path d="M6 9a6 6 0 0 1 12 0c0 5 2 6 2 6H4s2-1 2-6M10 21h4" /></>,
  bolt: <><path d="M13 2 4 14h7l-1 8 9-12h-7l1-8z" /></>,
  grid: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
  cpu: <><rect x="6" y="6" width="12" height="12" rx="1" /><path d="M9 1v3M15 1v3M9 20v3M15 20v3M1 9h3M1 15h3M20 9h3M20 15h3" /></>,
  flask: <><path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-5-9V3" /></>,
  power: <><path d="M12 3v9M6 6a8 8 0 1 0 12 0" /></>,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  history: <><path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><path d="M3 4v4h4M12 8v4l3 2" /></>,
  settings: <><circle cx="12" cy="12" r="3" /><path d="M19 12a7 7 0 0 0-.1-1l2-1.5-2-3.4-2.3 1a7 7 0 0 0-1.7-1l-.3-2.5h-4l-.3 2.5a7 7 0 0 0-1.7 1l-2.3-1-2 3.4 2 1.5a7 7 0 0 0 0 2l-2 1.5 2 3.4 2.3-1a7 7 0 0 0 1.7 1l.3 2.5h4l.3-2.5a7 7 0 0 0 1.7-1l2.3 1 2-3.4-2-1.5a7 7 0 0 0 .1-1z" /></>,
  doc: <><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" /><path d="M14 3v6h6M9 13h6M9 17h6" /></>,
}

export default Panel

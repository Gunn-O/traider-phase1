// charts.jsx — lightweight SVG charts, theme-aware via CSS vars.
// Ported from the design bundle's charts.jsx (no recharts dependency).

const TONE = {
  cyan: 'var(--c-cyan)', magenta: 'var(--c-magenta)', gold: 'var(--c-gold)',
  green: 'var(--c-green)', red: 'var(--c-red)',
}
const tcol = (t) => TONE[t] || TONE.cyan

// ---- Equity / balance line chart -------------------------------------------
export function EquityCurve({ data, height = 220 }) {
  if (!data || data.length < 2) {
    return <div className="empty-state" style={{ padding: 32 }}>No equity data yet</div>
  }
  const W = 760, H = height, padL = 8, padR = 8, padT = 16, padB = 28
  const hasBalance = data.some((d) => d.balance != null)
  const vals = data.flatMap((d) => [d.balance ?? d.equity, d.equity])
  const min = Math.min(...vals), max = Math.max(...vals)
  const range = max - min || 1
  const x = (i) => padL + (i * (W - padL - padR)) / (data.length - 1)
  const y = (v) => padT + (1 - (v - min) / range) * (H - padT - padB)
  const path = (key) => data.map((d, i) => `${i === 0 ? 'M' : 'L'} ${x(i).toFixed(1)} ${y(d[key] ?? d.equity).toFixed(1)}`).join(' ')
  const area = `${path('equity')} L ${x(data.length - 1).toFixed(1)} ${H - padB} L ${x(0).toFixed(1)} ${H - padB} Z`
  const cyan = 'var(--c-cyan)'
  const grid = [0, 0.25, 0.5, 0.75, 1]
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ width: '100%', height }} className="chart-svg">
      <defs>
        <linearGradient id="eqfill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--c-cyan)" stopOpacity="0.28" />
          <stop offset="100%" stopColor="var(--c-cyan)" stopOpacity="0" />
        </linearGradient>
      </defs>
      {grid.map((g, i) => {
        const yy = padT + g * (H - padT - padB)
        return <line key={i} x1={padL} y1={yy} x2={W - padR} y2={yy} stroke="var(--line)" strokeWidth="1" strokeDasharray="2 5" />
      })}
      <path d={area} fill="url(#eqfill)" />
      {hasBalance && (
        <path d={path('balance')} fill="none" stroke="var(--muted)" strokeWidth="1.5" strokeDasharray="5 4" opacity="0.7" />
      )}
      <path d={path('equity')} fill="none" stroke={cyan} strokeWidth="2.5" style={{ filter: 'drop-shadow(0 0 6px var(--c-cyan-glow))' }} />
      {data.map((d, i) => (
        <circle key={i} cx={x(i)} cy={y(d.equity)} r={i === data.length - 1 ? 4 : 2.4}
          fill={i === data.length - 1 ? cyan : 'var(--panel-2)'} stroke={cyan} strokeWidth="1.5" />
      ))}
    </svg>
  )
}

// ---- Donut (single ring with center label) ---------------------------------
export function Donut({ value, max = 100, label, sub, size = 150, tone = 'cyan' }) {
  const r = size / 2 - 12, c = 2 * Math.PI * r, frac = Math.max(0, Math.min(1, value / max))
  const stroke = tcol(tone)
  return (
    <div style={{ position: 'relative', width: size, height: size }}>
      <svg viewBox={`0 0 ${size} ${size}`} style={{ width: size, height: size, transform: 'rotate(-90deg)' }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--line)" strokeWidth="10" />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={stroke} strokeWidth="10" strokeLinecap="round"
          strokeDasharray={`${(frac * c).toFixed(1)} ${c.toFixed(1)}`}
          style={{ filter: `drop-shadow(0 0 6px ${stroke})`, transition: 'stroke-dasharray .8s ease' }} />
      </svg>
      <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
        <div className="mono" style={{ fontSize: size * 0.26, fontWeight: 700, color: stroke, lineHeight: 1 }}>{label}</div>
        {sub && <div className="label-dim" style={{ fontSize: 10, marginTop: 4 }}>{sub}</div>}
      </div>
    </div>
  )
}

// ---- Mini bar histogram ----------------------------------------------------
export function BarHisto({ data, height = 130 }) {
  if (!data || !data.length) return <div className="empty-state" style={{ padding: 24 }}>No data</div>
  const max = Math.max(...data, 1)
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 4, height, padding: '0 2px' }}>
      {data.map((v, i) => (
        <div key={i} style={{ flex: 1, height: `${(v / max) * 100}%`, minHeight: 3, position: 'relative' }}
          className="histo-bar" title={`${v} signals`}>
          <div style={{
            position: 'absolute', inset: 0,
            background: 'linear-gradient(180deg, var(--c-cyan), transparent)',
            borderRadius: '2px 2px 0 0',
            opacity: i === data.length - 1 ? 1 : 0.55,
            boxShadow: i === data.length - 1 ? '0 0 8px var(--c-cyan-glow)' : 'none',
          }} />
        </div>
      ))}
    </div>
  )
}

// ---- Horizontal meter bar --------------------------------------------------
export function Meter({ value, max = 100, tone = 'cyan', showVal = true, unit = '%' }) {
  const frac = Math.max(0, Math.min(1, value / max))
  const col = tcol(tone)
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <div className="meter-track">
        <div className="meter-fill" style={{ width: `${frac * 100}%`, background: col, boxShadow: `0 0 8px ${col}` }} />
      </div>
      {showVal && (
        <div className="mono" style={{ minWidth: 48, textAlign: 'right', fontSize: 12, color: col }}>
          {typeof value === 'number' ? value.toFixed(1) : value}{unit}
        </div>
      )}
    </div>
  )
}

// ---- Sparkline -------------------------------------------------------------
export function Sparkline({ data, tone = 'cyan', width = 120, height = 36 }) {
  if (!data || data.length < 2) return null
  const min = Math.min(...data), max = Math.max(...data), range = max - min || 1
  const x = (i) => (i * width) / (data.length - 1)
  const y = (v) => height - 3 - ((v - min) / range) * (height - 6)
  const d = data.map((v, i) => `${i === 0 ? 'M' : 'L'} ${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(' ')
  const col = tcol(tone)
  return (
    <svg viewBox={`0 0 ${width} ${height}`} style={{ width, height }}>
      <path d={d} fill="none" stroke={col} strokeWidth="1.8" style={{ filter: `drop-shadow(0 0 3px ${col})` }} />
    </svg>
  )
}

// Reusable metric card — dark theme, matches TradeHistory color tokens.
// Created for the Execution Quality page (no MetricCard existed before).

const C = {
  card:   '#12121a',
  border: '#2a2a3a',
  text:   '#e0e0e0',
  muted:  '#888888',
  gray:   '#555566',
}

export default function MetricCard({ label, value, sub, color, badge, badgeColor }) {
  return (
    <div style={{
      background: C.card, border: `1px solid ${C.border}`,
      borderRadius: 12, padding: 16, minHeight: 96,
      display: 'flex', flexDirection: 'column',
    }}>
      <div style={{
        fontSize: 11, color: C.muted, letterSpacing: 1.5,
        textTransform: 'uppercase', marginBottom: 10,
      }}>
        {label}
      </div>
      <div style={{
        fontSize: 22, fontWeight: 700, color: color || C.text,
        fontFamily: 'monospace', lineHeight: 1.1,
      }}>
        {value}
      </div>
      {sub && <div style={{ fontSize: 11, color: C.muted, marginTop: 4 }}>{sub}</div>}
      {badge && (
        <div style={{
          marginTop: 'auto', paddingTop: 8,
        }}>
          <span style={{
            display: 'inline-block', padding: '2px 8px', borderRadius: 4,
            fontSize: 10, fontWeight: 600,
            background: 'rgba(136,136,136,0.15)',
            color: badgeColor || C.gray,
          }}>
            {badge}
          </span>
        </div>
      )}
    </div>
  )
}

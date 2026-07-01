import { useEffect, useMemo, useRef, useState, Component } from 'react'
import * as THREE from 'three'
import { Canvas } from '@react-three/fiber'
import { OrbitControls, Grid, Line, Text, Billboard } from '@react-three/drei'

// MarketModel3D — quant 3D "market evolution":
//  • volume/price SURFACE (theme heatmap navy→cyan→violet→magenta) — X=time,
//    Z=price, height/color = traded volume at that price (high-vol = magenta);
//  • TIME / PRICE / VOLUME axes with real-value labels so it reads as a chart;
//  • faint price path + bold ML TREND (EMA) line floating above → top view = chart;
//  • highlighted POC (max-volume price level) ridge + label.
// Fed by real /api/candles. Lazy-loaded so three.js stays out of the main bundle.

const BARS = 72
const NPRICE = 56
const W = 20, D = 13, H = 5
const EMA_SPAN = 9

const clamp01 = (x) => (x < 0 ? 0 : x > 1 ? 1 : x)

// Thermal heatmap (theme-tinted): COLD deep-navy/blue → cyan → gold → orange →
// HOT red. Low-traded prices read cold; the value area / POC reads hot — so the
// "where price lives" zones pop warm and the wings stay cool.
const STOPS = [
  [0.0, [0.04, 0.08, 0.20]],   // deep navy (cold)
  [0.22, [0.10, 0.42, 0.78]],  // blue
  [0.42, [0.13, 0.85, 0.93]],  // cyan
  [0.60, [0.96, 0.77, 0.32]],  // gold (warm)
  [0.80, [1.00, 0.48, 0.18]],  // orange (hot)
  [1.0, [1.00, 0.17, 0.40]],   // red (hottest)
]
function heat(t) {
  t = clamp01(t)
  for (let i = 1; i < STOPS.length; i++) {
    if (t <= STOPS[i][0]) {
      const [t0, c0] = STOPS[i - 1], [t1, c1] = STOPS[i]
      const f = (t - t0) / ((t1 - t0) || 1)
      return [c0[0] + (c1[0] - c0[0]) * f, c0[1] + (c1[1] - c0[1]) * f, c0[2] + (c1[2] - c0[2]) * f]
    }
  }
  return STOPS[STOPS.length - 1][1]
}

function smooth(grid, nx, nz) {
  const out = Array.from({ length: nx }, () => new Float32Array(nz))
  for (let i = 0; i < nx; i++) for (let j = 0; j < nz; j++) {
    let s = 0, n = 0
    for (let di = -1; di <= 1; di++) for (let dj = -1; dj <= 1; dj++) {
      const a = i + di, b = j + dj
      if (a >= 0 && a < nx && b >= 0 && b < nz) { s += grid[a][b]; n++ }
    }
    out[i][j] = s / n
  }
  return out
}

function ema(values, span) {
  const k = 2 / (span + 1)
  const out = []
  let prev = values[0]
  for (const v of values) { prev = v * k + prev * (1 - k); out.push(prev) }
  return out
}

function fmtT(ts) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function buildSurface(candles) {
  if (!candles || candles.length < 4) return null
  const nTime = candles.length
  let pmin = Infinity, pmax = -Infinity
  for (const c of candles) { pmin = Math.min(pmin, c.low); pmax = Math.max(pmax, c.high) }
  const prange = pmax - pmin || 1

  // Per-candle volume spread over its price range (presence/where price was),
  // plus colTotals = total volume traded AT each price level (the volume profile).
  const cell = Array.from({ length: nTime }, () => new Float32Array(NPRICE))
  const colTotals = new Float32Array(NPRICE)
  let maxCell = 0
  candles.forEach((c, ix) => {
    const vol = c.volume ?? c.tick_volume ?? Math.max(c.high - c.low, 0.01)
    const lo = Math.floor(((c.low - pmin) / prange) * (NPRICE - 1))
    const hi = Math.floor(((c.high - pmin) / prange) * (NPRICE - 1))
    const a = Math.max(0, Math.min(lo, hi)), b = Math.min(NPRICE - 1, Math.max(lo, hi))
    const span = b - a + 1
    for (let j = a; j <= b; j++) { cell[ix][j] += vol / span; colTotals[j] += vol / span }
  })
  for (let i = 0; i < nTime; i++) for (let j = 0; j < NPRICE; j++) maxCell = Math.max(maxCell, cell[i][j])
  maxCell = maxCell || 1
  let colMax = 0
  for (let j = 0; j < NPRICE; j++) colMax = Math.max(colMax, colTotals[j])
  colMax = colMax || 1

  // Heat field driven mainly by PRICE-LEVEL volume (78%) so consolidation /
  // value zones glow red across their band, while fast trend pass-throughs
  // (low volume-at-level) stay cold blue — "based on price, not the chart path".
  // Only cells the market actually traded are lit; untouched prices stay flat.
  const field = Array.from({ length: nTime }, () => new Float32Array(NPRICE))
  for (let i = 0; i < nTime; i++) for (let j = 0; j < NPRICE; j++) {
    if (cell[i][j] > 0) field[i][j] = 0.78 * (colTotals[j] / colMax) + 0.22 * (cell[i][j] / maxCell)
  }

  const sm = smooth(field, nTime, NPRICE)
  let max = 0
  for (let i = 0; i < nTime; i++) for (let j = 0; j < NPRICE; j++) max = Math.max(max, sm[i][j])
  max = max || 1

  // POC = price bin with most volume. Value Area = ~70% of volume expanded
  // outward from the POC → VAH (upper) / VAL (lower) act as support/resistance.
  let pocBin = 0
  for (let j = 1; j < NPRICE; j++) if (colTotals[j] > colTotals[pocBin]) pocBin = j
  const totalVol = colTotals.reduce((s, v) => s + v, 0) || 1
  const target = totalVol * 0.70
  let lo = pocBin, hi = pocBin, acc = colTotals[pocBin]
  while (acc < target && (lo > 0 || hi < NPRICE - 1)) {
    const left = lo > 0 ? colTotals[lo - 1] : -1
    const right = hi < NPRICE - 1 ? colTotals[hi + 1] : -1
    if (right >= left) { hi++; acc += colTotals[hi] } else { lo--; acc += colTotals[lo] }
  }
  const binPrice = (bin) => pmin + (bin / (NPRICE - 1)) * prange
  const pocPrice = binPrice(pocBin)
  const vahPrice = binPrice(hi)
  const valPrice = binPrice(lo)

  const xT = (i) => (i / (nTime - 1) - 0.5) * W
  const zP = (p) => (clamp01((p - pmin) / prange) - 0.5) * D
  const yLine = H * 1.2

  const closes = candles.map((c) => c.close)
  const trend = ema(closes, EMA_SPAN)
  const pricePts = closes.map((c, i) => [xT(i), yLine - 0.4, zP(c)])
  const trendPts = trend.map((v, i) => [xT(i), yLine, zP(v)])

  // Horizontal S/R levels span the full time axis at a constant price.
  const levelPts = (p, y) => [[-W / 2, y, zP(p)], [W / 2, y, zP(p)]]

  return {
    grid: sm, nTime, nPrice: NPRICE, max, pmin, pmax,
    pocPrice, vahPrice, valPrice,
    pocZ: zP(pocPrice), vahZ: zP(vahPrice), valZ: zP(valPrice),
    pricePts, trendPts, yLine,
    pocLine: levelPts(pocPrice, H * 1.12),
    vahLine: levelPts(vahPrice, H * 1.12),
    valLine: levelPts(valPrice, H * 1.12),
    times: candles.map((c) => c.time),
  }
}

function Surface({ surf }) {
  const geom = useMemo(() => {
    const { grid, nTime, nPrice, max } = surf
    const g = new THREE.PlaneGeometry(W, D, nTime - 1, nPrice - 1)
    g.rotateX(-Math.PI / 2)
    const pos = g.attributes.position
    const colors = new Float32Array(pos.count * 3)
    for (let iz = 0; iz < nPrice; iz++) for (let ix = 0; ix < nTime; ix++) {
      const vi = iz * nTime + ix
      const h = grid[ix][iz] / max
      pos.setY(vi, h * H)
      const [r, gg, b] = heat(h)
      colors[vi * 3] = r; colors[vi * 3 + 1] = gg; colors[vi * 3 + 2] = b
    }
    g.setAttribute('color', new THREE.BufferAttribute(colors, 3))
    g.computeVertexNormals()
    return g
  }, [surf])

  useEffect(() => () => geom.dispose(), [geom])

  return (
    <group position={[0, -1, 0]}>
      <mesh geometry={geom}>
        <meshStandardMaterial vertexColors metalness={0.3} roughness={0.5} side={THREE.DoubleSide} />
      </mesh>
      <mesh geometry={geom}>
        <meshBasicMaterial wireframe color="#13314e" transparent opacity={0.18} />
      </mesh>
    </group>
  )
}

function Lbl({ position, children, color = '#6f819f', size = 0.46 }) {
  return (
    <Billboard position={position}>
      <Text fontSize={size} color={color} anchorX="center" anchorY="middle" outlineWidth={0.012} outlineColor="#05080f">
        {children}
      </Text>
    </Billboard>
  )
}

function Axes({ surf }) {
  const { pmin, pmax, max, times, nTime } = surf
  const x0 = -W / 2, x1 = W / 2, z0 = -D / 2, z1 = D / 2
  const ax = '#23415f'
  const volMax = max >= 1000 ? `${(max / 1000).toFixed(1)}k` : Math.round(max).toString()
  const mid = Math.floor(nTime / 2)
  return (
    <group position={[0, -1, 0]}>
      {/* axis lines */}
      <Line points={[[x0, 0, z0], [x1, 0, z0]]} color={ax} lineWidth={1.2} />
      <Line points={[[x0, 0, z0], [x0, 0, z1]]} color={ax} lineWidth={1.2} />
      <Line points={[[x0, 0, z0], [x0, H, z0]]} color={ax} lineWidth={1.2} />

      {/* TIME (X) */}
      <Lbl position={[x0, -0.55, z0 - 0.9]}>{fmtT(times?.[0])}</Lbl>
      <Lbl position={[0, -0.55, z0 - 0.9]}>{fmtT(times?.[mid])}</Lbl>
      <Lbl position={[x1, -0.55, z0 - 0.9]} color="#22d8ee">{fmtT(times?.[nTime - 1])}</Lbl>
      <Lbl position={[0, -1.5, z0 - 1.7]} color="#8a98b5" size={0.52}>TIME →</Lbl>

      {/* PRICE (Z) */}
      <Lbl position={[x0 - 1.3, 0, z0]}>{pmin.toFixed(2)}</Lbl>
      <Lbl position={[x0 - 1.3, 0, 0]}>{((pmin + pmax) / 2).toFixed(2)}</Lbl>
      <Lbl position={[x0 - 1.3, 0, z1]} color="#f5c451">{pmax.toFixed(2)}</Lbl>
      <Lbl position={[x0 - 2.7, 0, 0]} color="#8a98b5" size={0.52}>PRICE</Lbl>

      {/* VOLUME (Y) */}
      <Lbl position={[x0 - 1.1, 0.15, z0]}>0</Lbl>
      <Lbl position={[x0 - 1.1, H, z0]} color="#ff2e9a">{volMax}</Lbl>
      <Lbl position={[x0 - 2.2, H / 2, z0]} color="#8a98b5" size={0.52}>VOL</Lbl>
    </group>
  )
}

// A support/resistance level: a faint vertical "wall" at a price across all time
// + a bright top line + a price label. The Value Area (VAL..VAH) is the hot band.
function Level({ z, topLine, color, opacity = 0.12, label, labelColor, lw = 2 }) {
  return (
    <group>
      <mesh position={[0, H * 0.55, z]}>
        <planeGeometry args={[W, H * 1.1]} />
        <meshBasicMaterial color={color} transparent opacity={opacity} side={THREE.DoubleSide} depthWrite={false} />
      </mesh>
      <Line points={topLine} color={color} lineWidth={lw} />
      <Lbl position={[W / 2 + 1.7, H * 1.12, z]} color={labelColor || color} size={0.5}>{label}</Lbl>
    </group>
  )
}

function Overlays({ surf }) {
  const { pricePts, trendPts, yLine, pocLine, vahLine, valLine, pocZ, vahZ, valZ, pocPrice, vahPrice, valPrice } = surf
  return (
    <group position={[0, -1, 0]}>
      {/* Value-area S/R levels — VAH/VAL bound the hot zone, POC is the center */}
      <Level z={vahZ} topLine={vahLine} color="#22d8ee" opacity={0.07} label={`VAH ${vahPrice.toFixed(2)}`} lw={1.6} />
      <Level z={valZ} topLine={valLine} color="#22d8ee" opacity={0.07} label={`VAL ${valPrice.toFixed(2)}`} lw={1.6} />
      <Level z={pocZ} topLine={pocLine} color="#ffd24a" opacity={0.18} label={`POC ${pocPrice.toFixed(2)}`} labelColor="#ffd24a" lw={3} />

      {/* price path + ML trend (reads as a chart from the top) */}
      <Line points={pricePts} color="#cfe8ff" lineWidth={1} transparent opacity={0.32} />
      <Line points={trendPts} color="#34e5a3" lineWidth={3} />
      <Lbl position={[-W / 2 - 1.7, yLine, trendPts[0]?.[2] ?? 0]} color="#34e5a3" size={0.5}>TREND</Lbl>
    </group>
  )
}

function Scene({ surf, view }) {
  const ctrl = useRef()
  useEffect(() => {
    const c = ctrl.current
    if (!c) return
    const cam = c.object
    // View presets — no auto-spin; user can still drag to rotate freely.
    const pos = view === 'top' ? [0, 27, 0.001]      // bird's-eye → reads as a chart
      : view === 'side' ? [29, 4, 0]                 // along time axis → volume profile by price
        : [0, 7, 18]                                 // iso / 3D (default)
    cam.position.set(...pos)
    c.target.set(0, 1, 0); c.update()
  }, [view])

  return (
    <group>
      <ambientLight intensity={0.6} />
      <pointLight position={[10, 14, 8]} intensity={1.1} color="#cfefff" />
      <pointLight position={[-10, 8, -8]} intensity={0.8} color="#ff2e9a" />
      <Grid
        position={[0, -1.05, 0]} args={[W * 1.3, D * 1.4]}
        cellColor="#0e2034" sectionColor="#1c3a55"
        cellSize={1.5} sectionSize={6} fadeDistance={44} fadeStrength={2} infiniteGrid={false}
      />
      <Surface surf={surf} />
      <Axes surf={surf} />
      <Overlays surf={surf} />
      <OrbitControls
        ref={ctrl} enablePan={false}
        minDistance={11} maxDistance={42} minPolarAngle={0.02} maxPolarAngle={1.54}
        target={[0, 1, 0]}
      />
    </group>
  )
}

class GLBoundary extends Component {
  constructor(p) { super(p); this.state = { failed: false } }
  static getDerivedStateFromError() { return { failed: true } }
  render() {
    if (this.state.failed) return <div className="market3d-fallback">3D view unavailable (WebGL off) — use the candlestick chart below.</div>
    return this.props.children
  }
}

export default function MarketModel3D({ bots = [] }) {
  const running = bots.filter((b) => b.status === 'running')
  const tf = running[0]?.tf && ['M1', 'M5', 'M15', 'M30'].includes(running[0].tf) ? running[0].tf : 'M5'
  const symbol = running[0]?.symbol || 'XAUUSDc'

  const [candles, setCandles] = useState([])
  const [err, setErr] = useState(null)
  const [view, setView] = useState('iso')

  useEffect(() => {
    let alive = true
    const poll = async () => {
      try {
        const r = await fetch(`/api/candles?tf=${tf}&limit=${BARS}&symbol=${symbol}`)
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        const j = await r.json()
        if (alive) { setCandles(Array.isArray(j) ? j : []); setErr(null) }
      } catch (e) { if (alive) setErr(e.message) }
    }
    poll()
    const t = setInterval(poll, tf === 'M1' ? 30000 : 60000)
    return () => { alive = false; clearInterval(t) }
  }, [tf, symbol])

  const surf = useMemo(() => buildSurface(candles), [candles])
  const last = candles.length ? candles[candles.length - 1].close : null

  return (
    <div className="market3d-wrap">
      <div className="market3d-hud">
        <span className="m3-tag">▤ LIQUIDITY TERRAIN · {symbol} {tf} · {candles.length} bars{last != null ? ` · ${last.toFixed(2)}` : ''}{surf ? ` · POC ${surf.pocPrice.toFixed(2)}` : ''}</span>
        <span className="m3-legend">
          <span style={{ color: '#34e5a3' }}>━ ML trend</span>
          <span style={{ color: '#ffd24a' }}>━ POC</span>
          <span style={{ color: '#22d8ee' }}>━ VA</span>
          <span><span style={{ color: '#1e6fd0' }}>cold</span>→<span style={{ color: '#ff2e44' }}>hot</span></span>
        </span>
      </div>
      <div className="market3d-controls">
        <button className={`filter-pill ${view === 'iso' ? 'active' : ''}`} onClick={() => setView('iso')}>3D</button>
        <button className={`filter-pill ${view === 'top' ? 'active' : ''}`} onClick={() => setView('top')}>Top · chart</button>
        <button className={`filter-pill ${view === 'side' ? 'active' : ''}`} onClick={() => setView('side')}>Side · profile</button>
      </div>
      {err && !surf && <div className="market3d-fallback">⚠ {err} — waiting for MT5 candles…</div>}
      {!err && !surf && <div className="market3d-fallback">Loading market data…</div>}
      {surf && (
        <GLBoundary>
          <Canvas camera={{ position: [0, 7, 18], fov: 45 }} dpr={[1, 1.8]}>
            <color attach="background" args={['#05080f']} />
            <fog attach="fog" args={['#05080f', 30, 52]} />
            <Scene surf={surf} view={view} />
          </Canvas>
        </GLBoundary>
      )}
    </div>
  )
}

// agents.js — Virtual Office roster: maps One Piece chibi characters to the
// REAL Tra(i)der agents (per CLAUDE.md, the per-trade pipeline is Python-only —
// Claude Reviewer / per-trade Risk-Manager AI are disabled; Weekly/Monthly are
// the only off-cycle AI agents).
//
// IMPORTANT image swap: the source PNGs are mislabeled — `reflector.png` is
// actually Sanji and `monthly.png` is actually Usopp. So the Reflector agent
// uses monthly.png and the Monthly agent uses reflector.png to line image up
// with character (carried over from the design bundle's data.jsx).
//
// `live` describes where useAgents pulls real status from:
//   pipeline  — derives from running bots + heartbeat + signal events
//   offcycle  — derives from /api/agent-logs (Weekly/Monthly)
//   infra     — derives from /api/mt5-status (Maintenance)
//   disabled  — not wired in the current architecture → always STANDBY

export const OFFICE_AGENTS = [
  {
    id: 'supervisor', img: '/agents/supervisor.png',
    char: 'Chopper', name: 'Supervisor', nameTh: 'ผู้ควบคุมระบบ', tone: 'magenta',
    role: 'Orchestrator · สั่งการเอเจนต์ทั้งหมด', live: 'pipeline', defaultStatus: 'active',
    desc: 'ศูนย์กลางตัดสินใจ ประสานงานเอเจนต์ทุกตัว ตามรอบ candle ของบอทที่กำลังรัน',
    metrics: [
      { k: 'Bots', kth: 'บอท', v: '0', u: 'run' },
      { k: 'Cycles', kth: 'รอบ', v: '0', u: '' },
      { k: 'Mode', kth: 'โหมด', v: '—', u: '' },
    ],
    log: 'STANDBY · ยังไม่มีบอททำงาน',
  },
  {
    id: 'analyst', img: '/agents/analyst.png',
    char: 'Luffy', name: 'Signal Engine', nameTh: 'เครื่องมือสร้างสัญญาณ', tone: 'cyan',
    role: 'Mountain · MaiRuay · Scanner', live: 'pipeline', defaultStatus: 'active',
    desc: 'สแกนหาแพทเทิร์น Mountain / MaiRuay / Uptrend-Downtrend บนกราฟทองตาม TF ที่รัน แล้วเลือกสัญญาณที่ดีที่สุดด้วย R:R',
    metrics: [
      { k: 'Pattern', kth: 'แพทเทิร์น', v: '—', u: '' },
      { k: 'Signals', kth: 'สัญญาณ', v: '0', u: '' },
      { k: 'R:R', kth: 'อาร์อาร์', v: '—', u: '' },
    ],
    log: 'STANDBY · รอ candle ปิด',
  },
  {
    id: 'risk_manager', img: '/agents/risk_manager.png',
    char: 'Zoro', name: 'Risk Gate (G3)', nameTh: 'ประตูควบคุมความเสี่ยง', tone: 'gold',
    role: 'Python guardian · circuit breaker', live: 'pipeline', defaultStatus: 'active',
    desc: 'กฎ Python ล้วน — คุมความเสี่ยงต่อแผน 10% ตัดวงจรเมื่อแพ้ติดกัน 3 ครั้ง หรือ DD เกิน 30/50%',
    metrics: [
      { k: 'Risk', kth: 'เสี่ยง', v: '10', u: '%' },
      { k: 'Consec L', kth: 'แพ้ติด', v: '0', u: '/3' },
      { k: 'Breaker', kth: 'ตัดวงจร', v: 'OK', u: '' },
    ],
    log: 'ALLOW · Python rules · ไม่มี AI',
  },
  {
    id: 'news_agent', img: '/agents/news_agent.png',
    char: 'Robin', name: 'Reviewer (off)', nameTh: 'ผู้ตรวจสอบ (ปิดใช้งาน)', tone: 'magenta',
    role: 'Claude Reviewer · disabled', live: 'disabled', defaultStatus: 'idle',
    desc: 'Per-trade Claude Reviewer ถูกปิดในสถาปัตยกรรมปัจจุบัน (per-trade = Python ล้วน) — เก็บไว้เป็น slot อนาคต',
    metrics: [
      { k: 'Mode', kth: 'โหมด', v: 'OFF', u: '' },
      { k: 'Calls', kth: 'เรียก', v: '0', u: '' },
      { k: 'Cost', kth: 'ค่าใช้จ่าย', v: '$0', u: '' },
    ],
    log: 'DISABLED · ไม่เรียก AI ต่อ trade (ตาม CLAUDE.md)',
  },
  {
    id: 'notify', img: '/agents/notify.png',
    char: 'Brook', name: 'Notify · LINE', nameTh: 'ผู้แจ้งเตือน', tone: 'magenta',
    role: 'G4 · LINE broadcast', live: 'pipeline', defaultStatus: 'active',
    desc: 'ส่งการแจ้งเตือนคำสั่งซื้อขายและเหตุการณ์สำคัญเข้ากลุ่ม LINE (เปิดเฉพาะ SIM/LIVE)',
    metrics: [
      { k: 'Channel', kth: 'ช่อง', v: 'LINE', u: '' },
      { k: 'Sent', kth: 'ส่ง', v: '0', u: '' },
      { k: 'State', kth: 'สถานะ', v: '—', u: '' },
    ],
    log: 'STANDBY · LINE_NOTIFY ตามค่า .env',
  },
  {
    id: 'reflector', img: '/agents/monthly.png', // mislabeled source → Usopp
    char: 'Usopp', name: 'Reflector', nameTh: 'ผู้ทบทวน', tone: 'cyan',
    role: 'Post-trade review · off-cycle', live: 'disabled', defaultStatus: 'idle',
    desc: 'ทบทวนผลเทรดที่ปิดแล้วและสรุปบทเรียน — ทำงานนอกรอบ per-trade (off-cycle)',
    metrics: [
      { k: 'Reviewed', kth: 'ทบทวน', v: '0', u: '' },
      { k: 'Lessons', kth: 'บทเรียน', v: '0', u: '' },
      { k: 'Cadence', kth: 'รอบ', v: 'OFF', u: '' },
    ],
    log: 'STANDBY · off-cycle',
  },
  {
    id: 'monthly', img: '/agents/reflector.png', // mislabeled source → Sanji
    char: 'Sanji', name: 'Monthly Evolver', nameTh: 'รายงาน/วิวัฒน์รายเดือน', tone: 'gold',
    role: 'Monthly strategy proposal (AI)', live: 'offcycle', defaultStatus: 'idle',
    desc: 'เดือนละครั้ง: วิเคราะห์ผลและเสนอปรับกลยุทธ์ให้มนุษย์อนุมัติ (ใช้ Claude แบบ off-cycle)',
    metrics: [
      { k: 'Last run', kth: 'ล่าสุด', v: '—', u: '' },
      { k: 'Proposals', kth: 'ข้อเสนอ', v: '0', u: '' },
      { k: 'Cost', kth: 'ค่าใช้จ่าย', v: '$0', u: '' },
    ],
    log: 'STANDBY · รอรอบรายเดือน',
  },
  {
    id: 'weekly', img: '/agents/weekly.png',
    char: 'Nami', name: 'Weekly Strategist', nameTh: 'นักกลยุทธ์รายสัปดาห์', tone: 'cyan',
    role: 'Weekly digest + params (AI)', live: 'offcycle', defaultStatus: 'idle',
    desc: 'สัปดาห์ละครั้ง: สรุปผลและแนะนำพารามิเตอร์ (ไม่บังคับใช้) ด้วย Claude แบบ off-cycle',
    metrics: [
      { k: 'Last run', kth: 'ล่าสุด', v: '—', u: '' },
      { k: 'Suggest', kth: 'แนะนำ', v: '0', u: '' },
      { k: 'Cost', kth: 'ค่าใช้จ่าย', v: '$0', u: '' },
    ],
    log: 'STANDBY · รอรอบรายสัปดาห์',
  },
  {
    id: 'maintenance', img: '/agents/maintenance.png',
    char: 'Franky', name: 'Maintenance', nameTh: 'ฝ่ายดูแลระบบ', tone: 'cyan',
    role: 'MT5 link · data · infra health', live: 'infra', defaultStatus: 'active',
    desc: 'ดูแลการเชื่อมต่อ MT5 ความสดของข้อมูล และสุขภาพระบบ',
    metrics: [
      { k: 'MT5', kth: 'เชื่อมต่อ', v: '—', u: '' },
      { k: 'Equity', kth: 'ทุน', v: '—', u: '' },
      { k: 'Pos', kth: 'โพซิชัน', v: '0', u: '' },
    ],
    log: 'STANDBY · checking MT5…',
  },
]

// status meta (label + colour)
export const OSTATUS = {
  active: { label: 'ACTIVE', th: 'ทำงาน', col: 'var(--c-green)' },
  review: { label: 'REVIEWING', th: 'กำลังทบทวน', col: 'var(--c-magenta)' },
  idle: { label: 'STANDBY', th: 'เตรียมพร้อม', col: 'var(--muted)' },
}

export const OTONE = { cyan: 'var(--c-cyan)', magenta: 'var(--c-magenta)', gold: 'var(--c-gold)' }

// character standing positions (x%, y%) — loose clusters (design layout)
export const STATIONS = {
  risk_manager: { x: 35, y: 64 }, news_agent: { x: 56, y: 67 }, maintenance: { x: 80, y: 65 },
  supervisor: { x: 15, y: 77 },
  notify: { x: 27, y: 89 }, reflector: { x: 46, y: 88 }, monthly: { x: 64, y: 90 }, weekly: { x: 79, y: 88 },
}

// themed background station per agent (placed to the SIDE so the character never hides it)
export const AGENT_PROPS = {
  supervisor: { type: 'command', dx: 0, dy: -9 }, risk_manager: { type: 'cctv', dx: -8, dy: -2 },
  news_agent: { type: 'news', dx: 9, dy: -2 }, maintenance: { type: 'robot', dx: 7, dy: 0 },
  notify: { type: 'stage', dx: 0, dy: -2 }, reflector: { type: 'holo', dx: -12, dy: 0 },
  monthly: { type: 'lectern', dx: 6, dy: 0 }, weekly: { type: 'board', dx: 8, dy: -2 },
}

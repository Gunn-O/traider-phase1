"""
Tra(i)der Phase I Configuration
Risk Management & System Constants

Reference: TRAIDER_MASTER_PLAN_v2.1.md Section 2
"""

# ============================================================================
# RISK MANAGEMENT CONFIG
# ============================================================================

RISK_CONFIG = {
    # พอร์ต
    'min_balance': 300,          # USD ขั้นต่ำ
    'risk_per_plan_pct': 0.10,   # 10% ของพอร์ตต่อแผน

    # Multi-Plan Limits
    'max_concurrent_plans': 2,   # เปิดพร้อมกันได้สูงสุด 2 plans
    'max_total_risk_pct': 0.20,  # risk รวมทุก plan ไม่เกิน 20%

    # Loss Limits
    'max_consecutive_loss': 3,   # หยุดเมื่อแพ้ติดกัน 3 ไม้
    'max_loss_30pct': 0.30,      # หยุดเมื่อขาดทุนสะสม > 30%
    'max_loss_50pct': 0.50,      # หยุดเมื่อขาดทุนรวม > 50%

    # Trailing SL
    'trailing_sl_min_tp': 3000,  # pip — เริ่ม trailing เมื่อ TP > 3000 pip
    'trailing_sl_trigger': 2000, # pip — เลื่อน SL เมื่อราคาไป 2000 pip
    'trailing_sl_target': 500,   # pip — ตั้ง SL ที่ +500 pip
    'trailing_sl_step': 1000,    # pip — เลื่อนทุก 1000 pip

    # R:R
    'min_rr_ratio': 1.0,

    # Winrate Test
    'winrate_test_lot': 0.01
}


# ============================================================================
# LOT CALCULATION
# ============================================================================

def calc_lot(balance: float, sl_pip: int, winrate_test: bool = False) -> dict:
    """
    สูตรใหม่จาก Strategy Part 4.4:
    Lot ทั้งหมด = เสียได้ (USD) / SL (pip)
    เสียได้ = balance × 10%

    ตัวอย่าง:
    balance=300, sl=900pip → lot = 30/900 = 0.033 → ปัดลง 0.03

    Args:
        balance: Account balance (USD)
        sl_pip: Stop Loss (pip) — 1 pip = 0.01 USD
        winrate_test: ถ้า True ใช้ 0.01 lot เสมอ

    Returns:
        {
            'lot_total': float,         # Lot ทั้งหมดของแผน
            'lot_per_order': float,     # Lot ต่อ order
            'suggested_orders': int,    # แนะนำจำนวน order (1-3)
            'max_loss_usd': float       # ยอดขาดทุนสูงสุด (USD)
        }
    """
    if winrate_test:
        return {
            'lot_total': 0.01,
            'lot_per_order': 0.01,
            'suggested_orders': 1,
            'max_loss_usd': sl_pip * 0.01
        }

    max_loss = balance * RISK_CONFIG['risk_per_plan_pct']
    lot_total = max_loss / sl_pip
    lot_total = round(lot_total, 2)
    lot_total = max(0.01, min(lot_total, 10.0))  # min 0.01, max 10.0

    # แนะนำจำนวน order (แบ่งได้ 1-3)
    if lot_total >= 0.03:
        suggested_orders = 3
    elif lot_total >= 0.02:
        suggested_orders = 2
    else:
        suggested_orders = 1

    lot_per_order = round(lot_total / suggested_orders, 2)

    return {
        'lot_total': lot_total,
        'lot_per_order': lot_per_order,
        'suggested_orders': suggested_orders,
        'max_loss_usd': round(max_loss, 2)
    }


# ============================================================================
# TIMEFRAME CONFIG
# ============================================================================

# Single TF mode: ง่าย, เร็ว, reliable กว่า MTF
# M1: signal เยอะ (20-50/day) เหมาะสำหรับ testing
# M5: balanced quality (5-15/day) เหมาะสำหรับ production
TIMEFRAMES = ['M5']  # Balanced: quality + frequency

TF_SIZE = {
    'H4': 6,
    'H1': 5,
    'M30': 4,
    'M15': 3,
    'M5': 2,
    'M1': 1
}


# ============================================================================
# CHART TYPES & TECHNIQUES
# ============================================================================

CHART_TYPES = [
    'uptrend',
    'downtrend',
    'sideway_down',
    'sideway_up',
    'mountain',
    'unclear'
]

TECHNIQUES = [
    'twin_candle',      # แท่งคู่
    'breakout_follow',  # ตามเจ้า
    'mai_ruay',         # ไม้รวย (แท่งพ่อ+แม่)
    'support_bounce'    # แนวเด้ง (ไม่ใช้ใน v2.1 — มีแต่ใน twin_candle)
]


# ============================================================================
# CANDLE & PATTERN DETECTION CONSTANTS
# ============================================================================

CANDLES_LOOKBACK = 55       # จำนวนแท่งที่ใช้วิเคราะห์
SCREEN_X = 5.7              # หน่วยแกน X (สัดส่วนหน้าจอ)
SCREEN_Y = 7.4              # หน่วยแกน Y (สัดส่วนหน้าจอ)
TARGET_SLOPE_DEG = 47.5     # ความชันอ้างอิง Uptrend/Downtrend (45-50°)
MIN_TWIN_CANDLE_BODY = 0.05  # แท่งคู่: เนื้อเทียนต้องหนา ≥ 5% Range (Strategy v2.1)
MAX_TWIN_CANDLE_GAP = 10     # แท่งคู่: Open/Close ห่างกันได้ไม่เกิน 10 pip (0.10 USD)


# ============================================================================
# ANTI-OVERTRADE RULES
# ============================================================================

# Guardian Block Rules (ไม่ใช้ Cooldown timer)
# 1. มีแผนที่ยังไม่สิ้นสุด (open plan exists) → BLOCK ทันที
# 2. Consecutive loss ≥ 3 → BLOCK + แจ้ง LINE
# 3. Total loss > 30% balance → BLOCK + แจ้ง LINE
# 4. Total loss > 50% balance → BLOCK ถาวร + แจ้ง LINE
# 5. R:R < 1.0 → BLOCK
# 6. news_flag = true → BLOCK ±30 นาที

NEWS_BLOCK_MINUTES = 30  # Block ±30 นาที รอบข่าว


# ============================================================================
# GOOGLE SHEETS SCHEMA
# ============================================================================

# Trade Log Columns (Sheet 1)
TRADE_LOG_COLUMNS = [
    'trade_id',           # A: TRD-YYYYMMDD-NNN
    'plan_id',            # B: PLAN-YYYYMMDD-NNN
    'order_num',          # C: 1,2,3
    'timestamp_open',     # D: เวลาเปิด
    'timeframe',          # E: H4/H1/M30/M15/M5/M1
    'chart_type',         # F: uptrend/downtrend/sideway_down/sideway_up/mountain/unclear
    'technique',          # G: twin_candle/breakout_follow/mai_ruay/support_bounce
    'action',             # H: BUY/SELL
    'entry_price',        # I: ราคา entry
    'sl_price',           # J: Stop Loss
    'tp_price',           # K: Take Profit (เดียว)
    'lot_size',           # L: lot ของ order นี้
    'lot_total_plan',     # M: lot ทั้งหมดของแผน (เท่ากับ lot_size)
    'rr_ratio',           # N: R:R จริง
    'confidence',         # O: 0.0-1.0
    'rsi_14',             # P: metadata
    'session',            # Q: Asia/London/NY
    'ai_reason',          # R: เหตุผลจาก Claude
    'llm_tokens',         # S: tokens ที่ใช้
    'llm_cost_usd',       # T: ต้นทุน API
    'result',             # U: WIN/LOSS/PENDING
    'pnl_usd',            # V: P&L USD
    'close_reason',       # W: TP_HIT/SL_HIT/MANUAL
    'close_price',        # X: ราคาปิด
    'timestamp_close',    # Y: เวลาปิด
    'trailing_sl',        # Z: SL ที่เลื่อนแล้ว (ถ้ามี)
    'human_action',       # AA: BUY/SELL/SKIP (human)
    'human_agree'         # AB: TRUE/FALSE
]

# Portfolio State Fields (Sheet 2)
PORTFOLIO_STATE_FIELDS = [
    'active_plan_id',        # แผนที่กำลังเปิดอยู่ (comma-separated: PLAN-001,PLAN-002)
    'open_plans_count',      # จำนวน plans ที่เปิดอยู่
    'total_risk_pct',        # risk รวมทุก plan (% ของ balance)
    'open_orders_count',     # จำนวน order ที่เปิดอยู่
    'total_open_lot',        # รวม lot ที่เปิดอยู่
    'realized_pnl_usd',      # P&L ที่ปิดแล้ว (วันนี้)
    'unrealized_pnl_usd',    # P&L ที่ยังเปิดอยู่ (estimate)
    'consecutive_loss',      # SL ติดกันกี่ครั้ง
    'total_loss_pct',        # ขาดทุนรวม % ของ balance เริ่มต้น
    'trading_blocked',       # TRUE/FALSE
    'block_reason',          # เหตุผลที่ block
    'last_updated',          # เวลา update ล่าสุด
    'last_technical_price',  # Technical price ของ plan ล่าสุด (ป้องกัน duplicate)
    'last_plan_chart_type'   # Chart type ของ plan ล่าสุด
]

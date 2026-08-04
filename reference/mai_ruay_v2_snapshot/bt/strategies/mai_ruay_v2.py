# ============================================================================
# bt/strategies/mai_ruay_v2.py
# ----------------------------------------------------------------------------
# ไม้รวย v2 — "ฉบับสะอาด": เก็บเฉพาะแกนหลัก ตัดเงื่อนไขเสริมทั้งหมด
# สเปค: docs/MAIRUAY_V2_SPEC.md (source of truth) · id: mai_ruay_v2
#
# ใช้ contract / Signal / engine เดิม (ไฟล์นี้เป็นแค่ strategy layer ใหม่)
# *** ห้ามแตะ mai_ruay.py / engine / contract — V1 ต้องนิ่งเป๊ะ ***
#
# ตัดออกจาก V1 (ไม่พอร์ตมา): ไม้รวยรอบ 2 · เพิ่ม/หาร lot · TP/SL ย่อย · buffer · R:R adjust
#
# โครงตรรกะ (เหมือน V1 แต่ล้วน):
#   father_end = bar-2 · mother = bar-1 · child(เข้า) = bar
#   พ่อ = แท่งสีเดียวต่อเนื่องจบที่ father_end · แม่ = แท่งย่อสีตรงข้าม 1 แท่ง
#   tech_point = (พ่อปิด + แม่เปิด)/2 · TP/SL = fixed % ของขนาดพ่อ จาก tech_point
#   entries = list ของ tier → เลือก tier ตาม when{พ่อ%, แม่%} → เปิดไม้ตาม legs
# ============================================================================
from __future__ import annotations

import math
from dataclasses import dataclass

from bt.contract import Bar, Decision, Order
from bt.data import PIP
from bt.strategies.base import Strategy


@dataclass
class Signal:
    # เหลือเฉพาะ field ที่ V2 อ่านจริง (on_bar) — proximity/pending + plan_meta
    direction:        str           # 'BUY' | 'SELL'
    father_start:     int
    father_end:       int
    father_pct_r55:   float
    mother_idx:       int
    mother_pct_r55:   float
    range55:          float
    entries:          list          # list[(price, label, lot, is_market, sl, tp)]
    reasons:          list          # analytics ล้วน — เหตุผลไทยจาก branch ที่เดินจริง

# ค่าคงที่ภายใน (lot/risk + proximity ย้ายไป config: general.*)
_PROXIMITY_PCT_R55_DEFAULT = 10.0   # default ระยะ proximity-cancel (%R55) — fallback ถ้า config ไม่มี key
_MIN_LOT           = 0.01    # lot ขั้นต่ำ (ปัดต่อไม้: <0.01 → 0.01 · ≥0.01 → ปัดลงทีละ 0.01)


def _r(x, n):
    return round(float(x), n)


# ---------- lot sizing ต่อแผน (risk = lot × ระยะ SL · convention เดิม) ----------
def _round_lot(x: float) -> float:
    """ปัดต่อไม้: <0.01 → ปัดขึ้น 0.01 (min) · ≥0.01 → ปัดลงทีละ 0.01 (floor)"""
    if x < _MIN_LOT:
        return _MIN_LOT
    return math.floor(x * 100 + 1e-9) / 100


def _compute_lots(dists_pips, budget, split_mode):
    """คิด lot ต่อไม้จาก budget (= พอร์ต×risk%) · dists_pips = [ระยะ SL ต่อไม้ (pip), >0]
      - equal_risk (B): risk ต่อไม้ = budget/N → lot_i = (budget/N) / dist_i
      - equal_lot  (A): L = budget / Σdist → lot_i = L (เท่ากันทุกไม้)
    ปัดต่อไม้แล้วเช็ค total_risk = Σ(lot_i×dist_i); ถ้า > budget → ตัดไม้ "ตัวล่างสุด" (ท้าย legs) ออก
    คิดใหม่ วนจน ≤ budget หรือเหลือ 1 ไม้ · คืน list[lot] (ยาว = จำนวนไม้ที่เหลือ)"""
    n = len(dists_pips)
    while n >= 1:
        sub = dists_pips[:n]
        if split_mode == 'equal_lot':
            total = sum(sub)
            L = budget / total if total > 0 else _MIN_LOT
            raw = [L] * n
        else:   # equal_risk (default)
            per = budget / n
            raw = [(per / d if d > 0 else 0.0) for d in sub]
        lots = [_round_lot(x) for x in raw]
        total_risk = sum(l * d for l, d in zip(lots, sub))
        if total_risk <= budget or n == 1:
            return lots
        n -= 1   # เกิน budget → ตัดไม้ท้ายสุดออก 1 แล้วคิดใหม่
    return []


# ---------- R55 (window ปรับได้ตาม general.r55_bars — calc_r55 ใน data.py fix 55) ----------
def _calc_r55(bars, end_idx: int, n: int) -> float:
    start = max(0, end_idx - n + 1)
    window = bars[start:end_idx + 1]
    if not window:
        return 0.0
    hi = max(b.high for b in window)
    lo = min(b.low for b in window)
    return (hi - lo) / PIP


# ---------- bar helpers ----------
def _body_pips(b: Bar) -> float: return abs(b.open - b.close) / PIP
def _is_bull(b: Bar) -> bool:    return b.close > b.open
def _is_bear(b: Bar) -> bool:    return b.close < b.open


# ---------- แท่งพ่อ (นับแท่ง + ขนาด + vol) ----------
def _find_father(bars, father_end, r55, fc):
    """หาแท่งพ่อ = run สีเดียวต่อเนื่องจบที่ father_end · คืน (start, end, dir, body_pips) หรือ None"""
    n = len(bars)
    if father_end < 0 or father_end >= n:
        return None
    eb = bars[father_end]
    if   _is_bull(eb): run_dir = 'UP'
    elif _is_bear(eb): run_dir = 'DOWN'
    else: return None

    # ถัดจากพ่อต้องเป็นแท่งย่อสีตรงข้าม (= ตำแหน่งแม่)
    if father_end + 1 < n:
        nb = bars[father_end + 1]
        if (run_dir == 'UP' and not _is_bear(nb)) or \
           (run_dir == 'DOWN' and not _is_bull(nb)):
            return None

    doji    = fc['doji_stop_pct'] / 100
    per_bar = fc['per_bar_body_min'] / 100
    big     = fc['big_bar_pct'] / 100

    # นับย้อนหลังขณะสีเดียว + เนื้อ > doji · สูงสุด count_max แท่ง
    run_start = father_end
    for k in range(father_end - 1, max(-1, father_end - fc['count_max']), -1):
        b = bars[k]
        same = (run_dir == 'UP' and _is_bull(b)) or (run_dir == 'DOWN' and _is_bear(b))
        if same and _body_pips(b) > r55 * doji:
            run_start = k
        else:
            break

    # ตัดแท่งเล็ก (เนื้อ ≤ per_bar) ที่หัวขบวน ได้สูงสุด head_trim_small_max แท่ง
    trimmed = 0
    while run_start < father_end and trimmed < fc['head_trim_small_max'] \
            and _body_pips(bars[run_start]) <= r55 * per_bar:
        run_start += 1
        trimmed += 1

    length = father_end - run_start + 1
    if length < fc['count_min']:
        return None

    seg = bars[run_start:father_end + 1]
    tb  = abs(seg[0].open - seg[-1].close) / PIP
    pct = tb / r55 * 100 if r55 > 0 else 0
    if pct < fc['body_min_pct_r55']:               # ขนาดพ่อรวมขั้นต่ำ (%R55)
        return None
    bmax = fc.get('body_max_pct_r55', 0)           # ขนาดพ่อรวมสูงสุด (%R55) · .get+sentinel 0 → กัน config เก่าไม่มีคีย์ · 0=ไม่จำกัด
    if bmax and pct > bmax:
        return None

    # เนื้อต่อแท่ง: อนุโลมแท่งเล็กได้เมื่อ "แท่งใหญ่เป็นส่วนมาก" และไม่เป็น doji · ≤ small_bar_allow แท่ง
    big_count = sum(1 for b in seg if _body_pips(b) > r55 * big)
    big_majority = big_count > length / 2
    fail = 0
    for b in seg:
        bp = _body_pips(b)
        if bp <= r55 * per_bar:
            if big_majority and bp > r55 * doji:
                fail += 1
            else:
                return None
    if fail > fc['small_bar_allow']:
        return None

    # Vol ratio: เนื้อเฉลี่ยพ่อ ÷ เนื้อเฉลี่ย vol_window แท่งก่อนหน้า ต้อง ≥ vol_ratio_min
    avg_body = tb / length
    pre = bars[max(0, run_start - fc['vol_window']):run_start]
    vol_ratio = 0.0
    if pre:
        pre_avg = sum(_body_pips(b) for b in pre) / len(pre)
        vol_ratio = avg_body / pre_avg if pre_avg > 0 else 0.0
    if vol_ratio < fc['vol_ratio_min']:
        return None

    return (run_start, father_end, run_dir, tb, _r(vol_ratio, 2))


# ---------- แท่งแม่ (ย่อตัวสีตรงข้าม · เทียบ %R55 หรือ %พ่อ ตาม compare_mode) ----------
def _validate_mother(bars, mother_idx, f_dir, r55, f_body, mc):
    """คืน (m_body_pips, m_pct) หรือ None · m_pct เทียบตาม compare_mode (r55|father)"""
    if mother_idx >= len(bars):
        return None
    m = bars[mother_idx]
    if f_dir == 'UP'   and not _is_bear(m):
        return None
    if f_dir == 'DOWN' and not _is_bull(m):
        return None
    m_body = _body_pips(m)
    base = f_body if mc.get('compare_mode') == 'father' else r55
    pct = m_body / base * 100 if base > 0 else 0
    if pct < mc['body_min_pct'] or pct > mc['body_max_pct']:
        return None
    return (m_body, pct)


# ---------- validate รูปร่าง entries (กัน config เพี้ยน → error ชัดแทน AttributeError ดิบ) ----------
def _validate_entries(entries) -> None:
    """entries ต้องเป็น list ของ tier · แต่ละ tier = dict {when: dict, legs: [ {mode,...}... ]}
    leg = {mode: market} หรือ {mode: mother_pct, value: -100..100}
    config ที่ถูก Form-save ทับจะกลายเป็น list ของ string → จับได้ตรงนี้พร้อมบอกวิธีแก้"""
    if not isinstance(entries, list) or not entries:
        raise ValueError("config 'entries' ต้องเป็น list ของ tier ที่ไม่ว่าง "
                         "(โครงเพี้ยน? แก้ผ่าน Raw YAML — ดู docs/MAIRUAY_V2_SPEC.md)")
    for i, tier in enumerate(entries):
        if not isinstance(tier, dict) or 'when' not in tier or 'legs' not in tier:
            raise ValueError(f"config 'entries[{i}]' ต้องเป็น dict ที่มี key 'when' และ 'legs' "
                             f"(เจอ {type(tier).__name__}: {tier!r}) — โครง entries เพี้ยน แก้ผ่าน Raw YAML")
        if not isinstance(tier['when'], dict):
            raise ValueError(f"config 'entries[{i}].when' ต้องเป็น dict (เจอ {type(tier['when']).__name__})")
        legs = tier['legs']
        if not isinstance(legs, list) or not legs:
            raise ValueError(f"config 'entries[{i}].legs' ต้องเป็น list ของไม้ที่ไม่ว่าง")
        for j, leg in enumerate(legs):
            if not isinstance(leg, dict) or 'mode' not in leg:
                raise ValueError(f"config 'entries[{i}].legs[{j}]' ต้องเป็น dict ที่มี key 'mode' "
                                 f"(ใช้ได้: {{mode: market}} หรือ {{mode: mother_pct, value: N}})")
            mode = leg['mode']
            if mode not in ('market', 'mother_pct'):
                raise ValueError(f"config 'entries[{i}].legs[{j}]' mode ไม่รู้จัก: {mode!r} "
                                 f"(ใช้ได้: market | mother_pct)")
            if mode == 'mother_pct':
                v = leg.get('value')
                if isinstance(v, bool) or not isinstance(v, (int, float)):
                    raise ValueError(f"config 'entries[{i}].legs[{j}]' mode=mother_pct "
                                     f"ต้องมี 'value' เป็นตัวเลข (เจอ {v!r})")
                if not (-100 <= v <= 100):
                    raise ValueError(f"config 'entries[{i}].legs[{j}]' value ต้องอยู่ในช่วง -100..100 "
                                     f"(0=tech · +100=ปลายแม่ · −100=ได้เปรียบสุด · เจอ {v})")
            # per-leg TP/SL adjust (optional · ทุกไม้รวม market · หน่วย=%ของพ่อ เหมือน base · 0/ไม่ใส่=no-op)
            for k in ('tp_adj', 'sl_adj'):
                a = leg.get(k)
                if a is not None and (isinstance(a, bool) or not isinstance(a, (int, float))):
                    raise ValueError(f"config 'entries[{i}].legs[{j}]' {k} ต้องเป็นตัวเลข (เจอ {a!r})")
            ao = leg.get('adj_on')
            if ao is not None and not isinstance(ao, bool):
                raise ValueError(f"config 'entries[{i}].legs[{j}]' adj_on ต้องเป็น true/false (เจอ {ao!r})")


# ---------- เลือก tier จาก entries ตามเงื่อนไข when ----------
def _select_tier(entries, f_pct, m_pct):
    """tier แรกที่ match (พ่อ ≥ father_min_pct และ mother_min ≤ แม่ ≤ mother_max) — ลำดับใน list = ลำดับความสำคัญ"""
    for tier in entries:
        w = tier.get('when', {})
        if f_pct >= w.get('father_min_pct', 0) \
                and w.get('mother_min_pct', 0) <= m_pct <= w.get('mother_max_pct', 1e9):
            return tier
    return None


# ---------- core analyzer ----------
def analyze_bar(bars, bar_idx, cfg) -> Signal | None:
    g  = cfg['general']
    rw = g['r55_bars']
    if bar_idx < rw - 1:
        return None
    mother_idx = bar_idx - 1
    father_end = bar_idx - 2
    if father_end < 0:
        return None

    r55 = _calc_r55(bars, bar_idx - 1, rw)          # R55 ณ จบแท่งแม่
    if r55 <= 0:
        return None

    fr = _find_father(bars, father_end, r55, cfg['father'])
    if fr is None:
        return None
    f_start, f_end, f_dir, f_body, vol_ratio = fr
    f_pct = f_body / r55 * 100 if r55 > 0 else 0

    mc = cfg['mother']
    mr = _validate_mother(bars, mother_idx, f_dir, r55, f_body, mc)
    if mr is None:
        return None
    m_body, m_pct = mr

    tier = _select_tier(cfg['entries'], f_pct, m_pct)
    if tier is None:
        return None

    mai_dir      = 'BUY' if f_dir == 'DOWN' else 'SELL'
    father_close = bars[f_end].close
    m_row        = bars[mother_idx]
    mother_open  = m_row.open
    tech_point   = (father_close + mother_open) / 2
    mother_body_len = abs(mother_open - m_row.close)   # |open แม่ − close แม่| (ราคา)
    child        = bars[bar_idx]

    # TP/SL = fixed % ของขนาดพ่อ จาก tech_point (ยังไม่มีเงื่อนไข)
    tp_off = f_body * (cfg['tpsl']['tp_pct_father'] / 100) * PIP
    sl_off = f_body * (cfg['tpsl']['sl_pct_father'] / 100) * PIP
    sl     = tech_point - sl_off if mai_dir == 'BUY' else tech_point + sl_off
    tp_sel = tech_point + tp_off if mai_dir == 'BUY' else tech_point - tp_off

    tp_pips = abs(tp_sel - tech_point) / PIP   # analytic: ระยะ TP จาก tech (รายงานเท่านั้น — ไม่ใช่ตัวกรองแล้ว)

    # สร้างไม้ตาม legs ของ tier:
    #   mode=market     → MARKET ที่ open แท่งลูก (เข้าทันที)
    #   mode=mother_pct → LIMIT ที่ tech ± (mother_body_len × value/100) ตามทิศ BUY/SELL (mirror)
    #     value 0 = tech · +N = เข้าตัวแม่ N% (50=ครึ่งแม่, +100=ปลายแม่) · −N = เลย tech ออกไป N% (ได้เปรียบ)
    #     BUY: + = ขึ้น (เข้าหาแม่) / − = ลง · SELL: mirror (+ = ลง / − = ขึ้น)
    # min_tp_pip: เช็ค "ต่อไม้" — ระยะ TP จาก entry ของไม้นั้น ในทิศกำไร (มีเครื่องหมาย):
    #   BUY  dist = (tp_sel − entry)/PIP   ·   SELL dist = (entry − tp_sel)/PIP
    #   dist < min_tp_pip → ดรอปไม้นั้น (ครอบทั้ง TP ใกล้เกิน [บวกน้อย] + TP ผิดฝั่ง entry [ติดลบ])
    sign = 1 if mai_dir == 'BUY' else -1
    min_tp = g['min_tp_pip']
    tp_pct_b = cfg['tpsl']['tp_pct_father']   # base % ของพ่อ (ร่วม) → ฐานของ per-leg adjust
    sl_pct_b = cfg['tpsl']['sl_pct_father']
    entries = []
    for idx, leg in enumerate(tier['legs']):
        if leg['mode'] == 'market':
            ep, label, mkt = child.open, f"ไม้{idx + 1}:market", True
        else:   # mother_pct
            val = leg['value']
            ep, label, mkt = tech_point + sign * mother_body_len * (val / 100), f"ไม้{idx + 1}:แม่{val:g}%", False
        # per-leg TP/SL adjust (ทุกไม้รวม market — TP/SL = tech ± %พ่อ ไม่ขึ้นกับ entry mode) · adj_on≠False และ adj≠0/None → base+adj
        use = (leg.get('adj_on') is not False)
        tp_pct_i = tp_pct_b + (leg.get('tp_adj') or 0 if use else 0)
        sl_pct_i = sl_pct_b + (leg.get('sl_adj') or 0 if use else 0)
        if sl_pct_i <= 0:
            sl_pct_i = sl_pct_b   # clamp: SL ต้อง > 0 (กัน sl=tech → sl_pips 0) → ตกกลับ base
        if tp_pct_i == tp_pct_b and sl_pct_i == sl_pct_b:
            sl_i, tp_i = sl, tp_sel   # no-op → ใช้ค่า base เป๊ะ (regression-safe)
        else:
            tp_off_i = f_body * (tp_pct_i / 100) * PIP
            sl_off_i = f_body * (sl_pct_i / 100) * PIP
            sl_i = tech_point - sl_off_i if mai_dir == 'BUY' else tech_point + sl_off_i
            tp_i = tech_point + tp_off_i if mai_dir == 'BUY' else tech_point - tp_off_i
        tp_dist = ((tp_i - ep) if mai_dir == 'BUY' else (ep - tp_i)) / PIP   # per-leg TP
        if tp_dist < min_tp:
            continue   # ไม้นี้ TP ใกล้เกิน/ผิดฝั่ง entry → ไม่วาง
        entries.append((ep, label, mkt, sl_i, tp_i))

    if not entries:        # ทุกไม้ถูกดรอป → แผนนี้ไม่มี order = ทิ้งสัญญาณ
        return None

    # lot ต่อไม้: risk ต่อแผน = portfolio_start × risk_per_plan_pct/100 · แบ่งตาม lot_split_mode
    #   (config = source เดียวของ V2 · ระยะ SL ต่อไม้ต่างกัน — SL ร่วม, entry ต่างกัน)
    first_price = entries[0][0]
    sl_pips = abs(first_price - sl) / PIP
    if sl_pips <= 0:
        return None
    portfolio_start = g.get('portfolio_start', 1000)
    risk_pct = g.get('risk_per_plan_pct', 10)
    split_mode = g.get('lot_split_mode', 'equal_risk')
    budget = portfolio_start * (risk_pct / 100)
    dists_pips = [abs(ep - sl_i) / PIP for ep, _, _, sl_i, _ in entries]   # lot คิดจาก SL ต่อไม้ (per-leg) · no-op: sl_i=sl เดิม
    lots = _compute_lots(dists_pips, budget, split_mode)
    if not lots:
        return None
    kept = entries[:len(lots)]                       # ไม้ที่เหลือหลังตัดตัวล่างสุด (ถ้าเกิน budget)
    entries_full = [(ep, label, _r(lots[k], 2), mkt, sl_i, tp_i) for k, (ep, label, mkt, sl_i, tp_i) in enumerate(kept)]
    lot = _r(sum(lots), 2)                            # lot รวมของแผน (analytics)

    _cut = len(entries) - len(kept)
    _tpdrop = len(tier['legs']) - len(entries)   # ไม้ที่ถูกดรอปด้วย min_tp_pip (TP ใกล้/ผิดฝั่ง)
    reasons = [
        f"พ่อ {f_pct:.1f}%R55 ({f_end - f_start + 1} แท่ง) · vol {vol_ratio:.2f}",
        f"แม่ {m_pct:.1f}% (compare={mc.get('compare_mode')})",
        f"เข้า tier: พ่อ≥{tier['when'].get('father_min_pct')}%, "
        f"แม่ {tier['when'].get('mother_min_pct')}–{tier['when'].get('mother_max_pct')}% "
        f"→ {len(kept)} ไม้" + (f" (ตัดท้าย {_cut} ไม้ — เกิน budget)" if _cut else "")
        + (f" (ดรอป {_tpdrop} ไม้ — TP < min_tp_pip)" if _tpdrop else ""),
        f"TP/SL = {cfg['tpsl']['tp_pct_father']}% / {cfg['tpsl']['sl_pct_father']}% ของพ่อ",
        f"lot: {split_mode} · budget {budget:.0f} (พอร์ต {portfolio_start:.0f}×{risk_pct}%)",
    ]

    return Signal(
        direction=mai_dir,
        father_start=f_start, father_end=f_end, father_pct_r55=f_pct,
        mother_idx=mother_idx, mother_pct_r55=m_pct,
        range55=r55,
        entries=entries_full, reasons=reasons,
    )


class MaiRuayV2(Strategy):
    name = "mai_ruay_v2"

    def __init__(self, cfg: dict, portfolio: float = 1000.0,
                 pre_fill_cancel: bool = False):
        _validate_entries(cfg.get('entries'))   # fail fast ถ้าโครง entries เพี้ยน (error ชัด)
        self.cfg = cfg
        # portfolio (จาก global.yaml) รับไว้ตาม signature ร่วม แต่ V2 ใช้ config.general.portfolio_start
        # เป็น source เดียวสำหรับ lot (กัน 2 แหล่งขัดกัน) — ดู analyze_bar
        self.portfolio = portfolio
        self.pre_fill_cancel = pre_fill_cancel
        self._pend = {}        # tag -> {tp_sel, sl, r55, dir, placed, plan_id, price, place_time}
        # analytics ล้วน (ไม่กระทบ Decision/ผลเทรด)
        self._plan_id = 0          # mirror engine plan_id (++ เฉพาะ batch ที่ place ไม่ว่าง · เลขบวก = ตรง trades)
        self._cancel_plan_id = 0   # plan ที่ proximity ตัดครบ (place ว่าง · engine ไม่ออกเลข) → เลขลบ ไม่ชน engine
        self.unfilled = []
        self.plan_meta = {}

    def on_bar(self, ctx) -> Decision:
        cfg = self.cfg
        g = cfg['general']
        place, cancel, modify = [], [], []
        i, bar = ctx.bar_index, ctx.bar
        expiry = g['pending_max_age']
        prox_on = g.get('proximity_cancel_enabled', True)
        prox = g.get('proximity_cancel_pct_r55', _PROXIMITY_PCT_R55_DEFAULT) / 100   # ระยะเฉียด TP (%R55) จาก config

        pend_tags = {o.tag for o in ctx.pendings}
        self._pend = {t: m for t, m in self._pend.items() if t in pend_tags}

        # (A) proximity-cancel + expiry (strategy ทำเอง — engine ไม่หมดอายุ/cancel ให้)
        for o in ctx.pendings:
            m = self._pend.get(o.tag)
            if m is None:
                continue
            age = i - m['placed']
            if (age > expiry) if self.pre_fill_cancel else (age >= expiry):
                cancel.append(o.tag); self._log_unfilled(o.tag, m, i, bar, 'expiry'); continue
            if not prox_on:
                continue
            buf = m['r55'] * prox * PIP
            if m['dir'] == 'BUY'  and bar.high >= m['tp_sel'] - buf:
                cancel.append(o.tag); self._log_unfilled(o.tag, m, i, bar, 'proximity'); continue
            if m['dir'] == 'SELL' and bar.low  <= m['tp_sel'] + buf:
                cancel.append(o.tag); self._log_unfilled(o.tag, m, i, bar, 'proximity'); continue

        remaining = pend_tags - set(cancel)

        # (B) one-plan guard — มี position / pending(เหลือ) / เพิ่งปิดแท่งนี้ → ไม่เปิดใหม่
        just_closed = [] if self.pre_fill_cancel else ctx.last_closed
        if ctx.positions or remaining or just_closed:
            return Decision(place, cancel, modify)
        # (C) เคารพ allow_new_entry (Friday/Gap fact จาก engine)
        if not ctx.allow_new_entry:
            return Decision(place, cancel, modify)

        # (D) หาสัญญาณ
        sig = analyze_bar(ctx.window, i, cfg)   # lot จาก config (portfolio_start) — ไม่พึ่ง self.portfolio
        if sig is None:
            return Decision(place, cancel, modify)

        # (E) สร้าง Order ต่อไม้ — เก็บ place + ไม้ที่ proximity ตัด (cut) + pending · ยังไม่ใส่ plan_id (รอรู้ก่อนว่า place ว่างไหม)
        cut, pend_new = [], []   # [(label, m)] · m = ข้อมูลไม้ (plan_id เติมหลังลูป) — กัน drift จากการ ++ ก่อนรู้ผล place
        for ep, label, lot, is_mkt, sl_i, tp_i in sig.entries:
            kind = "MARKET" if is_mkt else "LIMIT"
            m = {'tp_sel': tp_i, 'sl': sl_i, 'r55': sig.range55, 'dir': sig.direction,
                 'placed': i, 'price': ep, 'place_time': str(ctx.bar.time)}   # plan_id เติมหลังลูป
            # place-bar proximity-cancel: LIMIT ที่ "ไม่ fill แท่งนี้" แต่ราคาแท่งที่วางเฉียด TP แล้ว → ไม่วาง
            #   section A เห็นเฉพาะ pending จากแท่งก่อน → ไม้ที่เพิ่งวางตกหล่น · อุดที่นี่ (เกณฑ์เดียวกับ section A · fill ชนะ proximity เหมือน next-bar)
            if not is_mkt and prox_on:
                buf = sig.range55 * prox * PIP
                if sig.direction == 'SELL':
                    fills_now, grazed = bar.high >= ep, bar.low <= tp_i + buf
                else:
                    fills_now, grazed = bar.low <= ep, bar.high >= tp_i - buf
                if (not fills_now) and grazed:
                    cut.append((label, m)); continue
            place.append(Order(kind=kind, price=ep, lot=lot, sl=sl_i, tp=tp_i, tag=label))
            if not is_mkt:
                pend_new.append((label, m))

        # plan_id = mirror engine (engine.py:192 ++ เฉพาะ if decision.place) · place ว่าง (proximity ตัดครบ) → เลขลบ ไม่ชน engine (บวก)
        if place:
            self._plan_id += 1; pid = self._plan_id
        else:
            self._cancel_plan_id -= 1; pid = self._cancel_plan_id
        self.plan_meta[pid] = {
            'plan_id':          pid,
            'father_start_bar': sig.father_start,
            'father_end_bar':   sig.father_end,
            'father_pct':       _r(sig.father_pct_r55, 1),
            'mother_bar':       sig.mother_idx,
            'mother_pct':       _r(sig.mother_pct_r55, 1),
            'reasons':          list(sig.reasons),
        }
        for label, m in cut:        # ไม้ที่ proximity ตัดตอนวาง — plan_id เดียวกับ plan (place→บวก · ตัดครบ→ลบ)
            m['plan_id'] = pid; self._log_unfilled(label, m, i, bar, 'proximity')
        for label, m in pend_new:   # ไม้ที่วางจริง (pending) — เก็บ plan_id ให้ expiry/proximity-ทีหลังใช้ (section A)
            m['plan_id'] = pid; self._pend[label] = m
        return Decision(place, cancel, modify)

    def _log_unfilled(self, tag, m, death_bar, bar, reason):
        self.unfilled.append({
            'plan_id': m.get('plan_id'), 'tag': tag, 'direction': m['dir'],
            'kind': 'LIMIT', 'limit_price': m.get('price'),
            'sl': m.get('sl'), 'tp': m.get('tp_sel'),
            'place_time': m.get('place_time'), 'place_bar': m['placed'],
            'death_time': str(bar.time), 'death_bar': death_bar, 'reason': reason,
        })

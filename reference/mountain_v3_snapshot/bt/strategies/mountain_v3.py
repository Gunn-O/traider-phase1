# ============================================================================
# bt/strategies/mountain_v3.py
# ----------------------------------------------------------------------------
# ภูเขา v3 (clean) — แกะจาก backtest เก่า v4.45 (Mountain Only) เอา "วิธีคิด" มาทำใหม่
#   สเปก: docs/MOUNTAIN_V3_CLEAN_SPEC.md (source of truth) · id: mountain_v3
#
# *** STAGE 2 (ตรง contract engine): กลยุทธ์บอกแค่ "จุดเข้า+SL+TP" · engine fill/ปิดเอง ***
#   - ภูเขา valid ครบ (F1/F4/F6/F7a + ล็อกยอด C + F7b/F8 ผ่าน) ตอนราคาแตะ buffer 10% (C)
#     → วาง LIMIT 1 ไม้ ที่ base_lo (risk-based lot · reuse _compute_lots) · SL=base_lo−40%h · TP=base_lo+40%h
#   - engine fill เองเมื่อราคา [low,high] พาดผ่าน base_lo (intrabar) · ปิดเองที่ SL/TP เท่านั้น
#   - ยก pending (ยังไม่ fill): ยอดใหม่เหนือยอดล็อก · ฐานเปลี่ยน · timeout (pending_expiry_bars)
#   - *** ไม่มี force-close/zone 30% *** → label TP/SL ถูกเป๊ะ (TP=กำไร · SL=ขาดทุน)
#   - 1 ไม้ (base_lo) ก่อน · 3 ไม้/M1 ทีหลัง
#
# reuse (ไม่ copy): scan_swings/_calc_r55/_r จาก bt/strategies/_util.py
# ============================================================================
from __future__ import annotations

from bt.contract import Decision, Order
from bt.data import PIP
from bt.strategies.base import Strategy
from bt.strategies._util import scan_swings, _calc_r55, _r, _compute_lots


class MountainV3(Strategy):
    name = "mountain_v3"

    def __init__(self, cfg: dict, portfolio: float = 1000.0,
                 pre_fill_cancel: bool = False):
        self.cfg = cfg
        self.portfolio = portfolio
        self.pre_fill_cancel = pre_fill_cancel   # v3 ไม่มี inject_compat — รับไว้ให้ signature ตรง
        self._tiers = self._parse_tiers(cfg)     # [{when:{height_min/max_pct_r55}, legs:[{off,tp_adj,sl_adj,adj_on}]}]
        # state
        self._used = set()                       # base['bar'] ที่ลองวางไปแล้ว (1 แผน/ภูเขา)
        self._used_peaks = set()                 # peak['bar'] ที่ถูก consume แล้ว — กัน same-peak (1 ยอด 1 entry)
        self._armed = None                       # แผนที่ pending/ถืออยู่ (dict · มี legs list) · None = ว่าง
        self._plan_id = 0                        # mirror engine next_plan_id (++ ต่อ place-batch)
        self._base_check = {}                    # base['bar'] -> 'valid'|'rejected' (F8 first-seen)
        # analytics (อ่านโดย __main__ → plan_meta.csv / unfilled.csv / viewer)
        self.plan_meta = {}
        self.unfilled = []
        self._pend = {}                          # tag -> {plan_id, price, placed, sl, tp_sel, dir, place_time}
        self.filter_stats = {'placed': 0, 'F1': 0, 'F4': 0, 'F6': 0,
                             'F7a': 0, 'F7b': 0, 'F8': 0, 'validC': 0, 'min_tp': 0, 'tier': 0}

    # ---- parse entries → [tier] · รับ 2 โครง (backward-compat) + ไม่มี entries → 1 ไม้ @base_lo ----
    #   list [{when, legs}, ...] → tiers ตรงๆ · map {legs:[...]} (เฟส 1-2) → 1 tier catch-all (when ว่าง)
    #   when: {height_min_pct_r55, height_max_pct_r55} · leg: {offset_pct_height, tp_adj?, sl_adj?, adj_on?}
    @staticmethod
    def _parse_tiers(cfg) -> list:
        ent = cfg.get('entries')
        if isinstance(ent, list) and ent:                     # (a) list ของ tier (มี when)
            tiers = []
            for t in ent:
                if not isinstance(t, dict) or 'legs' not in t:
                    raise ValueError("config 'entries' (list) แต่ละ tier ต้องเป็น dict ที่มี 'legs' "
                                     "(เช่น { when: {...}, legs: [...] }) — แก้ผ่าน Raw YAML")
                tiers.append({'when': t.get('when') or {}, 'legs': MountainV3._parse_leglist(t['legs'])})
            return tiers
        legs = ent.get('legs') if isinstance(ent, dict) else None
        if isinstance(legs, list) and legs:                   # (b) map {legs} → 1 tier catch-all (เฟส 1-2)
            return [{'when': {}, 'legs': MountainV3._parse_leglist(legs)}]
        return [{'when': {}, 'legs': [{'off': 0.0, 'tp_adj': None, 'sl_adj': None, 'adj_on': None}]}]  # (c) ไม่มี entries

    @staticmethod
    def _parse_leglist(legs) -> list:
        if not (isinstance(legs, list) and legs):
            raise ValueError("config 'entries...legs' ต้องเป็น list ของไม้ที่ไม่ว่าง")
        out = []
        for lg in legs:
            if not isinstance(lg, dict) or 'offset_pct_height' not in lg:
                raise ValueError("config 'entries...legs' แต่ละไม้ต้องเป็น dict ที่มี 'offset_pct_height' "
                                 "(เช่น { offset_pct_height: 10 }) — แก้ผ่าน Raw YAML")
            out.append({'off': float(lg['offset_pct_height']),
                        'tp_adj': lg.get('tp_adj'), 'sl_adj': lg.get('sl_adj'),
                        'adj_on': lg.get('adj_on')})
        return out

    # ---- เลือก tier ตามความสูงภูเขา (%R55) — mirror mai_ruay_v2 _select_tier · ไม่ match = None (ทิ้งแผน) ----
    def _select_tier(self, h_pct):
        for t in self._tiers:                                 # ลำดับ list = priority · tier แรกที่ match → หยุด
            w = t['when']
            if w.get('height_min_pct_r55', 0) <= h_pct <= w.get('height_max_pct_r55', 1e9):
                return t
        return None

    def on_bar(self, ctx) -> Decision:
        cfg = self.cfg
        i, bar = ctx.bar_index, ctx.bar
        cancel = []

        # sync _pend กับ pending จริงของ engine (ลบ tag ที่ fill/cancel ไปแล้ว)
        pend_tags = {o.tag for o in ctx.pendings}
        self._pend = {t: m for t, m in self._pend.items() if t in pend_tags}

        # ===== A. มีแผน armed → จัดการ pending (cancel) / เคลียร์เมื่อจบ =====
        if self._armed is not None:
            self._manage_armed(ctx, i, bar, cancel)
            return Decision([], cancel, [])

        # ===== B. ว่าง → ตรวจหาภูเขา valid → วาง LIMIT ที่ base_lo =====
        if ctx.positions or ctx.pendings:
            return Decision([], cancel, [])

        det = self._detect(ctx, i)
        if det is None:
            return Decision([], cancel, [])
        base, peak, height, base_lo, peak_hi, lock_bar, r55, highs, lows = det
        bb, pb = base['bar'], peak['bar']

        # F8 (first-seen · stage-1): จบภูเขา(C)→i มี low ≤ base_lo = ราคาทะลุฐานก่อนเป็นฐานอ้างอิง → ตัดถาวร
        #   ช่วง [C, first_seen] (รวม C) — touch ที่แตะฐาน "พอดีที่ C" ก็นับ (entry ช้า/ซ้ำ)
        if bb not in self._base_check:
            broke = (lock_bar is not None and
                     any(ctx.window[k].low <= base_lo for k in range(int(lock_bar), i + 1)))
            self._base_check[bb] = 'rejected' if broke else 'valid'
            if broke:
                self.filter_stats['F8'] += 1
        if self._base_check[bb] == 'rejected':
            return Decision([], cancel, [])
        if bb in self._used:
            return Decision([], cancel, [])

        # gate: ภูเขาปิดแล้ว (ราคาแตะ buffer 10% = C ล็อกยอด) ถึงประเมิน F7b + วาง
        if lock_bar is None:
            return Decision([], cancel, [])

        # peak-dedup: ยอด (peak ที่ล็อกแล้ว) นี้ถูก consume ไปแล้ว → ฐานนี้เป็น same-peak duplicate → ตัด
        #   (find_base คืนฐานต่ำสุด → เข้าที่ C ก่อน → ล็อก peak · ฐานอื่นที่ share ยอดเดียวกันถูกกัน · รวม doji-pair)
        if pb in self._used_peaks:
            return Decision([], cancel, [])

        # ฟิลเตอร์ (วัดถึง C=lock_bar) — F1/F4/F6/F7a/F7b (F8 เช็คแล้วด้านบน)
        if not self._filters_ok(base, peak, height, r55, lock_bar, highs, lows, i):
            return Decision([], cancel, [])

        # gate valid@C: ภูเขาต้อง valid "ตั้งแต่ตอนจบ (C)" — ถ้า place ช้ากว่า C (i>C) เช็คซ้ำด้วยข้อมูล ณ C
        #   ไม่ valid@C (เช่น F1 ตก เพราะ R55@C ใหญ่ · valid สายตอน R55 หด) → ทิ้งถาวร (ไม่วาดภูเขาย้อนหลัง)
        #   no-look-ahead: winC = window ถึง C (อดีต) เท่านั้น
        if i > lock_bar:
            C = int(lock_bar)
            winC = ctx.window[:C + 1]
            r55C = _calc_r55(winC, C, cfg['r55_bars'])
            HC, LC = scan_swings(winC, r55C, cfg['pair_join_max_pip'],
                                 cfg['pair_min_body_pct_r55'], cfg['thick_exc_pct_r55'],
                                 start=max(0, C - cfg['r55_bars'] + 1))
            if not self._filters_ok(base, peak, height, r55C, C, HC, LC, C, count=False):
                self.filter_stats['validC'] += 1
                self._used.add(bb); self._used_peaks.add(pb)   # ทิ้งถาวร (กันปลุกทีหลัง)
                return Decision([], cancel, [])

        # TP/SL ต่อ leg (anchor base_lo · หน่วย %height) = base ± per-leg adj (mirror mai_ruay_v2 L270-283)
        #   base level = ไม้ no-op (ไม่มี adj) → ใช้เป๊ะ (unrounded · regression-safe) · adj_on:false → ปิด adjust
        base_tp, base_sl = cfg['tp_pct_height'], cfg['sl_pct_height']
        base_tp_lvl = base_lo + base_tp / 100 * height
        base_sl_lvl = base_lo - base_sl / 100 * height

        # tier: เลือกชุด legs ตามความสูงภูเขา (%R55) — mirror v2 · F1 ผ่านแล้ว (gate ภูเขาเล็ก) · ไม่เข้า tier = ทิ้งแผน
        h_pct = (height / PIP) / r55 * 100 if r55 > 0 else 0
        tier = self._select_tier(h_pct)
        if tier is None:                                  # ความสูงไม่เข้า tier ไหน → ไม่เล่น (ไม่มี catch-all อัตโนมัติ)
            self.filter_stats['tier'] += 1
            self._used.add(bb); self._used_peaks.add(pb)
            return Decision([], cancel, [])
        legs = tier['legs']

        # build ทุก leg: price = base_lo + off%×height · tp_i/sl_i ต่อไม้ · min_tp เช็คต่อไม้ (TP−price ทิศกำไร BUY)
        min_tp = cfg['min_tp_pip']
        built = []                                        # [(off, price[r], tp_i[unrounded], sl_i[unrounded], survive)]
        for lg in legs:
            off = lg['off']
            use = lg['adj_on'] is not False               # default เปิด · adj_on:false → ปิด (ใช้ base)
            tp_pct_i = base_tp + ((lg['tp_adj'] or 0) if use else 0)
            sl_pct_i = base_sl + ((lg['sl_adj'] or 0) if use else 0)
            if sl_pct_i <= 0:                             # clamp: SL ต้อง >0 → ตกกลับ base
                sl_pct_i = base_sl
            if tp_pct_i == base_tp and sl_pct_i == base_sl:
                tp_i, sl_i = base_tp_lvl, base_sl_lvl     # no-op → base เป๊ะ (ไม่คำนวณใหม่ · ผลเฟส 1 นิ่ง)
            else:
                tp_i = base_lo + tp_pct_i / 100 * height
                sl_i = base_lo - sl_pct_i / 100 * height
            price = _r(base_lo + off / 100 * height, 3)
            survive = (tp_i - price) / PIP >= min_tp      # TP ใกล้/ผิดฝั่ง entry → ไม่วางไม้นั้น (ใช้ tp_i)
            built.append((off, price, tp_i, sl_i, survive))
        if not any(b[4] for b in built):                  # ทุกไม้ตก min_tp → ทิ้งแผน
            self.filter_stats['min_tp'] += 1
            self._used.add(bb); self._used_peaks.add(pb)
            return Decision([], cancel, [])

        # lot: budget = พอร์ต×risk% · แบ่งตาม "จำนวนไม้ที่ตั้ง" (รวมไม้ตก min_tp · กินส่วนแบ่งทิ้ง · mirror v2)
        #   sl_dist ต่อไม้ = price − sl_i (>0 · per-leg SL) → equal_risk
        budget = cfg['portfolio_start'] * cfg['risk_per_plan_pct'] / 100
        sl_dists = [(price - sl_i) / PIP for _, price, _, sl_i, _ in built]
        if any(d <= 0 for d in sl_dists):                 # SL ต้องต่ำกว่าทุก entry (กัน degenerate)
            self._used.add(bb); self._used_peaks.add(pb)
            return Decision([], cancel, [])
        lots = _compute_lots(sl_dists, budget, 'equal_risk')
        if not lots:
            self._used.add(bb); self._used_peaks.add(pb)
            return Decision([], cancel, [])

        # วาง LIMIT เฉพาะไม้ survive · ทุกไม้ในก้อนเดียว → engine ออก 1 plan_id
        self._plan_id += 1
        pid = self._plan_id
        orders, legs_state = [], []
        for k, (off, price, tp_i, sl_i, survive) in enumerate(built):
            if k >= len(lots):                            # budget overflow-drop (ปกติไม่เกิด · floor → Σrisk ≤ budget)
                break
            tag = f"mountain:tech#{pid}:{k}"
            m = {'plan_id': pid, 'price': price, 'placed': i,
                 'sl': _r(sl_i, 3), 'tp_sel': _r(tp_i, 3), 'dir': 'BUY',
                 'place_time': str(bar.time)}
            if not survive:                               # min_tp cut: log · ไม่วาง · กินส่วนแบ่ง budget ทิ้ง
                self._log_unfilled(tag, i, bar, 'min_tp', m)
                continue
            orders.append(Order(kind="LIMIT", price=price, lot=lots[k],
                                sl=_r(sl_i, 3), tp=_r(tp_i, 3), tag=tag))
            self._pend[tag] = m
            legs_state.append({'tag': tag, 'place_bar': i})
        if not orders:                                    # survivor ถูก overflow-drop หมด (degenerate)
            self._used.add(bb); self._used_peaks.add(pb)
            return Decision([], cancel, [])

        self._used.add(bb); self._used_peaks.add(pb)
        self.filter_stats['placed'] += 1
        self._armed = {'plan_id': pid, 'base_bar': bb, 'base_lo': base_lo,
                       'peak_bar': pb, 'peak_hi': peak_hi, 'height': height,
                       'legs': legs_state}
        self._write_plan_meta(base, peak, height, base_lo, peak_hi, lock_bar, r55, i, bar, highs, lows, base_tp_lvl, base_sl_lvl, len(orders), legs)
        return Decision(orders, cancel, [])

    # ---- จัดการแผน armed (หลาย leg): ยก pending ตามเงื่อนไข · เคลียร์เมื่อ "ทุก leg" จบ ----
    def _manage_armed(self, ctx, i, bar, cancel) -> None:
        a = self._armed
        cfg = self.cfg
        pid = a['plan_id']
        live = {o.tag for o in ctx.pendings}                 # tag ที่ยัง pending (fill/cancel แล้วจะหาย)
        has_pos = any(p.plan_id == pid for p in ctx.positions)

        # เหตุผลระดับแผน (ยกทุก leg ที่ยัง pending พร้อมกัน): ยอดใหม่เหนือยอดล็อก · ฐานเปลี่ยน
        plan_reason = None
        if any(lg['tag'] in live for lg in a['legs']):
            if bar.high > a['peak_hi']:
                plan_reason = 'repeak'
            else:
                det = self._detect(ctx, i)
                if det is not None and det[0]['bar'] != a['base_bar']:
                    plan_reason = 'base_change'

        for lg in a['legs']:
            tag = lg['tag']
            if tag not in live:                              # fill แล้ว หรือ cancel ไปแล้ว → ข้าม
                continue
            reason = plan_reason
            if reason is None and i - lg['place_bar'] >= cfg['pending_expiry_bars']:
                reason = 'expiry'                            # แต่ละ leg นับ expiry เอง (แยก)
            if reason:
                cancel.append(tag)
                self._log_unfilled(tag, i, bar, reason)

        if plan_reason and not has_pos and pid in self.plan_meta:
            self.plan_meta[pid]['status'] = 'cancelled:' + plan_reason

        # เคลียร์เมื่อ "ทุก leg จบ": ไม่เหลือ pending (หลังหัก cancel รอบนี้) และไม่มี position ค้าง
        alive = [lg for lg in a['legs'] if lg['tag'] in live and lg['tag'] not in cancel]
        if not alive and not has_pos:                        # จบทุกไม้ (cancel/ปิด TP-SL) → ว่าง
            self._armed = None

    # ---- ตรวจหาภูเขา (reuse stage-1: find_base + peak-lock) ----
    def _detect(self, ctx, i):
        cfg = self.cfg
        r55 = _calc_r55(ctx.window, i, cfg['r55_bars'])
        if r55 <= 0:
            return None
        lo = max(0, i - cfg['r55_bars'] + 1)
        highs, lows = scan_swings(ctx.window, r55, cfg['pair_join_max_pip'],
                                  cfg['pair_min_body_pct_r55'], cfg['thick_exc_pct_r55'], start=lo)
        if not lows or not highs:
            return None
        base = min(lows, key=lambda d: d['body_lo'])
        base_lo = base['body_lo']
        if not any(h['bar'] > base['bar'] for h in highs):
            return None
        peak, lock_bar = self._locked_peak(highs, base['bar'], base_lo, ctx.window, i)
        if peak is None:
            return None
        height = peak['body_hi'] - base_lo
        if height <= 0:
            return None
        return base, peak, height, base_lo, peak['body_hi'], lock_bar, r55, highs, lows

    # ---- F1/F4/F6/F7a/F7b · F4/F7b วัดถึง C=lock_bar · F6 วัดถึง place bar (i) ----
    def _filters_ok(self, base, peak, height, r55, lock_bar, highs, lows, place_bar, count=True) -> bool:
        cfg = self.cfg
        bb, pb = base['bar'], peak['bar']
        if height / PIP < cfg['min_height_pct_r55'] / 100 * r55:           # F1
            if count: self.filter_stats['F1'] += 1
            return False
        X, span = pb - bb, lock_bar - bb                                   # span = base→C (F4/F7b)
        if X + (lock_bar - pb) < cfg['min_mountain_bars']:                 # F4 (X+Y = span_C)
            if count: self.filter_stats['F4'] += 1
            return False
        # F6: ฐาน→place (no-look-ahead proxy ของ entry · ตรงสเปก "ฐาน→entry") — ตัด stale base ที่ place ช้าหลัง C
        if place_bar - bb > cfg['max_base_to_entry_bars']:                 # F6 (base→place)
            if count: self.filter_stats['F6'] += 1
            return False
        if X > cfg['upleg_check_min_bars']:                               # F7a (SH+SL รวม ช่วง ฐาน,ยอด)
            n = (sum(1 for o in lows if bb < o['bar'] < pb)
                 + sum(1 for h in highs if bb < h['bar'] < pb))
            if n > cfg['upleg_max_count']:
                if count: self.filter_stats['F7a'] += 1
                return False
        if span > cfg['downleg_check_min_bars']:                          # F7b (SH+SL รวม ช่วง ยอด,C]
            n = (sum(1 for h in highs if pb < h['bar'] <= lock_bar)
                 + sum(1 for o in lows if pb < o['bar'] <= lock_bar))
            if n > cfg['downleg_max_count']:
                if count: self.filter_stats['F7b'] += 1
                return False
        return True

    def _write_plan_meta(self, base, peak, height, base_lo, peak_hi, lock_bar, r55, i, bar, highs, lows, tp, sl, n_placed=1, legs=()) -> None:
        pid = self._plan_id
        hp = height / PIP
        swings = "|".join(
            [f"SL:{o['bar']:g}:{_r(o['body_lo'], 3):g}" for o in lows]
            + [f"SH:{h['bar']:g}:{_r(h['body_hi'], 3):g}" for h in highs]
        )
        self.plan_meta[pid] = {
            'plan_id': pid, 'base_bar': base['bar'], 'base_mid': _r(base_lo, 3),
            'peak_bar': peak['bar'], 'peak_mid': _r(peak_hi, 3),
            'lock_bar': lock_bar if lock_bar is not None else '',
            'height': _r(height, 3), 'entry_bar': i, 'trigger_bar': i, 'status': 'placed',
            'swings': swings,
            'reasons': [
                f"ฐาน #{base['i0']}-{base['i1']} lo {base_lo:.2f} · ยอด #{peak['i0']}-{peak['i1']} hi {peak_hi:.2f}",
                f"สูง {hp:.0f}pip ({hp / r55 * 100:.0f}%R55) · วาง {n_placed} ไม้ offset {[lg['off'] for lg in legs]} (#{i}) · C@{lock_bar}",
                f"TP {tp:.2f} (+{self.cfg['tp_pct_height']}%) · SL {sl:.2f} (−{self.cfg['sl_pct_height']}%)",
            ],
        }

    def _log_unfilled(self, tag, death_bar, bar, reason, m=None) -> None:
        m = m if m is not None else self._pend.get(tag, {})
        self.unfilled.append({
            'plan_id': m.get('plan_id'), 'tag': tag, 'direction': m.get('dir', 'BUY'),
            'kind': 'LIMIT', 'limit_price': m.get('price'), 'sl': m.get('sl'), 'tp': m.get('tp_sel'),
            'place_time': m.get('place_time'), 'place_bar': m.get('placed'),
            'death_time': str(bar.time), 'death_bar': death_bar, 'reason': reason,
        })

    # ยอด = running max body_hi หลังฐาน — ล็อกเมื่อราคา retrace แตะ buffer (peak_lock_pct%) ครั้งแรก
    #   ไม่แตะ buffer จนถึง i → global-max · ไม่มี high หลังฐาน → (None, None) · คืน (peak|None, lock_bar|None)
    def _locked_peak(self, highs, base_bar, base_lo, window, i):
        lock = self.cfg['peak_lock_pct'] / 100
        sh = sorted((h for h in highs if h['bar'] > base_bar), key=lambda d: d['bar'])
        if not sh:
            return None, None
        cur = None
        si = 0
        for k in range(int(base_bar) + 1, i + 1):
            if cur is not None and window[k].low <= base_lo + lock * (cur['body_hi'] - base_lo):
                return cur, k
            while si < len(sh) and sh[si]['bar'] <= k:
                if cur is None or sh[si]['body_hi'] > cur['body_hi']:
                    cur = sh[si]
                si += 1
        return cur, None

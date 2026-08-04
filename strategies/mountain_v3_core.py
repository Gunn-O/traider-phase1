"""
strategies/mountain_v3_core.py — Mountain v3 decision core (engine-compatible)

Verbatim port of the validated snapshot
reference/mountain_v3_snapshot/bt/strategies/mountain_v3.py — the SINGLE source
of Mountain v3 logic. Only the imports differ from the snapshot:
  bt.contract.{Decision,Order} → repo-local dataclasses below (engine duck-types)
  bt.data.PIP                  → strategies._util.PIP
  bt.strategies.base.Strategy  → plain class (base is trivial)
  bt.strategies._util          → strategies._util (shared with MaiRuay v2)

This keeps the core free of any `reference/` runtime import so it can drive the
LIVE pipeline (via strategies/mountain.py), yet the parity harness runs THIS
exact class inside the snapshot engine → byte-identical trades.csv (both configs).

*** DO NOT change the decision logic — it is validated against golden.
    Any behaviour change breaks parity. ***

Mountain v3: BUY-only. Find swing base(low)+peak(high) → lock peak when price
retraces to base_lo+10%height (point C) → filters F1/F4/F6/F7a/F7b/F8 + valid@C
→ place LIMIT at base_lo+offset%height · fixed %height TP/SL · one peak → one plan.
No trailing (closes at SL/TP only). Pending is stateful: cancel on repeak /
base_change / expiry while unfilled.
"""
from __future__ import annotations

from dataclasses import dataclass

from strategies._util import PIP, scan_swings, _calc_r55, _r, _compute_lots


# ---------- repo-local contract (mirrors bt.contract; engine consumes duck-typed) ----------
@dataclass
class Order:
    kind:  str        # "MARKET" | "LIMIT"
    price: float
    lot:   float
    sl:    float
    tp:    float
    tag:   str


@dataclass
class Decision:
    place:  list      # list[Order]
    cancel: list      # list[str] (tags to cancel)
    modify: list      # list[Modify] (unused by Mountain v3 — no trailing)


class MountainV3:
    name = "mountain_v3"

    def __init__(self, cfg: dict, portfolio: float = 1000.0,
                 pre_fill_cancel: bool = False):
        self.cfg = cfg
        self.portfolio = portfolio
        self.pre_fill_cancel = pre_fill_cancel   # v3 has no inject_compat — accepted for signature parity
        self._tiers = self._parse_tiers(cfg)     # [{when:{height_min/max_pct_r55}, legs:[{off,tp_adj,sl_adj,adj_on}]}]
        # state
        self._used = set()                       # base['bar'] already attempted (1 plan/mountain)
        self._used_peaks = set()                 # peak['bar'] already consumed — block same-peak (1 peak 1 entry)
        self._armed = None                       # armed plan (dict · has legs list) · None = idle
        self._plan_id = 0                        # mirror engine next_plan_id (++ per place-batch)
        self._base_check = {}                    # base['bar'] -> 'valid'|'rejected' (F8 first-seen)
        # analytics (read by __main__ → plan_meta.csv / unfilled.csv / viewer)
        self.plan_meta = {}
        self.unfilled = []
        self._pend = {}                          # tag -> {plan_id, price, placed, sl, tp_sel, dir, place_time}
        self.filter_stats = {'placed': 0, 'F1': 0, 'F4': 0, 'F6': 0,
                             'F7a': 0, 'F7b': 0, 'F8': 0, 'validC': 0, 'min_tp': 0, 'tier': 0}

    # ---- parse entries → [tier] · accepts 2 shapes (backward-compat) + no entries → 1 leg @base_lo ----
    @staticmethod
    def _parse_tiers(cfg) -> list:
        ent = cfg.get('entries')
        if isinstance(ent, list) and ent:                     # (a) list of tiers (with when)
            tiers = []
            for t in ent:
                if not isinstance(t, dict) or 'legs' not in t:
                    raise ValueError("config 'entries' (list) each tier must be a dict with 'legs' "
                                     "(e.g. { when: {...}, legs: [...] }) — edit via Raw YAML")
                tiers.append({'when': t.get('when') or {}, 'legs': MountainV3._parse_leglist(t['legs'])})
            return tiers
        legs = ent.get('legs') if isinstance(ent, dict) else None
        if isinstance(legs, list) and legs:                   # (b) map {legs} → 1 catch-all tier
            return [{'when': {}, 'legs': MountainV3._parse_leglist(legs)}]
        return [{'when': {}, 'legs': [{'off': 0.0, 'tp_adj': None, 'sl_adj': None, 'adj_on': None}]}]  # (c) no entries

    @staticmethod
    def _parse_leglist(legs) -> list:
        if not (isinstance(legs, list) and legs):
            raise ValueError("config 'entries...legs' must be a non-empty list of legs")
        out = []
        for lg in legs:
            if not isinstance(lg, dict) or 'offset_pct_height' not in lg:
                raise ValueError("config 'entries...legs' each leg must be a dict with 'offset_pct_height' "
                                 "(e.g. { offset_pct_height: 10 }) — edit via Raw YAML")
            out.append({'off': float(lg['offset_pct_height']),
                        'tp_adj': lg.get('tp_adj'), 'sl_adj': lg.get('sl_adj'),
                        'adj_on': lg.get('adj_on')})
        return out

    # ---- select tier by mountain height (%R55) — mirror mai_ruay_v2 _select_tier · no match = None (drop) ----
    def _select_tier(self, h_pct):
        for t in self._tiers:                                 # list order = priority · first match → stop
            w = t['when']
            if w.get('height_min_pct_r55', 0) <= h_pct <= w.get('height_max_pct_r55', 1e9):
                return t
        return None

    def on_bar(self, ctx) -> Decision:
        cfg = self.cfg
        i, bar = ctx.bar_index, ctx.bar
        cancel = []

        # sync _pend with engine's real pendings (drop tags that filled/cancelled)
        pend_tags = {o.tag for o in ctx.pendings}
        self._pend = {t: m for t, m in self._pend.items() if t in pend_tags}

        # ===== A. armed plan → manage pending (cancel) / clear when done =====
        if self._armed is not None:
            self._manage_armed(ctx, i, bar, cancel)
            return Decision([], cancel, [])

        # ===== B. idle → look for a valid mountain → place LIMIT at base_lo =====
        if ctx.positions or ctx.pendings:
            return Decision([], cancel, [])

        det = self._detect(ctx, i)
        if det is None:
            return Decision([], cancel, [])
        base, peak, height, base_lo, peak_hi, lock_bar, r55, highs, lows = det
        bb, pb = base['bar'], peak['bar']

        # F8 (first-seen · stage-1): a low ≤ base_lo between C and i means price broke the base
        # before it became the reference base → permanently reject.
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

        # gate: mountain must be closed (price touched buffer 10% = C, peak locked) before evaluating F7b + placing
        if lock_bar is None:
            return Decision([], cancel, [])

        # peak-dedup: this locked peak already consumed → same-peak duplicate base → drop
        if pb in self._used_peaks:
            return Decision([], cancel, [])

        # filters (measured to C=lock_bar) — F1/F4/F6/F7a/F7b (F8 checked above)
        if not self._filters_ok(base, peak, height, r55, lock_bar, highs, lows, i):
            return Decision([], cancel, [])

        # gate valid@C: mountain must be valid "at close (C)" — if placing later than C (i>C) recheck with data at C
        # no-look-ahead: winC = window up to C (past) only
        if i > lock_bar:
            C = int(lock_bar)
            winC = ctx.window[:C + 1]
            r55C = _calc_r55(winC, C, cfg['r55_bars'])
            HC, LC = scan_swings(winC, r55C, cfg['pair_join_max_pip'],
                                 cfg['pair_min_body_pct_r55'], cfg['thick_exc_pct_r55'],
                                 start=max(0, C - cfg['r55_bars'] + 1))
            if not self._filters_ok(base, peak, height, r55C, C, HC, LC, C, count=False):
                self.filter_stats['validC'] += 1
                self._used.add(bb); self._used_peaks.add(pb)   # permanent drop (don't re-wake later)
                return Decision([], cancel, [])

        # TP/SL per leg (anchor base_lo · units %height) = base ± per-leg adj (mirror mai_ruay_v2)
        base_tp, base_sl = cfg['tp_pct_height'], cfg['sl_pct_height']
        base_tp_lvl = base_lo + base_tp / 100 * height
        base_sl_lvl = base_lo - base_sl / 100 * height

        # tier: pick legs by mountain height (%R55) — mirror v2 · F1 passed · no tier = drop plan
        h_pct = (height / PIP) / r55 * 100 if r55 > 0 else 0
        tier = self._select_tier(h_pct)
        if tier is None:
            self.filter_stats['tier'] += 1
            self._used.add(bb); self._used_peaks.add(pb)
            return Decision([], cancel, [])
        legs = tier['legs']

        # build each leg: price = base_lo + off%×height · tp_i/sl_i per leg · min_tp per leg (TP−price BUY-profit)
        min_tp = cfg['min_tp_pip']
        built = []                                        # [(off, price[r], tp_i[unrounded], sl_i[unrounded], survive)]
        for lg in legs:
            off = lg['off']
            use = lg['adj_on'] is not False               # default on · adj_on:false → off (use base)
            tp_pct_i = base_tp + ((lg['tp_adj'] or 0) if use else 0)
            sl_pct_i = base_sl + ((lg['sl_adj'] or 0) if use else 0)
            if sl_pct_i <= 0:                             # clamp: SL must be >0 → fall back to base
                sl_pct_i = base_sl
            if tp_pct_i == base_tp and sl_pct_i == base_sl:
                tp_i, sl_i = base_tp_lvl, base_sl_lvl     # no-op → base exactly (regression-safe)
            else:
                tp_i = base_lo + tp_pct_i / 100 * height
                sl_i = base_lo - sl_pct_i / 100 * height
            price = _r(base_lo + off / 100 * height, 3)
            survive = (tp_i - price) / PIP >= min_tp      # TP too close / wrong side → don't place this leg
            built.append((off, price, tp_i, sl_i, survive))
        if not any(b[4] for b in built):                  # all legs fail min_tp → drop plan
            self.filter_stats['min_tp'] += 1
            self._used.add(bb); self._used_peaks.add(pb)
            return Decision([], cancel, [])

        # lot: budget = portfolio×risk% · split by "legs placed" (incl. min_tp-cut legs · they eat a share · mirror v2)
        budget = cfg['portfolio_start'] * cfg['risk_per_plan_pct'] / 100
        sl_dists = [(price - sl_i) / PIP for _, price, _, sl_i, _ in built]
        if any(d <= 0 for d in sl_dists):                 # SL must be below every entry (guard degenerate)
            self._used.add(bb); self._used_peaks.add(pb)
            return Decision([], cancel, [])
        lots = _compute_lots(sl_dists, budget, 'equal_risk')
        if not lots:
            self._used.add(bb); self._used_peaks.add(pb)
            return Decision([], cancel, [])

        # place LIMIT for surviving legs only · all in one batch → engine issues 1 plan_id
        self._plan_id += 1
        pid = self._plan_id
        orders, legs_state = [], []
        for k, (off, price, tp_i, sl_i, survive) in enumerate(built):
            if k >= len(lots):                            # budget overflow-drop (rare · floor → Σrisk ≤ budget)
                break
            tag = f"mountain:tech#{pid}:{k}"
            m = {'plan_id': pid, 'price': price, 'placed': i,
                 'sl': _r(sl_i, 3), 'tp_sel': _r(tp_i, 3), 'dir': 'BUY',
                 'place_time': str(bar.time)}
            if not survive:                               # min_tp cut: log · don't place · still eats budget share
                self._log_unfilled(tag, i, bar, 'min_tp', m)
                continue
            orders.append(Order(kind="LIMIT", price=price, lot=lots[k],
                                sl=_r(sl_i, 3), tp=_r(tp_i, 3), tag=tag))
            self._pend[tag] = m
            legs_state.append({'tag': tag, 'place_bar': i})
        if not orders:                                    # survivors all overflow-dropped (degenerate)
            self._used.add(bb); self._used_peaks.add(pb)
            return Decision([], cancel, [])

        self._used.add(bb); self._used_peaks.add(pb)
        self.filter_stats['placed'] += 1
        self._armed = {'plan_id': pid, 'base_bar': bb, 'base_lo': base_lo,
                       'peak_bar': pb, 'peak_hi': peak_hi, 'height': height,
                       'legs': legs_state}
        self._write_plan_meta(base, peak, height, base_lo, peak_hi, lock_bar, r55, i, bar, highs, lows, base_tp_lvl, base_sl_lvl, len(orders), legs)
        return Decision(orders, cancel, [])

    # ---- manage armed plan (multi-leg): cancel pending on conditions · clear when ALL legs done ----
    def _manage_armed(self, ctx, i, bar, cancel) -> None:
        a = self._armed
        cfg = self.cfg
        pid = a['plan_id']
        live = {o.tag for o in ctx.pendings}                 # tags still pending (gone once filled/cancelled)
        has_pos = any(p.plan_id == pid for p in ctx.positions)

        # plan-level reasons (cancel all still-pending legs together): new peak above locked peak · base changed
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
            if tag not in live:                              # filled or already cancelled → skip
                continue
            reason = plan_reason
            if reason is None and i - lg['place_bar'] >= cfg['pending_expiry_bars']:
                reason = 'expiry'                            # each leg counts its own expiry
            if reason:
                cancel.append(tag)
                self._log_unfilled(tag, i, bar, reason)

        if plan_reason and not has_pos and pid in self.plan_meta:
            self.plan_meta[pid]['status'] = 'cancelled:' + plan_reason

        # clear when ALL legs done: no pending left (after this round's cancels) and no position held
        alive = [lg for lg in a['legs'] if lg['tag'] in live and lg['tag'] not in cancel]
        if not alive and not has_pos:                        # every leg done (cancel/closed TP-SL) → idle
            self._armed = None

    # ---- detect mountain (reuse stage-1: find_base + peak-lock) ----
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

    # ---- F1/F4/F6/F7a/F7b · F4/F7b measured to C=lock_bar · F6 measured to place bar (i) ----
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
        # F6: base→place (no-look-ahead proxy for entry) — cut stale base placed long after C
        if place_bar - bb > cfg['max_base_to_entry_bars']:                 # F6 (base→place)
            if count: self.filter_stats['F6'] += 1
            return False
        if X > cfg['upleg_check_min_bars']:                               # F7a (SH+SL total in base,peak)
            n = (sum(1 for o in lows if bb < o['bar'] < pb)
                 + sum(1 for h in highs if bb < h['bar'] < pb))
            if n > cfg['upleg_max_count']:
                if count: self.filter_stats['F7a'] += 1
                return False
        if span > cfg['downleg_check_min_bars']:                          # F7b (SH+SL total in peak,C]
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

    # peak = running max body_hi after base — locked when price retraces to buffer (peak_lock_pct%) first time
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

"""
MT5 Live Broker — ส่ง order จริงไปที่ MT5 Terminal

รองรับ mode='micro' (Cent account) และ mode='live' (Standard/Real)
- ใช้ ORDER_FILLING_IOC (Immediate or Cancel)
- deviation = 20 points (= 2 pips XAUUSD)
- แยก magic per mode เพื่อให้ bot จัดการเฉพาะ order ของตัวเอง
- ไม่แตะ order ที่ user เปิดเองใน MT5

Interface ตรงกับ PaperBroker เพื่อให้ main.py สลับใช้ได้:
    open_position, update_positions, close_all,
    get_open_positions, get_closed_trades, get_stats,
    get_current_price
"""

import os
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import logging

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None
    MT5_AVAILABLE = False

logger = logging.getLogger(__name__)

# Magic numbers — identify orders ของ bot แยกตาม mode
MAGIC_BY_MODE = {
    'micro': 10002,  # Cent account
    'live':  10003,  # Standard/Real account
}

DEFAULT_DEVIATION = 20   # points (max slippage on entry fill — market order only)
DEFAULT_FILLING = None   # set in __init__ after mt5 import succeeds
COMMENT_MAX_LEN = 31     # MT5 comment field is 31 chars max
MAX_SPREAD_PIP  = 100    # safety: reject order if current spread > 100 pip (= 1 USD)
                         # Cent broker normal ~28 pip; spike ใน news ~80+ pip
                         # > 100 pip = ตลาดผิดปกติ (off-hours / news / liquidity drop)

# Pending-order expiration = N × current TF duration (auto from env BACKTEST_TIMEFRAME)
# 5 แท่งเป็นค่ามาตรฐาน — ถ้าราคาไม่กลับมาภายใน 5 แท่ง = setup กลายเป็น stale
PENDING_EXPIRY_BARS = 5
TF_SECONDS = {
    'M1': 60, 'M5': 300, 'M15': 900,
    'M30': 1800, 'H1': 3600, 'H4': 14400,
}


class MT5LiveBroker:
    """
    Real broker — ส่ง mt5.order_send() จริงทุก open/close

    Tracks positions ผ่าน mt5.positions_get(magic=...) — ไม่เก็บ state ใน memory
    เพื่อให้ตรงกับสภาพจริงของ MT5 ตลอด (กรณี user ปิด order เอง / SL/TP hit ระหว่าง bot ปิด)
    """

    def __init__(self, symbol: str, mode: str = 'live',
                 max_spread_pip: float = MAX_SPREAD_PIP):
        if not MT5_AVAILABLE or mt5 is None:
            raise RuntimeError("MetaTrader5 not available — MT5LiveBroker requires Windows + MT5")

        if mode not in MAGIC_BY_MODE:
            raise ValueError(f"MT5LiveBroker mode must be one of {list(MAGIC_BY_MODE)}, got {mode!r}")

        self.symbol = symbol
        self.mode = mode
        self.magic = MAGIC_BY_MODE[mode]
        self.deviation = DEFAULT_DEVIATION
        self.max_spread_pip = max_spread_pip
        self.filling = mt5.ORDER_FILLING_IOC
        self.closed_trades: List[dict] = []
        # Track tickets we've seen open, so we can detect "newly closed" by diff
        self._known_open_tickets: set = set()
        # Per-ticket trailing state (Mountain only — MAI_RUAY uses static SL)
        # ticket → {stage, direction, tp1, tp2, tech_point, height_usd}
        # ⚠️ In-memory only — lost on restart (broker still holds last-known SL)
        self._trail_state: Dict[int, dict] = {}

        self._verify_environment()
        logger.info(
            f"💹 MT5LiveBroker initialized | symbol={symbol} mode={mode} "
            f"magic={self.magic} deviation={self.deviation} filling=IOC "
            f"max_spread={self.max_spread_pip}pip"
        )

    # ------------------------------------------------------------------ helpers

    def _verify_environment(self):
        """Pre-flight checks — fail loud ถ้า MT5 / symbol / trade ไม่พร้อม"""
        ti = mt5.terminal_info()
        if ti is None:
            raise RuntimeError("MT5 terminal_info() = None — MT5 not connected")
        if not ti.connected:
            raise RuntimeError("MT5 terminal not connected to broker")
        if not ti.trade_allowed:
            raise RuntimeError(
                "MT5 trade_allowed=False — เปิด Auto Trading ใน MT5 Desktop "
                "(ปุ่ม Algo Trading บน toolbar ต้องเป็นสีเขียว)"
            )

        ai = mt5.account_info()
        if ai is None:
            raise RuntimeError("MT5 account_info() = None — not logged in")

        si = mt5.symbol_info(self.symbol)
        if si is None:
            raise RuntimeError(f"Symbol {self.symbol!r} not found on broker")
        if not si.visible:
            # Try to enable in Market Watch
            if not mt5.symbol_select(self.symbol, True):
                raise RuntimeError(f"Cannot enable symbol {self.symbol!r} in Market Watch")
        if si.trade_mode == 0:
            raise RuntimeError(f"Symbol {self.symbol!r} trade_mode=0 (DISABLED)")

        logger.info(
            f"✅ Pre-flight OK | account={ai.login}/{ai.server} "
            f"trade_mode={ai.trade_mode}(0=demo,2=real) bal={ai.balance} {ai.currency} "
            f"symbol_trade_mode={si.trade_mode}"
        )

    def get_current_price(self) -> Tuple[float, float]:
        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            raise RuntimeError(f"Cannot get tick for {self.symbol}")
        return tick.bid, tick.ask

    # ------------------------------------------------------------------ open

    def open_position(
        self,
        action: str,
        lot: float,
        sl: float,
        tp: float,
        plan_id: str,
        candle_time: datetime,
        trade_id: Optional[str] = None,
        technique: Optional[str] = None,
        session: Optional[str] = None,
        beauty_score: Optional[int] = None,
        entry_price: Optional[float] = None,  # required: zone level for pending limit
        trail_meta: Optional[dict] = None,    # Mountain trailing: {tp1, tp2_base, tech_point, height_pip}
    ) -> Optional[int]:
        """
        ส่ง pending LIMIT order ที่ entry_price (zone level) — รอราคากลับมาแตะ.
        Fallback เป็น market order ถ้าราคาเลย entry ไปแล้ว (ไม่สามารถตั้ง limit ได้).

        Expiration = PENDING_EXPIRY_BARS × current_TF (auto-scale ตาม TF)

        Returns:
            broker ticket (int) หรือ None ถ้า fail
        """
        if action not in ('BUY', 'SELL'):
            logger.error(f"Invalid action {action!r}")
            return None

        bid, ask = self.get_current_price()
        spread_usd = ask - bid
        spread_pip = spread_usd * 100

        # Safety: reject if spread too wide (broker spike / news / off-hours)
        if spread_pip > self.max_spread_pip:
            logger.warning(
                f"⛔ Spread too wide: {spread_pip:.1f}pip > {self.max_spread_pip}pip "
                f"(bid={bid:.3f} ask={ask:.3f}) — order rejected"
            )
            return None

        # ── Decide order type: PENDING LIMIT vs MARKET fallback ─────────────
        # Pending limit only valid when entry is on the "wait" side of current price:
        #   BUY_LIMIT: entry < ask (need price to drop)
        #   SELL_LIMIT: entry > bid (need price to rise)
        # If price already past entry, use market order as fallback (zone touched + bounced fast).
        is_pending = False
        if entry_price is not None and entry_price > 0:
            if action == 'BUY' and entry_price < ask:
                is_pending = True
            elif action == 'SELL' and entry_price > bid:
                is_pending = True

        # Spread adjustment (same logic as before — applied to broker SL/TP for SELL)
        if action == 'BUY':
            broker_sl = float(sl)
            broker_tp = float(tp)
        else:
            broker_sl = float(sl) + spread_usd
            broker_tp = float(tp) + spread_usd
            logger.info(
                f"  SELL spread adjust: spread={spread_pip:.1f}pip → "
                f"SL {sl:.3f}→{broker_sl:.3f}  TP {tp:.3f}→{broker_tp:.3f}"
            )

        # Choose order type + price
        if is_pending:
            if action == 'BUY':
                order_type = mt5.ORDER_TYPE_BUY_LIMIT
            else:
                order_type = mt5.ORDER_TYPE_SELL_LIMIT
            price = float(entry_price)
            trade_action = mt5.TRADE_ACTION_PENDING
        else:
            order_type = mt5.ORDER_TYPE_BUY if action == 'BUY' else mt5.ORDER_TYPE_SELL
            price = ask if action == 'BUY' else bid
            trade_action = mt5.TRADE_ACTION_DEAL
            logger.info(
                f"  ⚡ Market order fallback (price already past entry: "
                f"entry={entry_price} bid/ask={bid:.3f}/{ask:.3f})"
            )

        # Expiration: N × TF duration (auto-scale)
        active_tf = os.getenv('BACKTEST_TIMEFRAME', 'M5').upper()
        tf_secs = TF_SECONDS.get(active_tf, 300)
        expire_secs = tf_secs * PENDING_EXPIRY_BARS
        expiration_dt = datetime.now() + timedelta(seconds=expire_secs)

        comment = (trade_id or f"BOT-{plan_id}")[:COMMENT_MAX_LEN]

        request = {
            "action":       trade_action,
            "symbol":       self.symbol,
            "volume":       float(lot),
            "type":         order_type,
            "price":        price,
            "sl":           broker_sl,
            "tp":           broker_tp,
            "deviation":    self.deviation,
            "magic":        self.magic,
            "comment":      comment,
            "type_filling": self.filling,
        }
        if is_pending:
            # Pending order: time-bound expiration
            request["type_time"]  = mt5.ORDER_TIME_SPECIFIED
            request["expiration"] = int(expiration_dt.timestamp())
        else:
            request["type_time"]  = mt5.ORDER_TIME_GTC

        # Validate before send
        check = mt5.order_check(request)
        if check is None:
            logger.error(f"order_check returned None: {mt5.last_error()}")
            return None
        if check.retcode != 0:
            logger.error(
                f"order_check failed | retcode={check.retcode} comment={check.comment!r} "
                f"margin={check.margin} margin_free={check.margin_free}"
            )
            return None

        # Send
        result = mt5.order_send(request)
        if result is None:
            logger.error(f"order_send returned None: {mt5.last_error()}")
            return None
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(
                f"order_send failed | retcode={result.retcode} comment={result.comment!r} "
                f"deal={result.deal} order={result.order}"
            )
            return None

        ticket = int(result.order)
        self._known_open_tickets.add(ticket)
        # Register trailing state if metadata provided (Mountain only)
        if trail_meta:
            self._trail_state[ticket] = {
                'stage':      0,
                'direction':  action,
                'tp1':        float(trail_meta.get('tp1') or 0),
                'tp2':        float(trail_meta.get('tp2_base') or trail_meta.get('tp2') or 0),
                'tech_point': float(trail_meta.get('tech_point') or trail_meta.get('base_lo') or 0),
                'height_usd': float(trail_meta.get('height') or 0) / 100.0,  # pip → USD
            }
            logger.info(
                f"💹 Trail state registered | ticket={ticket} "
                f"tp1={self._trail_state[ticket]['tp1']:.3f} "
                f"tp2={self._trail_state[ticket]['tp2']:.3f} "
                f"tech={self._trail_state[ticket]['tech_point']:.3f} "
                f"H={self._trail_state[ticket]['height_usd']:.3f}"
            )
        order_label = (
            f"{action}_LIMIT @ {price:.3f} (expire {expire_secs}s = {PENDING_EXPIRY_BARS}×{active_tf})"
            if is_pending
            else f"{action} MARKET @ {result.price:.3f}"
        )
        logger.info(
            f"💹 LIVE {order_label} | ticket={ticket} vol={result.volume} "
            f"sl={broker_sl:.3f} tp={broker_tp:.3f} comment={comment}"
        )
        return ticket

    # ------------------------------------------------------------------ monitor

    def _build_pos_dict(self, pos, action: str, current_price: float) -> dict:
        """Convert MT5 position object to our standard dict shape"""
        if action == "BUY":
            pnl = (current_price - pos.price_open) * pos.volume * 100
        else:
            pnl = (pos.price_open - current_price) * pos.volume * 100
        return {
            "ticket":       int(pos.ticket),
            "trade_id":     pos.comment or f"LIVE-{pos.ticket}",
            "action":       action,
            "lot":          float(pos.volume),
            "lot_size":     float(pos.volume),
            "entry":        float(pos.price_open),
            "entry_price":  float(pos.price_open),
            "sl":           float(pos.sl),
            "sl_price":     float(pos.sl),
            "tp":           float(pos.tp),
            "tp_price":     float(pos.tp),
            "plan_id":      "",
            "open_time":    datetime.fromtimestamp(pos.time).isoformat(),
            "pnl":          round(pnl, 2),
            "result":       "PENDING",
        }

    def _query_open(self) -> Dict[int, dict]:
        """Return {ticket: pos_dict} for our magic only"""
        positions = mt5.positions_get(symbol=self.symbol)
        if positions is None:
            return {}
        try:
            bid, ask = self.get_current_price()
        except Exception:
            bid = ask = 0.0
        out = {}
        for pos in positions:
            if pos.magic != self.magic:
                continue  # not our order
            action = "BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL"
            current = bid if action == "BUY" else ask
            out[int(pos.ticket)] = self._build_pos_dict(pos, action, current)
        return out

    def _query_history_deal(self, ticket: int) -> Optional[dict]:
        """Look up close info from MT5 history for a given ticket (after position closed).

        Also extracts the original trade_id from the *entry* deal's comment
        (we write our trade_id there in open_position). This lets the caller
        sync the close back to the correct row in position_monitor / Sheets /
        LocalDB, instead of inventing a synthetic 'LIVE-{ticket}' key that
        nothing else recognizes.
        """
        deals = mt5.history_deals_get(position=ticket)
        if deals is None or len(deals) == 0:
            return None
        # First deal = entry (carries our trade_id in comment); last = close.
        entry_deal = deals[0]
        close_deal = deals[-1]
        entry_comment = str(getattr(entry_deal, "comment", "") or "").strip()
        return {
            "close_price":   float(close_deal.price),
            "close_time":    datetime.fromtimestamp(close_deal.time).isoformat(),
            "pnl":           round(float(close_deal.profit), 2),
            "entry_comment": entry_comment,
        }

    # ------------------------------------------------------------------ trailing SL

    def _modify_sl(self, position, new_sl: float, new_tp: Optional[float] = None) -> bool:
        """ส่ง mt5.order_send ปรับ SL (และ TP ถ้าระบุ) ของ position ที่ broker"""
        request = {
            "action":   mt5.TRADE_ACTION_SLTP,
            "position": int(position.ticket),
            "symbol":   self.symbol,
            "sl":       float(new_sl),
            "tp":       float(new_tp if new_tp is not None else position.tp),
            "magic":    self.magic,
        }
        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.warning(
                f"SL modify failed | ticket={position.ticket} new_sl={new_sl:.3f} "
                f"retcode={result.retcode if result else None} "
                f"comment={result.comment if result else mt5.last_error()}"
            )
            return False
        return True

    def _apply_trailing(self):
        """
        ตรวจ price ปัจจุบัน → ถ้าแตะ TP1/TP2/TP2+20%H ของ position ที่มี trail_state
        → ปรับ SL ที่ broker ตามขั้น (Mountain v67 spec)

        Stages (BUY only — Mountain เป็น BUY):
            0 → 1: bid ≥ TP1       → SL = tech + 5%H
            1 → 2: bid ≥ TP2_base  → SL = TP1
            2 → 3: bid ≥ TP2+20%H  → SL = TP2
        """
        if not self._trail_state:
            return
        positions = mt5.positions_get(symbol=self.symbol)
        if not positions:
            return
        try:
            tick = mt5.symbol_info_tick(self.symbol)
            if tick is None:
                return
            current_bid = tick.bid
        except Exception:
            return

        for pos in positions:
            if pos.magic != self.magic:
                continue
            ticket = int(pos.ticket)
            st = self._trail_state.get(ticket)
            if not st:
                continue
            # Mountain = BUY only — sanity skip non-BUY
            if pos.type != mt5.POSITION_TYPE_BUY:
                continue

            stage = st['stage']
            new_sl = None
            new_stage = stage

            tp1   = st['tp1']
            tp2   = st['tp2']
            tech  = st['tech_point']
            h_usd = st['height_usd']

            if stage == 0 and tp1 > 0 and current_bid >= tp1:
                new_sl = tech + h_usd * 0.05    # tech + 5%H
                new_stage = 1
            elif stage == 1 and tp2 > 0 and current_bid >= tp2:
                new_sl = tp1                     # SL = TP1
                new_stage = 2
            elif stage == 2 and tp2 > 0:
                tp2_plus20 = tp2 + h_usd * 0.20  # TP2 + 20%H
                if current_bid >= tp2_plus20:
                    new_sl = tp2                 # SL = TP2
                    new_stage = 3

            # Only move SL UP for BUY (never tighten worse)
            if new_sl is not None and new_sl > pos.sl:
                ok = self._modify_sl(pos, new_sl)
                if ok:
                    st['stage'] = new_stage
                    logger.info(
                        f"💹 Trail SL moved | ticket={ticket} stage={stage}→{new_stage} "
                        f"old_sl={pos.sl:.3f} new_sl={new_sl:.3f} bid={current_bid:.3f}"
                    )

    def reconcile_pending(self, trade_ids: List[str]) -> List[dict]:
        """Verify each `trade_id` we *believe* is PENDING against MT5's actual state.

        Returns close-event dicts (same shape as `update_positions`) for trades
        that MT5 says are gone — i.e., the LIMIT order expired, was cancelled,
        or rejected before fill. The caller treats these the same way it would
        a SL/TP close: mark CANCELLED in DB/Sheets, drop from open_orders,
        broadcast `plan_closed`.

        Detection strategy (matches `scripts/reconcile_pending.py`):
          1. Snapshot `positions_get` + `orders_get` — if our trade_id matches
             a live entry there, it's still active. Skip.
          2. Search 24h `history_deals_get` — deals are only created on fills,
             so any deal carrying our comment means the order DID fill (and
             update_positions() handles the WIN/LOSS sync separately). Skip.
          3. Otherwise: the LIMIT was placed but never filled → mark CANCELLED.

        Why not `history_orders_get`? MT5 overwrites the order's comment with
        text like `"expired [2026.05.12 08:42]"` once the order expires, so the
        original trade_id is lost there. Deals preserve the comment because
        deals only fire on fills (no deal = never filled).

        Caller is expected to apply a min-age filter (e.g., 60s) before
        invoking so we don't false-cancel a LIMIT that was just placed but
        MT5 hasn't indexed yet.

        Verified bug fixed by this: 2026-05-12 BUY_LIMIT 4698.173 (ticket
        #3274854807) expired at 08:42 server time without filling; bot UI
        kept showing it as open until the manual reconcile script ran.
        """
        if not trade_ids:
            return []

        positions = mt5.positions_get(symbol=self.symbol) or []
        orders    = mt5.orders_get(symbol=self.symbol)    or []
        live_comments    = [(p.comment or "").strip() for p in positions if p.magic == self.magic]
        pending_comments = [(o.comment or "").strip() for o in orders    if o.magic == self.magic]

        from_dt = datetime.now() - timedelta(hours=24)
        deals = mt5.history_deals_get(from_dt, datetime.now()) or []
        deal_comments = [(d.comment or "").strip() for d in deals if getattr(d, "magic", 0) == self.magic]

        # Broker truncates the comment to 16 chars on many platforms even
        # though the MT5 spec allows 31, so match by prefix (stored is a
        # leading substring of our full trade_id).
        def _matches(stored: str, full_tid: str) -> bool:
            stored = (stored or "").strip()
            if not stored:
                return False
            return stored == full_tid or full_tid.startswith(stored)

        cancelled: List[dict] = []
        now_iso = datetime.now().isoformat()

        for tid in trade_ids:
            if any(_matches(c, tid) for c in live_comments):
                continue   # filled and currently open
            if any(_matches(c, tid) for c in pending_comments):
                continue   # LIMIT still queued
            if any(_matches(c, tid) for c in deal_comments):
                continue   # filled, then closed — update_positions handles that

            # Not in any of: positions / orders / deals → never filled.
            # MT5 has either expired it server-side, the user/admin cancelled
            # it, or it was rejected before reaching the order book. Either
            # way the local PENDING row is stale and should be CANCELLED.
            cancelled.append({
                "trade_id":     tid,
                "ticket":       0,
                "plan_id":      "",
                "action":       "BUY",        # caller already knows; not needed downstream
                "lot":          0.0,
                "lot_size":     0.0,
                "entry":        0.0,
                "entry_price":  0.0,
                "result":       "CANCELLED",
                "close_price":  0.0,
                "close_time":   now_iso,
                "close_reason": "BROKER_REJECT_OR_EXPIRE",
                "pnl":          0.0,
            })
            logger.warning(f"⚠️ Reconcile: {tid} → CANCELLED (not in MT5 positions/orders/deals)")

        return cancelled

    def update_positions(self, candle_time: datetime, current_price: Optional[float] = None) -> List[dict]:
        """
        เช็ค SL/TP / manual close — diff กับ _known_open_tickets เพื่อหา newly closed
        SL/TP ปิดโดย broker เอง (เพราะเราใส่ sl/tp ใน request) — เราแค่ตามอ่าน
        """
        # Apply trailing SL first (Mountain only) — broker server-side update
        try:
            self._apply_trailing()
        except Exception as e:
            logger.warning(f"_apply_trailing error: {e}")

        current_open = self._query_open()
        current_tickets = set(current_open.keys())

        newly_closed_tickets = self._known_open_tickets - current_tickets
        newly_closed = []

        for ticket in newly_closed_tickets:
            hist = self._query_history_deal(ticket)
            if hist is None:
                logger.warning(f"Cannot find history for closed ticket {ticket}")
                continue
            pnl = hist["pnl"]
            # Prefer the trade_id we wrote into the entry deal's comment; fall
            # back to a synthetic id only when the comment is empty (e.g. an
            # order opened outside this bot). Without this, main.py's
            # `if order['trade_id'] == trade_id` never matches and the close
            # never syncs to position_monitor / Sheets / LocalDB.
            trade_id = hist.get("entry_comment") or f"LIVE-{ticket}"
            pos_dict = {
                "ticket":       ticket,
                "trade_id":     trade_id,
                "close_price":  hist["close_price"],
                "close_time":   hist["close_time"],
                "pnl":          pnl,
                "result":       "WIN" if pnl > 0 else "LOSS",
                "close_reason": "TP_HIT" if pnl > 0 else "SL_HIT",
            }
            self.closed_trades.append(pos_dict)
            newly_closed.append(pos_dict)
            logger.info(
                f"💹 LIVE position closed | ticket={ticket} "
                f"close_price={hist['close_price']:.5f} pnl={pnl:.2f}"
            )

        # Update known set to current state + cleanup trail_state for closed tickets
        self._known_open_tickets = current_tickets
        for ticket in list(self._trail_state):
            if ticket not in current_tickets:
                self._trail_state.pop(ticket, None)
        return newly_closed

    def get_open_positions(self) -> List[dict]:
        return list(self._query_open().values())

    # ------------------------------------------------------------------ close

    def _close_one(self, pos, candle_time: datetime, reason: str = "MANUAL") -> Optional[dict]:
        """ส่ง opposite-direction order เพื่อปิด position"""
        bid, ask = self.get_current_price()
        if pos.type == mt5.POSITION_TYPE_BUY:
            order_type = mt5.ORDER_TYPE_SELL
            price = bid
            action = "BUY"
        else:
            order_type = mt5.ORDER_TYPE_BUY
            price = ask
            action = "SELL"

        request = {
            "action":       mt5.TRADE_ACTION_DEAL,
            "position":     int(pos.ticket),
            "symbol":       self.symbol,
            "volume":       float(pos.volume),
            "type":         order_type,
            "price":        price,
            "deviation":    self.deviation,
            "magic":        self.magic,
            "comment":      f"close-{reason}"[:COMMENT_MAX_LEN],
            "type_time":    mt5.ORDER_TIME_GTC,
            "type_filling": self.filling,
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(
                f"close_position failed | ticket={pos.ticket} "
                f"retcode={result.retcode if result else None} "
                f"comment={result.comment if result else mt5.last_error()}"
            )
            return None

        if action == "BUY":
            pnl = (price - pos.price_open) * pos.volume * 100
        else:
            pnl = (pos.price_open - price) * pos.volume * 100

        closed = {
            "ticket":       int(pos.ticket),
            "trade_id":     pos.comment or f"LIVE-{pos.ticket}",
            "action":       action,
            "lot":          float(pos.volume),
            "entry":        float(pos.price_open),
            "sl":           float(pos.sl),
            "tp":           float(pos.tp),
            "close_price":  float(price),
            "close_time":   candle_time.isoformat(),
            "pnl":          round(pnl, 2),
            "result":       "WIN" if pnl > 0 else "LOSS",
            "close_reason": reason,
        }
        self.closed_trades.append(closed)
        logger.info(
            f"💹 LIVE close sent | ticket={pos.ticket} reason={reason} "
            f"close_price={price:.5f} pnl={pnl:.2f}"
        )
        return closed

    def close_all(self, candle_time: datetime) -> List[dict]:
        """Emergency stop — ปิดทุก open position ของ bot (เฉพาะ magic นี้)"""
        positions = mt5.positions_get(symbol=self.symbol)
        if positions is None:
            return []
        closed = []
        for pos in positions:
            if pos.magic != self.magic:
                continue
            r = self._close_one(pos, candle_time, reason="MANUAL")
            if r:
                closed.append(r)
        self._known_open_tickets.clear()
        logger.info(f"💹 LIVE close_all | {len(closed)} positions closed")
        return closed

    # ------------------------------------------------------------------ stats

    def get_closed_trades(self) -> List[dict]:
        return self.closed_trades

    def get_stats(self) -> dict:
        wins = [t for t in self.closed_trades if t["result"] == "WIN"]
        losses = [t for t in self.closed_trades if t["result"] == "LOSS"]
        total_pnl = sum(t["pnl"] for t in self.closed_trades)
        return {
            "total_trades": len(self.closed_trades),
            "wins":         len(wins),
            "losses":       len(losses),
            "win_rate":     len(wins) / len(self.closed_trades) if self.closed_trades else 0,
            "total_pnl":    round(total_pnl, 2),
        }

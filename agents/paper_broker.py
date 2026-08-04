"""
Paper Broker — Simulate MT5 order execution (v4.3)
ดึงราคา real-time จาก MT5 แต่ไม่ส่ง order จริง

V4.3: รองรับ beauty_score, technique, session tracking

Usage:
    broker = PaperBroker(symbol="XAUUSDc")
    ticket = broker.open_position("BUY", lot=0.01, sl=3230, tp=3275, ...)
    newly_closed = broker.update_positions(candle_time)
"""

from datetime import datetime
from typing import Dict, List, Tuple, Optional
import logging

# Execution-quality logger — records spread baseline at signal time (paper mode).
# Import guarded so a broken/missing logger never breaks order execution.
try:
    from agents.g4_execution_logger import log_paper_snapshot as _exec_log_paper
except Exception:  # pragma: no cover — defensive
    _exec_log_paper = None

# MetaTrader5 is only available on Windows
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None
    MT5_AVAILABLE = False
    logging.warning("MetaTrader5 not available - PaperBroker will need mock prices")

logger = logging.getLogger(__name__)

PAPER_TICKET_START = 90000  # เริ่มที่ 90000 เพื่อแยกจาก order จริง


class PaperBroker:
    """
    Simulate MT5 order execution without sending real orders
    """

    def __init__(self, symbol: str):
        """
        Initialize Paper Broker

        Args:
            symbol: Symbol name (e.g., "XAUUSDc", "XAUUSD")
        """
        self.symbol = symbol
        self.positions: Dict[int, dict] = {}  # ticket -> position dict
        self.closed_trades: List[dict] = []
        self.ticket_counter = PAPER_TICKET_START

        logger.info(f"📄 PaperBroker initialized | symbol={symbol}")

    def get_current_price(self) -> Tuple[float, float]:
        """
        ดึง bid/ask จาก MT5 จริง

        Returns:
            (bid, ask) tuple

        Raises:
            RuntimeError: ถ้าดึงราคาไม่ได้
        """
        if not MT5_AVAILABLE or mt5 is None:
            raise RuntimeError("MetaTrader5 not available - use mock prices for testing")

        try:
            tick = mt5.symbol_info_tick(self.symbol)
            if tick is None:
                raise RuntimeError(f"Cannot get tick for {self.symbol}")
            return tick.bid, tick.ask
        except Exception as e:
            logger.error(f"Failed to get price for {self.symbol}: {e}")
            raise

    def get_fill_price(self, ticket: int) -> Optional[float]:
        """Return the actual fill price for an opened ticket.
        Paper broker has no slippage — fill_price == entry the caller passed."""
        pos = self.positions.get(ticket)
        if not pos:
            return None
        return float(pos.get("entry") or pos.get("entry_price") or 0.0) or None

    def get_broker_sl_tp(self, ticket: int):
        """Return (sl, tp) tuple stored with the position. Paper broker has no
        spread adjustment, so these equal what the caller passed — but the
        method exists for interface parity with MT5LiveBroker (main.py calls
        it the same way for both)."""
        pos = self.positions.get(ticket)
        if not pos:
            return None
        sl = pos.get("sl") or pos.get("sl_price")
        tp = pos.get("tp") or pos.get("tp_price")
        if sl is None or tp is None:
            return None
        return (float(sl), float(tp))

    def open_position(
        self,
        action: str,       # BUY / SELL
        lot: float,
        sl: float,
        tp: float,
        plan_id: str,
        candle_time: datetime,
        trade_id: Optional[str] = None,
        technique: Optional[str] = None,  # V4.3
        session: Optional[str] = None,    # V4.3
        beauty_score: Optional[int] = None,  # V4.3
        entry_price: Optional[float] = None,  # For backtest mode
        trail_meta: Optional[dict] = None,    # Mountain trailing metadata
        order_type: Optional[str] = None,     # 'MARKET' | 'LIMIT' | None (auto)
        # MaiRuay v2 pending kwargs are accepted (and ignored) here. The fill /
        # cancel-near-TP / candle-expire logic for LIMITs lives in
        # position_monitor (the single owner of order state) — paper_broker
        # only records the order. Accepting these kwargs prevents TypeError
        # when main.py uses the unified call site.
        pending_bars: int = 5,
        tp_cancel_buffer_pips: float = 0.0,
    ) -> Optional[int]:
        """
        เปิด virtual position (V4.3: รองรับ metadata เพิ่มเติม)

        Args:
            action: "BUY" or "SELL"
            lot: Lot size (e.g., 0.01)
            sl: Stop Loss price
            tp: Take Profit price
            plan_id: Plan ID
            candle_time: Candle timestamp
            trade_id: Optional trade ID
            technique: Technique name (V4.3)
            session: Trading session (V4.3)
            beauty_score: Beauty score 60/80/90/100 (V4.3)
            entry_price: Entry price (for backtest mode, default: get from MT5)

        Returns:
            ticket number หรือ None ถ้าล้มเหลว
        """
        try:
            # Use provided entry_price or get from MT5
            if entry_price is not None:
                entry = entry_price
            else:
                bid, ask = self.get_current_price()
                entry = ask if action == "BUY" else bid

            self.ticket_counter += 1
            ticket = self.ticket_counter

            # Mountain v3 has NO trailing (closes at fixed %height SL/TP only).
            # trail_meta is always None now; keep trail=None so the trailing-SL
            # update block below is inert for every pattern.
            trail = None

            # PaperBroker fills MARKET and LIMIT identically (no order-book
            # simulation). MaiRuay v2 pending-LIMIT fill/cancel/expire logic
            # lives in position_monitor (the single source of truth for order
            # state). PaperBroker just records what the caller asked for.
            ot_upper = (order_type or "MARKET").upper()
            self.positions[ticket] = {
                "ticket": ticket,
                "trade_id": trade_id or f"PAPER-{ticket}",
                "action": action,
                "lot": lot,
                "lot_size": lot,  # Alias for compatibility
                "entry": entry,
                "entry_price": entry,  # Alias
                "sl": sl,
                "sl_price": sl,  # Alias
                "tp": tp,
                "tp_price": tp,  # Alias
                "plan_id": plan_id,
                "open_time": candle_time.isoformat(),
                "pnl": 0.0,
                "result": "PENDING",
                # V4.3: metadata
                "technique": technique or "unknown",
                "session": session or "Unknown",
                "beauty_score_used": beauty_score or 100,
                "order_type": ot_upper,
                # Trailing state (None for non-Mountain)
                "trail": trail,
            }
            logger.info(
                f"📄 Paper {action} opened | "
                f"ticket={ticket} entry={entry:.2f} "
                f"sl={sl:.2f} tp={tp:.2f} lot={lot} order_type={ot_upper}"
            )

            # ── Execution-quality: paper spread baseline at "would-fire" point ──
            # Skip in backtest (no real execution → would pollute the baseline).
            # exec_is_backtest / exec_mode are stamped by main.py after broker
            # creation; default to safe values when absent. Never raises.
            self._log_paper_exec(action, entry, plan_id, candle_time, trade_id)

            return ticket

        except Exception as e:
            logger.error(f"PaperBroker open_position error: {e}")
            return None

    def _log_paper_exec(self, action, entry, plan_id, candle_time, trade_id):
        """Emit a paper_signal execution-quality record (spread baseline).

        Fully guarded — logging must NEVER break order flow. Skips the
        backtest path entirely (no real execution to characterise). When
        DATA_MODE=mt5 and MT5 is connected, pulls the live bid/ask so the
        spread baseline is real; on yfinance / no-tick it logs meta only.
        """
        try:
            if _exec_log_paper is None:
                return
            # Backtest → skip (exec_is_backtest stamped by main.py; default False)
            if getattr(self, "exec_is_backtest", False):
                return

            spread_pip = bid = ask = None
            try:
                bid, ask = self.get_current_price()  # raises on yfinance / no MT5
                spread_pip = round((ask - bid) * 100, 2)  # 1 pip = 0.01 USD
            except Exception:
                pass  # no tick available → log meta only (spread=None)

            _exec_log_paper(
                {
                    "plan_id":     plan_id,
                    "trade_id":    trade_id,
                    "candle_time": candle_time,
                    "direction":   action,
                    "entry":       entry,
                    "mode":        getattr(self, "exec_mode", "paper"),
                    "symbol":      self.symbol,
                },
                spread_pip=spread_pip,
                bid=bid,
                ask=ask,
            )
        except Exception as e:  # pragma: no cover — defensive
            logger.warning(f"paper exec-log failed (order OK): {e}")

    def update_positions(self, candle_time: datetime, current_price: Optional[float] = None) -> List[dict]:
        """
        เช็ค SL/TP hit — เรียกทุก candle close

        Args:
            candle_time: Current candle timestamp
            current_price: Current close price (for backtest mode, default: get from MT5)

        Returns:
            list ของ position ที่ปิดในรอบนี้
        """
        # Use provided current_price or get from MT5
        if current_price is not None:
            bid = ask = current_price  # In backtest, use same price for bid/ask
        else:
            try:
                bid, ask = self.get_current_price()
            except Exception as e:
                logger.error(f"Cannot update positions: {e}")
                return []

        newly_closed = []

        for ticket in list(self.positions.keys()):
            pos = self.positions[ticket]
            action = pos["action"]
            current = bid if action == "BUY" else ask

            # คำนวณ P&L ปัจจุบัน
            if action == "BUY":
                pnl = (current - pos["entry"]) * pos["lot"] * 100
            else:
                pnl = (pos["entry"] - current) * pos["lot"] * 100
            pos["pnl"] = round(pnl, 2)

            # Mountain 3-stage trailing SL (BUY only) — runs before SL/TP check
            trail = pos.get("trail")
            if trail and action == "BUY":
                stage = int(trail.get("stage", 0))
                tp1 = float(trail.get("tp1") or 0)
                tp2 = float(trail.get("tp2") or 0)
                tech = float(trail.get("tech_point") or 0)
                h_usd = float(trail.get("height_usd") or 0)

                new_sl = None
                new_stage = stage

                if stage == 0 and tp1 > 0 and current >= tp1:
                    new_sl = tech + h_usd * 0.05
                    new_stage = 1
                elif stage == 1 and tp2 > 0 and current >= tp2:
                    new_sl = tp1
                    new_stage = 2
                elif stage == 2 and tp2 > 0:
                    tp2_plus20 = tp2 + h_usd * 0.20
                    if current >= tp2_plus20:
                        new_sl = tp2
                        new_stage = 3

                # Only move SL UP for BUY
                if new_sl is not None and new_sl > pos["sl"]:
                    old_sl = pos["sl"]
                    pos["sl"] = new_sl
                    pos["sl_price"] = new_sl
                    trail["stage"] = new_stage
                    logger.info(
                        f"📄 Paper trailing | ticket={ticket} stage={stage}->{new_stage} "
                        f"sl={old_sl:.2f}->{new_sl:.2f} price={current:.2f}"
                    )

            # เช็ค SL/TP hit
            close_reason = None
            close_price = None

            if action == "BUY":
                if current <= pos["sl"]:
                    close_reason = "SL_HIT"
                    close_price = pos["sl"]
                elif current >= pos["tp"]:
                    close_reason = "TP_HIT"
                    close_price = pos["tp"]
            else:  # SELL
                if current >= pos["sl"]:
                    close_reason = "SL_HIT"
                    close_price = pos["sl"]
                elif current <= pos["tp"]:
                    close_reason = "TP_HIT"
                    close_price = pos["tp"]

            if close_reason:
                # คำนวณ final P&L
                if action == "BUY":
                    final_pnl = (close_price - pos["entry"]) * pos["lot"] * 100
                else:
                    final_pnl = (pos["entry"] - close_price) * pos["lot"] * 100

                pos["pnl"] = round(final_pnl, 2)
                pos["result"] = "WIN" if final_pnl > 0 else "LOSS"
                pos["close_reason"] = close_reason
                pos["close_price"] = close_price
                pos["close_time"] = candle_time.isoformat()

                self.closed_trades.append(pos)
                del self.positions[ticket]
                newly_closed.append(pos)

                logger.info(
                    f"📄 Paper {action} closed | "
                    f"ticket={ticket} reason={close_reason} "
                    f"close_price={close_price:.2f} pnl={final_pnl:.2f}"
                )

        return newly_closed

    def get_open_positions(self) -> List[dict]:
        """
        Get all open positions

        Returns:
            List of position dicts
        """
        return list(self.positions.values())


    def close_all(self, candle_time: datetime) -> List[dict]:
        """
        Emergency stop — ปิดทุก position ทันที

        Args:
            candle_time: Current candle timestamp

        Returns:
            List of closed positions
        """
        try:
            bid, ask = self.get_current_price()
        except Exception as e:
            logger.error(f"Cannot close positions: {e}")
            return []

        closed = []

        for ticket, pos in list(self.positions.items()):
            current = bid if pos["action"] == "BUY" else ask

            # คำนวณ P&L
            if pos["action"] == "BUY":
                pnl = (current - pos["entry"]) * pos["lot"] * 100
            else:
                pnl = (pos["entry"] - current) * pos["lot"] * 100

            pos["pnl"] = round(pnl, 2)
            pos["result"] = "WIN" if pnl > 0 else "LOSS"
            pos["close_reason"] = "MANUAL"
            pos["close_price"] = current
            pos["close_time"] = candle_time.isoformat()

            self.closed_trades.append(pos)
            closed.append(pos)

        self.positions.clear()
        logger.info(f"📄 Paper close_all | {len(closed)} positions closed")
        return closed

    def get_closed_trades(self) -> List[dict]:
        """
        Get all closed trades

        Returns:
            List of closed trade dicts
        """
        return self.closed_trades

    def get_stats(self) -> dict:
        """
        Get trading statistics

        Returns:
            Dict with win, loss, total_pnl
        """
        wins = [t for t in self.closed_trades if t["result"] == "WIN"]
        losses = [t for t in self.closed_trades if t["result"] == "LOSS"]
        total_pnl = sum(t["pnl"] for t in self.closed_trades)

        return {
            "total_trades": len(self.closed_trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": len(wins) / len(self.closed_trades) if self.closed_trades else 0,
            "total_pnl": round(total_pnl, 2),
        }
